from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    MemorySensitivity,
    MemorySource,
    RelationalState,
    RelationshipEpisode,
    RelationshipEpisodeKind,
    RelationshipMemoryAudit,
    RelationshipMemoryStatus,
    SharedRitual,
)
from app.services.profile_service import ProfileService
from app.services.relationship_schemas import EpisodeCandidate, RitualCandidate


MIN_EPISODE_SALIENCE = 0.65
LOW_SALIENCE_ARCHIVE_DAYS = 180
RELATIONSHIP_RULE_VERSION = "relationship-v1"
_SAFE_TOKEN = re.compile(r"[^\W_]{3,}", re.UNICODE)
_STOP_WORDS = {
    "and", "the", "this", "that", "with", "from", "have", "remember",
    "mình", "những", "được", "của", "với", "rằng", "nhớ", "chúng", "tụi",
}


class RelationshipMemoryNotFoundError(LookupError):
    pass


def _normalized_key(value: str) -> str:
    normalized = " ".join(re.findall(r"[^\W_]+", value.casefold(), re.UNICODE))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _references(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return [item for item in parsed if isinstance(item, str)] if isinstance(parsed, list) else []


class RelationshipMemoryService:
    """Deterministic source-of-truth for episodes, rituals and bounded state."""

    def __init__(self, database: AsyncSession):
        self.database = database
        self.profiles = ProfileService(database)

    async def create_episode(self, candidate: EpisodeCandidate) -> RelationshipEpisode | None:
        if candidate.source_type not in {"explicit_user", "verified_app_event"}:
            return None
        if candidate.sensitivity != "low" or candidate.salience < MIN_EPISODE_SALIENCE:
            return None
        if candidate.source_type == "verified_app_event" and not (
            candidate.entity_type and candidate.entity_id
        ):
            return None

        profile = await self.profiles.get_or_create_default(commit=False)
        existing_rows = list((await self.database.execute(
            select(RelationshipEpisode).where(RelationshipEpisode.profile_id == profile.id)
        )).scalars().all())
        for existing in existing_rows:
            if candidate.source_reference in _references(existing.source_references_json):
                return existing

        consolidation_key = _normalized_key(candidate.summary)
        consolidated = next(
            (
                episode for episode in existing_rows
                if episode.consolidation_key == consolidation_key
                and episode.kind.value == candidate.kind
            ),
            None,
        )
        now = datetime.utcnow()
        if consolidated is not None:
            # Never reactivate suppressed data. A matching new source is retained
            # only when the episode is still active.
            if consolidated.status != RelationshipMemoryStatus.ACTIVE:
                return consolidated
            refs = _references(consolidated.source_references_json)
            refs.append(candidate.source_reference)
            consolidated.source_references_json = json.dumps(refs, ensure_ascii=False)
            consolidated.salience = max(consolidated.salience, candidate.salience)
            consolidated.confidence = max(consolidated.confidence, candidate.confidence)
            consolidated.updated_at = now
            await self._apply_state_event(profile.id, candidate.kind, now)
            await self.database.commit()
            await self.database.refresh(consolidated)
            return consolidated

        episode = RelationshipEpisode(
            id=str(uuid4()),
            profile_id=profile.id,
            kind=RelationshipEpisodeKind(candidate.kind),
            summary=candidate.summary,
            source_type=MemorySource(candidate.source_type),
            source_reference=candidate.source_reference,
            source_references_json=json.dumps([candidate.source_reference], ensure_ascii=False),
            entity_type=candidate.entity_type,
            entity_id=candidate.entity_id,
            salience=candidate.salience,
            confidence=candidate.confidence,
            emotional_tone=candidate.emotional_tone,
            sensitivity=MemorySensitivity.LOW,
            scope=candidate.scope,
            status=RelationshipMemoryStatus.ACTIVE,
            consolidation_key=consolidation_key,
        )
        self.database.add(episode)
        await self._apply_state_event(profile.id, candidate.kind, now)
        await self.database.commit()
        await self.database.refresh(episode)
        return episode

    async def capture_milestone(
        self,
        *,
        summary: str,
        entity_type: str,
        entity_id: str,
        source_reference: str,
    ) -> RelationshipEpisode | None:
        from app.services.memory_extractor import personalization_feature_enabled

        if not personalization_feature_enabled():
            return None
        profile = await self.profiles.get_or_create_default()
        if not profile.memory_prompts_on:
            return None
        return await self.create_episode(EpisodeCandidate(
            kind="milestone",
            summary=summary,
            source_type="verified_app_event",
            source_reference=source_reference,
            entity_type=entity_type,
            entity_id=entity_id,
            salience=0.9,
            confidence=1.0,
            emotional_tone="positive",
        ))

    async def create_ritual(self, candidate: RitualCandidate) -> SharedRitual | None:
        # Repetition alone never activates a ritual in P1-C; explicit agreement
        # is required, preventing an inferred routine from becoming relationship fact.
        if not candidate.explicitly_confirmed:
            return None
        profile = await self.profiles.get_or_create_default(commit=False)
        ritual_key = _normalized_key(candidate.description)
        ritual = (await self.database.execute(
            select(SharedRitual).where(
                SharedRitual.profile_id == profile.id,
                SharedRitual.ritual_key == ritual_key,
            )
        )).scalar_one_or_none()
        if ritual is not None:
            refs = _references(ritual.source_references_json)
            if candidate.source_reference in refs or ritual.status != RelationshipMemoryStatus.ACTIVE:
                return ritual
            refs.append(candidate.source_reference)
            ritual.source_references_json = json.dumps(refs, ensure_ascii=False)
            ritual.evidence_count += 1
            ritual.confidence = max(ritual.confidence, candidate.confidence)
            ritual.updated_at = datetime.utcnow()
            await self.database.commit()
            await self.database.refresh(ritual)
            return ritual

        ritual = SharedRitual(
            id=str(uuid4()),
            profile_id=profile.id,
            ritual_key=ritual_key,
            label=candidate.label,
            description=candidate.description,
            source_type=MemorySource.EXPLICIT_USER,
            source_references_json=json.dumps([candidate.source_reference], ensure_ascii=False),
            confidence=candidate.confidence,
            evidence_count=1,
            explicitly_confirmed=True,
            scope=candidate.scope,
            status=RelationshipMemoryStatus.ACTIVE,
        )
        self.database.add(ritual)
        await self.database.commit()
        await self.database.refresh(ritual)
        return ritual

    async def list_episodes(self, *, include_archived: bool = False) -> list[RelationshipEpisode]:
        profile = await self.profiles.get_or_create_default()
        await self._archive_stale_low_salience(profile.id, datetime.utcnow())
        query = select(RelationshipEpisode).where(RelationshipEpisode.profile_id == profile.id)
        if not include_archived:
            query = query.where(RelationshipEpisode.status == RelationshipMemoryStatus.ACTIVE)
        result = await self.database.execute(
            query.order_by(RelationshipEpisode.salience.desc(), RelationshipEpisode.updated_at.desc())
        )
        return list(result.scalars().all())

    async def list_rituals(self, *, include_archived: bool = False) -> list[SharedRitual]:
        profile = await self.profiles.get_or_create_default()
        query = select(SharedRitual).where(SharedRitual.profile_id == profile.id)
        if not include_archived:
            query = query.where(SharedRitual.status == RelationshipMemoryStatus.ACTIVE)
        result = await self.database.execute(query.order_by(SharedRitual.updated_at.desc()))
        return list(result.scalars().all())

    async def set_episode_status(
        self, episode_id: str, operation: str, source_reference: str | None = None
    ) -> RelationshipEpisode:
        episode = await self.database.get(RelationshipEpisode, episode_id)
        if episode is None or episode.status != RelationshipMemoryStatus.ACTIVE:
            raise RelationshipMemoryNotFoundError("Active episode was not found")
        episode.status = RelationshipMemoryStatus(operation)
        episode.updated_at = datetime.utcnow()
        self.database.add(RelationshipMemoryAudit(
            id=str(uuid4()), profile_id=episode.profile_id, target_type="episode",
            target_id=episode.id, operation=operation, source_reference=source_reference,
        ))
        await self._rebuild_state(episode.profile_id, datetime.utcnow())
        await self.database.commit()
        await self.database.refresh(episode)
        return episode

    async def set_ritual_status(
        self, ritual_id: str, operation: str, source_reference: str | None = None
    ) -> SharedRitual:
        ritual = await self.database.get(SharedRitual, ritual_id)
        if ritual is None or ritual.status != RelationshipMemoryStatus.ACTIVE:
            raise RelationshipMemoryNotFoundError("Active ritual was not found")
        ritual.status = RelationshipMemoryStatus(operation)
        ritual.updated_at = datetime.utcnow()
        self.database.add(RelationshipMemoryAudit(
            id=str(uuid4()), profile_id=ritual.profile_id, target_type="ritual",
            target_id=ritual.id, operation=operation, source_reference=source_reference,
        ))
        await self.database.commit()
        await self.database.refresh(ritual)
        return ritual

    async def retrieve(self, message: str, limit: int = 4) -> list[RelationshipEpisode]:
        profile = await self.profiles.get_or_create_default()
        profile_id = profile.id
        await self._archive_stale_low_salience(profile_id, datetime.utcnow())
        tokens = [
            token.casefold() for token in _SAFE_TOKEN.findall(message)
            if token.casefold() not in _STOP_WORDS
        ][:12]
        candidate_ids: list[str] = []
        if tokens:
            fts_query = " OR ".join(f'"{token}"' for token in tokens)
            try:
                rows = (await self.database.execute(text(
                    "SELECT episode_id FROM relationship_episode_fts "
                    "WHERE relationship_episode_fts MATCH :query AND profile_id = :profile_id "
                    "ORDER BY bm25(relationship_episode_fts) LIMIT 24"
                ), {"query": fts_query, "profile_id": profile_id})).fetchall()
                candidate_ids = [row[0] for row in rows]
            except Exception:
                await self.database.rollback()

        query = select(RelationshipEpisode).where(
            RelationshipEpisode.profile_id == profile_id,
            RelationshipEpisode.status == RelationshipMemoryStatus.ACTIVE,
            RelationshipEpisode.sensitivity == MemorySensitivity.LOW,
        )
        if candidate_ids:
            query = query.where(RelationshipEpisode.id.in_(candidate_ids))
        episodes = list((await self.database.execute(query)).scalars().all())
        now = datetime.utcnow()

        def score(episode: RelationshipEpisode) -> float:
            summary_tokens = {token.casefold() for token in _SAFE_TOKEN.findall(episode.summary)}
            relevance = sum(token in summary_tokens for token in tokens) / max(1, len(set(tokens)))
            days = max(0.0, (now - episode.updated_at).total_seconds() / 86400)
            recency = math.exp(-days / 120)
            explicitness = 1.0 if episode.source_type == MemorySource.EXPLICIT_USER else 0.9
            return 0.45 * relevance + 0.35 * episode.salience + 0.12 * recency + 0.08 * explicitness

        ranked = sorted(episodes, key=score, reverse=True)
        # A non-empty unrelated query must not surface an arbitrary old memory.
        if tokens:
            ranked = [episode for episode in ranked if any(
                token in {word.casefold() for word in _SAFE_TOKEN.findall(episode.summary)}
                for token in tokens
            )]
        return ranked[: max(0, min(limit, 8))]

    async def get_relational_state(self) -> RelationalState:
        profile = await self.profiles.get_or_create_default(commit=False)
        state = await self.database.get(RelationalState, profile.id)
        if state is None:
            state = RelationalState(profile_id=profile.id, rule_version=RELATIONSHIP_RULE_VERSION)
            self.database.add(state)
            await self.database.commit()
            await self.database.refresh(state)
            return state
        self._apply_decay(state, datetime.utcnow())
        await self.database.commit()
        await self.database.refresh(state)
        return state

    async def _apply_state_event(self, profile_id: str, kind: str, now: datetime) -> None:
        state = await self.database.get(RelationalState, profile_id)
        if state is None:
            state = RelationalState(profile_id=profile_id, rule_version=RELATIONSHIP_RULE_VERSION)
            self.database.add(state)
            await self.database.flush()
        self._apply_decay(state, now)
        deltas = self._state_delta(kind)
        for field, delta in zip(
            ("familiarity", "warmth", "playfulness", "concern", "pride"), deltas
        ):
            setattr(state, field, min(1.0, max(0.0, getattr(state, field) + delta)))
        state.evidence_count += 1
        state.last_event_at = now
        state.updated_at = now

    async def _rebuild_state(self, profile_id: str, now: datetime) -> None:
        state = await self.database.get(RelationalState, profile_id)
        if state is None:
            state = RelationalState(profile_id=profile_id, rule_version=RELATIONSHIP_RULE_VERSION)
            self.database.add(state)
            await self.database.flush()
        episodes = list((await self.database.execute(
            select(RelationshipEpisode).where(
                RelationshipEpisode.profile_id == profile_id,
                RelationshipEpisode.status == RelationshipMemoryStatus.ACTIVE,
            )
        )).scalars().all())
        baselines = {"familiarity": 0.1, "warmth": 0.4, "playfulness": 0.25, "concern": 0.0, "pride": 0.0}
        for field, baseline in baselines.items():
            setattr(state, field, baseline)
        state.evidence_count = 0
        state.last_event_at = None
        for episode in episodes:
            days = max(0.0, (now - episode.updated_at).total_seconds() / 86400)
            retention = 0.5 ** (days / 180)
            evidence_count = max(1, len(_references(episode.source_references_json)))
            for field, delta in zip(
                ("familiarity", "warmth", "playfulness", "concern", "pride"),
                self._state_delta(episode.kind.value),
            ):
                value = getattr(state, field) + delta * retention * evidence_count
                setattr(state, field, min(1.0, max(0.0, value)))
            state.evidence_count += evidence_count
            if state.last_event_at is None or episode.updated_at > state.last_event_at:
                state.last_event_at = episode.updated_at
        state.rule_version = RELATIONSHIP_RULE_VERSION
        state.updated_at = now

    async def _archive_stale_low_salience(self, profile_id: str, now: datetime) -> None:
        cutoff = now - timedelta(days=LOW_SALIENCE_ARCHIVE_DAYS)
        episodes = list((await self.database.execute(
            select(RelationshipEpisode).where(
                RelationshipEpisode.profile_id == profile_id,
                RelationshipEpisode.status == RelationshipMemoryStatus.ACTIVE,
                RelationshipEpisode.kind != RelationshipEpisodeKind.MILESTONE,
                RelationshipEpisode.salience < 0.75,
                RelationshipEpisode.updated_at < cutoff,
            )
        )).scalars().all())
        if not episodes:
            return
        for episode in episodes:
            episode.status = RelationshipMemoryStatus.ARCHIVED
            self.database.add(RelationshipMemoryAudit(
                id=str(uuid4()),
                profile_id=profile_id,
                target_type="episode",
                target_id=episode.id,
                operation="archived",
                source_reference=f"policy:{RELATIONSHIP_RULE_VERSION}",
            ))
        await self._rebuild_state(profile_id, now)
        await self.database.commit()

    @staticmethod
    def _state_delta(kind: str) -> tuple[float, float, float, float, float]:
        return {
            "milestone": (0.04, 0.02, 0.0, 0.0, 0.08),
            "recovery": (0.04, 0.04, 0.0, 0.03, 0.04),
            "shared_event": (0.03, 0.03, 0.01, 0.0, 0.0),
            "important_correction": (0.01, 0.0, -0.02, 0.0, 0.0),
        }[kind]

    @staticmethod
    def _apply_decay(state: RelationalState, now: datetime) -> None:
        if not state.updated_at:
            return
        days = max(0.0, (now - state.updated_at).total_seconds() / 86400)
        if days < 1:
            return
        retention = 0.5 ** (days / 180)
        baselines = {"familiarity": 0.1, "warmth": 0.4, "playfulness": 0.25, "concern": 0.0, "pride": 0.0}
        for field, baseline in baselines.items():
            value = baseline + (getattr(state, field) - baseline) * retention
            setattr(state, field, min(1.0, max(0.0, value)))
        state.updated_at = now

    async def delete_all(self, profile_id: str) -> None:
        await self.database.execute(delete(RelationshipMemoryAudit).where(
            RelationshipMemoryAudit.profile_id == profile_id
        ))
        await self.database.execute(delete(RelationshipEpisode).where(
            RelationshipEpisode.profile_id == profile_id
        ))
        await self.database.execute(delete(SharedRitual).where(
            SharedRitual.profile_id == profile_id
        ))
        await self.database.execute(delete(RelationalState).where(
            RelationalState.profile_id == profile_id
        ))

    @staticmethod
    def serialize_episode(episode: RelationshipEpisode) -> dict[str, Any]:
        return {
            "id": episode.id,
            "kind": episode.kind.value,
            "summary": episode.summary,
            "source_type": episode.source_type.value,
            "source_reference": episode.source_reference,
            "source_references": _references(episode.source_references_json),
            "entity_type": episode.entity_type,
            "entity_id": episode.entity_id,
            "salience": episode.salience,
            "confidence": episode.confidence,
            "emotional_tone": episode.emotional_tone,
            "status": episode.status.value,
            "created_at": episode.created_at.isoformat() if episode.created_at else None,
            "updated_at": episode.updated_at.isoformat() if episode.updated_at else None,
        }

    @staticmethod
    def serialize_ritual(ritual: SharedRitual) -> dict[str, Any]:
        return {
            "id": ritual.id,
            "label": ritual.label,
            "description": ritual.description,
            "source_type": ritual.source_type.value,
            "source_references": _references(ritual.source_references_json),
            "confidence": ritual.confidence,
            "evidence_count": ritual.evidence_count,
            "explicitly_confirmed": ritual.explicitly_confirmed,
            "status": ritual.status.value,
            "created_at": ritual.created_at.isoformat() if ritual.created_at else None,
            "updated_at": ritual.updated_at.isoformat() if ritual.updated_at else None,
        }

    @staticmethod
    def serialize_state(state: RelationalState) -> dict[str, Any]:
        return {
            "familiarity": round(state.familiarity, 3),
            "warmth": round(state.warmth, 3),
            "playfulness": round(state.playfulness, 3),
            "concern": round(state.concern, 3),
            "pride": round(state.pride, 3),
            "rule_version": state.rule_version,
            "evidence_count": state.evidence_count,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        }
