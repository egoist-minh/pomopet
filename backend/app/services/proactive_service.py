from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    AgentTraceEvent,
    Goal,
    GoalStatus,
    PlanHorizon,
    PlanItem,
    PlanItemStatus,
    ProactiveDecision,
    UserActionEvent,
)
from app.services.ai_service import ModelFactory, ProviderError, provider_model_name
from app.services.agent_memory import agent_memory
from app.services.profile_service import ProfileService
from app.services.user_context_builder import UserContextBuilder


STAY_SILENT = "STAY_SILENT"
TELL_JOKE = "TELL_JOKE"
TELL_DRY_HUMOR = "TELL_DRY_HUMOR"
GIVE_HYDRATION_TIP = "GIVE_HYDRATION_TIP"
GIVE_FOCUS_TIP = "GIVE_FOCUS_TIP"
SUGGEST_PLAN = "SUGGEST_PLAN"
WELCOME = "WELCOME"
GOODBYE = "GOODBYE"
COOLDOWN_MINUTES = 5

PROACTIVE_POLICY_PROMPT = """You are PomoPet, a small desktop companion choosing whether and how
to casually interact with the user. Choose exactly one action from candidate_actions using the
supplied context. During idle time or a break, favor a lightweight interaction when the timing is
safe, but STAY_SILENT remains valid. Vary both the action type and wording using recent interactions;
do not repeat the same bit or tip. Never select an action outside candidate_actions.

TELL_JOKE is playful and friendly. TELL_DRY_HUMOR is understated, wry, and never insulting or cruel.
GIVE_HYDRATION_TIP is a casual reminder to drink water, with no medical claims or guilt.
GIVE_FOCUS_TIP is one immediately actionable productivity tip. SUGGEST_PLAN may only invite the user
to plan; never claim an action was performed or mutate a goal or plan. Respect preferences, avoid
pressure, and use the user's apparent language.

WELCOME is a lifecycle greeting. Choose it when present, greet the user warmly, then briefly mention
the most relevant open tasks and the unresolved topic from recent_conversation when those exist.
Do not invent missing context; keep the whole welcome to at most two compact sentences. GOODBYE is a
lifecycle farewell: choose it when present and write one warm, concise sentence without guilt.

For STAY_SILENT, message must be null. For every visible action, message must be one short, natural
message at most 400 characters. reason_codes must contain 1-3 short UPPER_SNAKE_CASE codes. Return
only the requested structured object."""


class ProactivePolicyChoice(BaseModel):
    action: Literal[
        "STAY_SILENT",
        "TELL_JOKE",
        "TELL_DRY_HUMOR",
        "GIVE_HYDRATION_TIP",
        "GIVE_FOCUS_TIP",
        "SUGGEST_PLAN",
        "WELCOME",
        "GOODBYE",
    ]
    message: str | None = Field(default=None, max_length=400)
    reason_codes: list[str] = Field(min_length=1, max_length=3)


class ProactiveDecisionNotFound(LookupError):
    pass


class ProactiveDecisionConflict(ValueError):
    pass


def utc_iso(value: datetime | None) -> str | None:
    """Serialize SQLite's naive UTC datetimes unambiguously for browser clients."""
    if value is None:
        return None
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return aware.isoformat().replace("+00:00", "Z")


