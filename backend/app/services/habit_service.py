from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    HabitProfile,
    PersonalMemory,
    UserActionEvent,
    UserActionSource,
    UserActionType,
)
from app.services.profile_service import ProfileService
from app.utils.logger import get_logger


logger = get_logger("pomopet.habit_service")

MODEL_VERSION = "habit-v1"
MIN_SAMPLE_COUNT = 3
PREFILL_SAMPLE_COUNT = 5
SUGGESTION_CONFIDENCE = 0.55
PREFILL_CONFIDENCE = 0.78
HALF_LIFE_DAYS = 45.0
ALLOWED_VIEWS = {"inbox", "today", "week"}
ALLOWED_SORT_MODES = {"created_desc", "importance", "date_importance"}


def _feature_enabled() -> bool:
    return os.getenv("PERSONALIZATION_ENABLED", "true").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _time_bucket(local_hour: int) -> str:
    if 5 <= local_hour < 12:
        return "morning"
    if 12 <= local_hour < 17:
        return "afternoon"
    if 17 <= local_hour < 22:
        return "evening"
    return "night"


def _temporal_context(occurred_at: datetime, timezone_offset: int) -> dict[str, str]:
    aware = occurred_at.replace(tzinfo=timezone.utc) if occurred_at.tzinfo is None else occurred_at
    local = aware.astimezone(timezone(timedelta(minutes=timezone_offset)))
    return {
        "time_bucket": _time_bucket(local.hour),
        "day_type": "weekend" if local.weekday() >= 5 else "weekday",
    }


def _clean_context(context: dict[str, Any] | None, occurred_at: datetime) -> dict[str, Any]:
    raw = context or {}
    timezone_offset = raw.get("timezone_offset", 0)
    if not isinstance(timezone_offset, int) or not -720 <= timezone_offset <= 840:
        timezone_offset = 0
    cleaned: dict[str, Any] = {"timezone_offset": timezone_offset}
    cleaned.update(_temporal_context(occurred_at, timezone_offset))

    view = raw.get("view")
    if view in ALLOWED_VIEWS:
        cleaned["view"] = view
    sort_mode = raw.get("sort_mode")
    if sort_mode in ALLOWED_SORT_MODES:
        cleaned["sort_mode"] = sort_mode
    for key in ("rank", "visible_task_count", "duration_minutes", "extension_minutes",
                "suggested_duration_minutes", "suggested_rank"):
        value = raw.get(key)
        if isinstance(value, int) and 0 <= value <= 24 * 60:
            cleaned[key] = value
    for key in ("goal_id", "task_id", "session_id", "suggested_task_id"):
        value = raw.get(key)
        if isinstance(value, str) and 0 < len(value) <= 128:
            cleaned[key] = value
    duration_source = raw.get("duration_source")
    if duration_source in {"selected", "explicit_preference", "habit_prefill", "task_estimate", "chat"}:
        cleaned["duration_source"] = duration_source
    return cleaned


@dataclass(frozen=True)
class EventSpec:
    event_type: UserActionType
    source: UserActionSource
    entity_type: str | None = None
    entity_id: str | None = None
    idempotency_key: str | None = None
    context: dict[str, Any] | None = None
    occurred_at: datetime | None = None