class ProactiveService:
    """Consent-first LLM policy with deterministic safety gates."""

    def __init__(self, database: AsyncSession, *, model=None):
        self.database = database
        self.profiles = ProfileService(database)
        self.model = model

    async def evaluate(
        self,
        *,
        request_id: str,
        trigger: str,
        session_state: str,
        timezone_offset: int,
        provider: Literal["openai", "gemini"] = "openai",
        thread_id: str | None = None,
        now: datetime | None = None,
    ) -> ProactiveDecision:
        existing = await self.database.get(ProactiveDecision, request_id)
        if existing is not None:
            return existing

        now = now or datetime.utcnow()
        local_now = now + timedelta(minutes=timezone_offset)
        local_date = local_now.date().isoformat()
        profile = await self.profiles.get_or_create_default(commit=False)
        traces: list[AgentTraceEvent] = []

        def trace(stage: str, details: dict[str, Any]) -> None:
            traces.append(AgentTraceEvent(
                id=str(uuid4()),
                run_id=request_id,
                sequence=len(traces) + 1,
                stage=stage,
                details_json=json.dumps(details, ensure_ascii=False, sort_keys=True),
            ))

        trace("TRIGGER_RECEIVED", {"trigger": trigger, "session_state": session_state})

        executed_today = int(await self.database.scalar(
            select(func.count()).select_from(ProactiveDecision).where(
                ProactiveDecision.profile_id == profile.id,
                ProactiveDecision.local_date == local_date,
                ProactiveDecision.status == "EXECUTED",
            )
        ) or 0)
        last_executed = (await self.database.execute(
            select(ProactiveDecision).where(
                ProactiveDecision.profile_id == profile.id,
                ProactiveDecision.status == "EXECUTED",
            ).order_by(ProactiveDecision.executed_at.desc()).limit(1)
        )).scalar_one_or_none()
        planning_opportunity = await self._has_planning_opportunity(local_date)
        state = {
            "profile_id": profile.id,
            "local_date": local_date,
            "local_hour": local_now.hour,
            "session_state": session_state,
            "executed_today": executed_today,
            "has_planning_opportunity": planning_opportunity,
            "proactive_enabled": profile.proactive_enabled,
            "proactive_jokes_on": profile.proactive_jokes_on,
            "proactive_planning_on": profile.proactive_planning_on,
        }
        trace("STATE_BUILT", state)

        lifecycle_action = WELCOME if trigger == "welcome" else GOODBYE if trigger == "goodbye" else None
        candidates = [STAY_SILENT]
        if lifecycle_action:
            candidates.append(lifecycle_action)
        else:
            if profile.proactive_planning_on and planning_opportunity:
                candidates.append(SUGGEST_PLAN)
            if profile.proactive_jokes_on and session_state in {"idle", "break"}:
                candidates.extend([
                    TELL_JOKE,
                    TELL_DRY_HUMOR,
                    GIVE_HYDRATION_TIP,
                    GIVE_FOCUS_TIP,
                ])
        trace("CANDIDATES_CREATED", {"actions": candidates})

        blocking_reason = None
        if not profile.proactive_enabled:
            blocking_reason = "PROACTIVE_DISABLED"
        elif not lifecycle_action and session_state in {"running", "paused"}:
            blocking_reason = "FOCUS_ACTIVE"
        elif not lifecycle_action and (local_now.hour >= 22 or local_now.hour < 7):
            blocking_reason = "QUIET_HOURS"
        elif (
            not lifecycle_action
            and
            last_executed is not None
            and last_executed.executed_at is not None
            and last_executed.executed_at > now - timedelta(minutes=COOLDOWN_MINUTES)
        ):
            blocking_reason = "COOLDOWN_ACTIVE"
        trace("SAFETY_APPLIED", {
            "allowed": blocking_reason is None,
            "blocking_reason": blocking_reason,
        })

        action = STAY_SILENT
        message = None
        target = None
        reasons: list[str]
        if blocking_reason:
            reasons = [blocking_reason]
        elif len(candidates) == 1:
            reasons = ["NO_USEFUL_OPPORTUNITY"]
        else:
            context = await self._build_decision_context(
                profile_id=profile.id,
                local_now=local_now,
                trigger=trigger,
                session_state=session_state,
                executed_today=executed_today,
                candidates=candidates,
                thread_id=thread_id,
            )
            trace("CONTEXT_BUILT", {
                "active_goal_count": len(context["active_goals"]),
                "today_plan_count": len(context["today_plan"]),
                "open_task_count": len(context["open_tasks"]),
                "recent_conversation_count": len(context["recent_conversation"]),
                "recent_user_action_count": len(context["recent_user_actions"]),
                "recent_proactive_count": len(context["recent_proactive_actions"]),
                "personalization_included": bool(context["user_context"]),
            })
            try:
                choice = await self._select_with_llm(context, provider)
                if choice.action not in candidates:
                    raise ValueError("LLM selected an action outside candidate_actions")
                action = choice.action
                reasons = [self._normalize_reason_code(code) for code in choice.reason_codes]
                if action == STAY_SILENT:
                    message = None
                else:
                    message = (choice.message or "").strip()
                    if not message:
                        raise ValueError("LLM selected a visible action without a message")
                target = (
                    "plan" if action == SUGGEST_PLAN
                    else "hydrate" if action == GIVE_HYDRATION_TIP
                    else None
                )
                trace("LLM_DECISION", {
                    "action": choice.action,
                    "provider": provider,
                    "model": provider_model_name(provider),
                })
            except Exception as error:
                action = STAY_SILENT
                message = None
                target = None
                reasons = ["LLM_POLICY_UNAVAILABLE"]
                trace("LLM_FAILED", {"error_type": type(error).__name__, "provider": provider})

        trace("ACTION_SELECTED", {"action": action, "reason_codes": reasons})
        decision = ProactiveDecision(
            id=request_id,
            profile_id=profile.id,
            created_at=now,
            trigger=trigger,
            session_state=session_state,
            local_date=local_date,
            selected_action=action,
            message=message,
            target=target,
            reason_codes_json=json.dumps(reasons),
            state_snapshot_json=json.dumps(state, ensure_ascii=False, sort_keys=True),
            candidate_actions_json=json.dumps(candidates),
            status="SILENT" if action == STAY_SILENT else "SELECTED",
        )
        self.database.add(decision)
        self.database.add_all(traces)
        try:
            await self.database.commit()
        except IntegrityError:
            # A concurrent retry may win after the initial lookup. The request id
            # remains authoritative, so return that committed immutable result.
            await self.database.rollback()
            existing = await self.database.get(ProactiveDecision, request_id)
            if existing is None:
                raise
            return existing
        await self.database.refresh(decision)
        return decision

    async def _build_decision_context(
        self,
        *,
        profile_id: str,
        local_now: datetime,
        trigger: str,
        session_state: str,
        executed_today: int,
        candidates: list[str],
        thread_id: str | None,
    ) -> dict[str, Any]:
        active_goals = list((await self.database.execute(
            select(Goal)
            .where(Goal.status == GoalStatus.ACTIVE)
            .order_by(Goal.updated_at.desc())
            .limit(8)
        )).scalars().all())
        today_plan = list((await self.database.execute(
            select(PlanItem)
            .where(
                PlanItem.horizon == PlanHorizon.DAY,
                PlanItem.planned_for == local_now.date().isoformat(),
                PlanItem.status != PlanItemStatus.DROPPED,
            )
            .order_by(PlanItem.updated_at.desc())
            .limit(12)
        )).scalars().all())
        recent_user_actions = list((await self.database.execute(
            select(UserActionEvent)
            .where(UserActionEvent.profile_id == profile_id)
            .order_by(UserActionEvent.occurred_at.desc())
            .limit(12)
        )).scalars().all())
        recent_proactive = list((await self.database.execute(
            select(ProactiveDecision)
            .where(
                ProactiveDecision.profile_id == profile_id,
                ProactiveDecision.status == "EXECUTED",
            )
            .order_by(ProactiveDecision.executed_at.desc())
            .limit(6)
        )).scalars().all())
        recent_conversation: list[dict[str, str]] = []
        if thread_id:
            try:
                recent_conversation = await agent_memory.get_recent_conversation(thread_id)
            except Exception:
                # Conversation recall is optional; lifecycle messages must fail soft.
                recent_conversation = []
        user_context = await UserContextBuilder(self.database).build(
            "proactive focus task plan productivity joke communication preference"
        )
        return {
            "local_datetime": local_now.isoformat(timespec="minutes"),
            "weekday": local_now.strftime("%A"),
            "trigger": trigger,
            "session_state": session_state,
            "candidate_actions": candidates,
            "executed_proactive_actions_today": executed_today,
            "active_goals": [{
                "title": goal.title,
                "definition_of_done": goal.definition_of_done,
                "deadline": goal.deadline,
                "importance": goal.importance.value,
            } for goal in active_goals],
            "today_plan": [{
                "title": item.name,
                "status": item.status.value,
                "estimated_minutes": item.estimated_duration,
            } for item in today_plan],
            "open_tasks": [{
                "title": item.name,
                "priority": item.priority.value if item.priority else None,
                "deadline": item.deadline,
                "estimated_minutes": item.estimated_duration,
            } for item in list((await self.database.execute(
                select(PlanItem)
                .where(PlanItem.completed.is_(False), PlanItem.status == PlanItemStatus.OPEN)
                .order_by(PlanItem.updated_at.desc())
                .limit(8)
            )).scalars().all())],
            "recent_conversation": recent_conversation,
            "recent_user_actions": [{
                "type": event.event_type.value,
                "source": event.source.value,
                "entity_type": event.entity_type,
                "occurred_at": event.occurred_at.isoformat(),
            } for event in recent_user_actions],
            "recent_proactive_actions": [{
                "action": decision.selected_action,
                "message": decision.message,
                "executed_at": decision.executed_at.isoformat() if decision.executed_at else None,
            } for decision in recent_proactive],
            "user_context": user_context,
        }

    async def _select_with_llm(
        self,
        context: dict[str, Any],
        provider: Literal["openai", "gemini"],
    ) -> ProactivePolicyChoice:
        model = self.model or ModelFactory.create(provider, max_tokens=240, temperature=0.7)
        try:
            structured = model.with_structured_output(ProactivePolicyChoice)
            result = await structured.ainvoke([
                SystemMessage(PROACTIVE_POLICY_PROMPT),
                HumanMessage(json.dumps(context, ensure_ascii=False)),
            ])
            return (
                result
                if isinstance(result, ProactivePolicyChoice)
                else ProactivePolicyChoice.model_validate(result)
            )
        except (ProviderError, ValidationError):
            raise
        except Exception as error:
            raise ProviderError(f"{provider.title()} proactive policy is unavailable") from error

    @staticmethod
    def _normalize_reason_code(value: str) -> str:
        normalized = "".join(
            character if character.isalnum() else "_" for character in value.upper()
        )
        normalized = "_".join(part for part in normalized.split("_") if part)
        return (normalized or "LLM_DECISION")[:64]

    async def mark_executed(
        self, decision_id: str, *, now: datetime | None = None
    ) -> ProactiveDecision:
        decision = await self.database.get(ProactiveDecision, decision_id)
        if decision is None:
            raise ProactiveDecisionNotFound("Proactive decision was not found")
        if decision.status == "SILENT":
            raise ProactiveDecisionConflict("Silent decisions cannot be executed")
        if decision.status == "EXECUTED":
            return decision

        decision.status = "EXECUTED"
        decision.executed_at = now or datetime.utcnow()
        sequence = int(await self.database.scalar(
            select(func.max(AgentTraceEvent.sequence)).where(
                AgentTraceEvent.run_id == decision_id
            )
        ) or 0) + 1
        self.database.add(AgentTraceEvent(
            id=str(uuid4()),
            run_id=decision_id,
            sequence=sequence,
            stage="ACTION_EXECUTED",
            details_json=json.dumps({"action": decision.selected_action}),
        ))
        await self.database.commit()
        await self.database.refresh(decision)
        return decision

    async def list_runs(self, limit: int) -> list[ProactiveDecision]:
        profile = await self.profiles.get_or_create_default()
        result = await self.database.execute(
            select(ProactiveDecision).where(
                ProactiveDecision.profile_id == profile.id
            ).order_by(ProactiveDecision.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_run(self, decision_id: str) -> tuple[ProactiveDecision, list[AgentTraceEvent]]:
        decision = await self.database.get(ProactiveDecision, decision_id)
        if decision is None:
            raise ProactiveDecisionNotFound("Proactive decision was not found")
        result = await self.database.execute(
            select(AgentTraceEvent).where(
                AgentTraceEvent.run_id == decision_id
            ).order_by(AgentTraceEvent.sequence.asc())
        )
        return decision, list(result.scalars().all())

    async def _has_planning_opportunity(self, local_date: str) -> bool:
        active_goal_ids = list((await self.database.execute(
            select(Goal.id).where(Goal.status == GoalStatus.ACTIVE)
        )).scalars().all())
        if not active_goal_ids:
            return False
        planned_goal_ids = set((await self.database.execute(
            select(PlanItem.goal_id).where(
                PlanItem.goal_id.in_(active_goal_ids),
                PlanItem.horizon == PlanHorizon.DAY,
                PlanItem.planned_for == local_date,
                PlanItem.status != PlanItemStatus.DROPPED,
            )
        )).scalars().all())
        return any(goal_id not in planned_goal_ids for goal_id in active_goal_ids)

    @staticmethod
    def serialize(decision: ProactiveDecision) -> dict[str, Any]:
        return {
            "decision_id": decision.id,
            "action": decision.selected_action,
            "message": decision.message,
            "target": decision.target,
            "reason_codes": json.loads(decision.reason_codes_json),
            "status": decision.status,
            "created_at": utc_iso(decision.created_at),
            "executed_at": utc_iso(decision.executed_at),
        }

    @staticmethod
    async def delete_history(database: AsyncSession, profile_id: str) -> None:
        run_ids = select(ProactiveDecision.id).where(
            ProactiveDecision.profile_id == profile_id
        )
        await database.execute(delete(AgentTraceEvent).where(AgentTraceEvent.run_id.in_(run_ids)))
        await database.execute(delete(ProactiveDecision).where(
            ProactiveDecision.profile_id == profile_id
        ))