class HabitAggregator:
    """Deterministic, explainable aggregation over immutable productivity events."""

    def __init__(self, database: AsyncSession):
        self.database = database

    @staticmethod
    def _candidate(
        habit_key: str,
        context: dict[str, str],
        observations: list[tuple[str, datetime]],
        now: datetime,
    ) -> dict[str, Any] | None:
        if not observations:
            return None
        counts: dict[str, int] = defaultdict(int)
        weights: dict[str, float] = defaultdict(float)
        last_observed = max(observed_at for _, observed_at in observations)
        for value, observed_at in observations:
            age_days = max(0.0, (now - observed_at).total_seconds() / 86400)
            counts[value] += 1
            weights[value] += math.pow(0.5, age_days / HALF_LIFE_DAYS)
        dominant = max(weights, key=lambda value: (weights[value], counts[value], value))
        evidence_count = len(observations)
        recency = math.pow(
            0.5,
            max(0.0, (now - last_observed).total_seconds() / 86400) / HALF_LIFE_DAYS,
        )
        confidence = (
            weights[dominant]
            / max(sum(weights.values()), 0.0001)
            * min(1.0, evidence_count / PREFILL_SAMPLE_COUNT)
            * recency
        )
        value: Any = int(dominant) if dominant.isdigit() else dominant
        return {
            "habit_key": habit_key,
            "context": context,
            "value": value,
            "distribution": {
                key: {"count": counts[key], "weight": round(weights[key], 4)}
                for key in sorted(counts)
            },
            "evidence_count": evidence_count,
            "matching_count": counts[dominant],
            "confidence": round(confidence, 4),
            "active": evidence_count >= MIN_SAMPLE_COUNT and confidence >= SUGGESTION_CONFIDENCE,
            "last_observed_at": last_observed,
        }

    async def refresh(self, profile_id: str) -> list[HabitProfile]:
        events = (
            await self.database.execute(
                select(UserActionEvent)
                .where(UserActionEvent.profile_id == profile_id)
                .order_by(UserActionEvent.occurred_at.asc())
            )
        ).scalars().all()
        now = datetime.utcnow()
        groups: dict[tuple[str, str], dict[str, Any]] = {}

        def add(key: str, context: dict[str, str], value: Any, observed_at: datetime) -> None:
            context_key = _canonical(context)
            group = groups.setdefault((key, context_key), {"context": context, "items": []})
            group["items"].append((str(value), observed_at))

        started_session_ids: set[str] = set()
        extended_session_ids: set[str] = set()
        for event in events:
            context = json.loads(event.context_json or "{}")
            if event.event_type == UserActionType.SESSION_STARTED:
                duration = context.get("duration_minutes")
                if isinstance(duration, int):
                    add("focus_duration", {}, duration, event.occurred_at)
                    if context.get("task_id"):
                        add("focus_duration", {"task_id": context["task_id"]}, duration, event.occurred_at)
                    if context.get("goal_id"):
                        add("focus_duration", {"goal_id": context["goal_id"]}, duration, event.occurred_at)
                    bucket = context.get("time_bucket")
                    if bucket:
                        add("focus_duration", {"time_bucket": bucket}, duration, event.occurred_at)
                    if bucket and context.get("day_type"):
                        add(
                            "focus_duration",
                            {"time_bucket": bucket, "day_type": context["day_type"]},
                            duration,
                            event.occurred_at,
                        )
                bucket = context.get("time_bucket")
                if bucket:
                    add("focus_start_time", {"day_type": context.get("day_type", "weekday")}, bucket, event.occurred_at)
                started_session_ids.add(event.entity_id or context.get("session_id", ""))
            elif event.event_type == UserActionType.SESSION_EXTENDED:
                extended_session_ids.add(event.entity_id or context.get("session_id", ""))
            elif event.event_type == UserActionType.TASK_SELECTED:
                rank = context.get("rank")
                view = context.get("view")
                if isinstance(rank, int) and view in ALLOWED_VIEWS:
                    add("task_rank", {"view": view}, rank, event.occurred_at)

        extension_times = {
            event.entity_id: event.occurred_at
            for event in events
            if event.event_type == UserActionType.SESSION_STARTED and event.entity_id
        }
        for session_id in started_session_ids:
            if session_id:
                add(
                    "extension_pattern",
                    {},
                    "extended" if session_id in extended_session_ids else "not_extended",
                    extension_times.get(session_id, now),
                )

        candidates = [
            candidate
            for (habit_key, _), group in groups.items()
            if (candidate := self._candidate(habit_key, group["context"], group["items"], now))
        ]
        existing = {
            (habit.habit_key, habit.context_key): habit
            for habit in (
                await self.database.execute(
                    select(HabitProfile).where(HabitProfile.profile_id == profile_id)
                )
            ).scalars().all()
        }
        touched: list[HabitProfile] = []
        candidate_keys: set[tuple[str, str]] = set()
        for candidate in candidates:
            context_key = _canonical(candidate["context"])
            key = (candidate["habit_key"], context_key)
            candidate_keys.add(key)
            habit = existing.get(key)
            if habit is None:
                habit = HabitProfile(
                    id=str(uuid4()), profile_id=profile_id,
                    habit_key=candidate["habit_key"], context_key=context_key,
                    context_json=_canonical(candidate["context"]),
                    value_json=_canonical(candidate["value"]),
                    distribution_json=_canonical(candidate["distribution"]),
                    last_observed_at=candidate["last_observed_at"],
                )
                self.database.add(habit)
            habit.value_json = _canonical(candidate["value"])
            habit.distribution_json = _canonical(candidate["distribution"])
            habit.evidence_count = candidate["evidence_count"]
            habit.matching_count = candidate["matching_count"]
            habit.confidence = candidate["confidence"]
            habit.active = candidate["active"] and not habit.dismissed
            habit.model_version = MODEL_VERSION
            habit.last_observed_at = candidate["last_observed_at"]
            habit.updated_at = now
            touched.append(habit)
        for key, habit in existing.items():
            if key not in candidate_keys and not habit.dismissed:
                habit.active = False
        return touched


class HabitService:
    def __init__(self, database: AsyncSession):
        self.database = database

    @staticmethod
    def serialize(habit: HabitProfile) -> dict[str, Any]:
        return {
            "id": habit.id,
            "habit_key": habit.habit_key,
            "context": json.loads(habit.context_json),
            "value": json.loads(habit.value_json),
            "distribution": json.loads(habit.distribution_json),
            "evidence_count": habit.evidence_count,
            "matching_count": habit.matching_count,
            "confidence": habit.confidence,
            "active": habit.active,
            "model_version": habit.model_version,
            "last_observed_at": habit.last_observed_at.isoformat(),
            "explanation": HabitService._explanation(habit),
        }

    @staticmethod
    def _explanation(habit: HabitProfile) -> str:
        if habit.habit_key == "focus_duration":
            return f"Suggested from {habit.evidence_count} recent focus sessions"
        if habit.habit_key == "task_rank":
            return f"Suggested from {habit.evidence_count} recent task choices"
        if habit.habit_key == "focus_start_time":
            return f"Observed across {habit.evidence_count} recent starts"
        return f"Observed across {habit.evidence_count} recent sessions"

    async def _profile(self):
        return await ProfileService(self.database).get_or_create_default()

    async def list_active(self) -> list[HabitProfile]:
        profile = await self._profile()
        if _feature_enabled() and profile.personalization_on:
            await HabitAggregator(self.database).refresh(profile.id)
            await self.database.commit()
        return list((await self.database.execute(
            select(HabitProfile).where(
                HabitProfile.profile_id == profile.id,
                HabitProfile.active.is_(True),
                HabitProfile.dismissed.is_(False),
            ).order_by(HabitProfile.confidence.desc(), HabitProfile.habit_key.asc())
        )).scalars().all())

    async def dismiss(self, habit_id: str) -> bool:
        profile = await self._profile()
        habit = (await self.database.execute(select(HabitProfile).where(
            HabitProfile.id == habit_id, HabitProfile.profile_id == profile.id,
        ))).scalar_one_or_none()
        if habit is None:
            return False
        habit.dismissed = True
        habit.active = False
        await self.database.commit()
        return True

    async def dismiss_key(self, habit_key: str) -> int:
        profile = await ProfileService(self.database).get_or_create_default()
        habits = (await self.database.execute(select(HabitProfile).where(
            HabitProfile.profile_id == profile.id,
            HabitProfile.habit_key == habit_key,
        ))).scalars().all()
        for habit in habits:
            habit.dismissed = True
            habit.active = False
        if habits:
            await self.database.commit()
        return len(habits)

    async def focus_suggestion(
        self,
        *,
        view: str = "today",
        timezone_offset: int = 0,
        task_id: str | None = None,
        goal_id: str | None = None,
    ) -> dict[str, Any]:
        profile = await self._profile()
        empty = {"duration": None, "task_rank": None}
        if not _feature_enabled() or not profile.personalization_on:
            return empty
        await HabitAggregator(self.database).refresh(profile.id)
        await self.database.commit()

        explicit = (await self.database.execute(select(PersonalMemory).where(
            PersonalMemory.profile_id == profile.id,
            PersonalMemory.key == "explicit_focus_duration",
            PersonalMemory.active.is_(True),
        ))).scalar_one_or_none()
        if explicit is not None:
            duration: dict[str, Any] | None = {
                "minutes": json.loads(explicit.value_json),
                "source": "explicit_preference",
                "mode": "prefill",
                "confidence": 1.0,
                "evidence_count": 1,
                "explanation": "Using your explicit focus-duration preference",
            }
        else:
            now = datetime.now(timezone.utc).astimezone(timezone(timedelta(minutes=timezone_offset)))
            contexts = [
                *([{"task_id": task_id}] if task_id else []),
                *([{"goal_id": goal_id}] if goal_id else []),
                {"time_bucket": _time_bucket(now.hour), "day_type": "weekend" if now.weekday() >= 5 else "weekday"},
                {"time_bucket": _time_bucket(now.hour)},
                {},
            ]
            duration = None
            for context in contexts:
                habit = (await self.database.execute(select(HabitProfile).where(
                    HabitProfile.profile_id == profile.id,
                    HabitProfile.habit_key == "focus_duration",
                    HabitProfile.context_key == _canonical(context),
                    HabitProfile.active.is_(True), HabitProfile.dismissed.is_(False),
                ))).scalar_one_or_none()
                if habit:
                    duration = {
                        "minutes": json.loads(habit.value_json),
                        "source": "behavioral_inference",
                        "mode": "prefill" if habit.confidence >= PREFILL_CONFIDENCE and habit.evidence_count >= PREFILL_SAMPLE_COUNT else "suggestion",
                        "confidence": habit.confidence,
                        "evidence_count": habit.evidence_count,
                        "explanation": self._explanation(habit),
                    }
                    break

        rank_habit = (await self.database.execute(select(HabitProfile).where(
            HabitProfile.profile_id == profile.id,
            HabitProfile.habit_key == "task_rank",
            HabitProfile.context_key == _canonical({"view": view}),
            HabitProfile.active.is_(True), HabitProfile.dismissed.is_(False),
        ))).scalar_one_or_none()
        task_rank = None if rank_habit is None else {
            "rank": json.loads(rank_habit.value_json),
            "source": "behavioral_inference",
            "confidence": rank_habit.confidence,
            "evidence_count": rank_habit.evidence_count,
            "explanation": self._explanation(rank_habit),
        }
        return {"duration": duration, "task_rank": task_rank}


async def capture_behavior_events(
    database: AsyncSession,
    specs: Iterable[EventSpec],
) -> None:
    """Best-effort capture. The caller's already-committed action is never rolled back."""
    try:
        profile = await ProfileService(database).get_or_create_default()
        if not _feature_enabled() or not profile.personalization_on:
            return
        added = 0
        for spec in specs:
            occurred_at = spec.occurred_at or datetime.utcnow()
            if occurred_at.tzinfo is not None:
                occurred_at = occurred_at.astimezone(timezone.utc).replace(tzinfo=None)
            key = (spec.idempotency_key or str(uuid4()))[:180]
            if await database.scalar(select(UserActionEvent.id).where(UserActionEvent.idempotency_key == key)):
                continue
            database.add(UserActionEvent(
                id=str(uuid4()), profile_id=profile.id, event_type=spec.event_type,
                source=spec.source, entity_type=spec.entity_type,
                entity_id=spec.entity_id, idempotency_key=key,
                context_json=_canonical(_clean_context(spec.context, occurred_at)),
                occurred_at=occurred_at,
            ))
            added += 1
        if added:
            await database.flush()
            await HabitAggregator(database).refresh(profile.id)
            await database.commit()
            logger.info("behavior_events_captured profile_id=%s count=%s", profile.id, added)
    except Exception as error:
        await database.rollback()
        logger.warning("behavior_event_capture_failed type=%s", type(error).__name__)
