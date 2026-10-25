from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    MemoryCorrection,
    MemoryCorrectionOperation,
    MemorySensitivity,
    MemorySource,
    PersonalMemory,
    HabitProfile,
    UserActionEvent,
    UserProfile,
)
from app.services.personal_memory_schemas import KEY_KINDS, MemoryCandidate, validate_memory_value
from app.services.profile_service import ProfileService


class MemoryNotFoundError(LookupError):
    pass


class PersonalMemoryService:
    def __init__(self, database: AsyncSession):
        self.database = database
        self.profiles = ProfileService(database)

    async def list_active(self, profile_id: str | None = None) -> list[PersonalMemory]:
        profile = None
        if profile_id is None:
            profile = await self.profiles.get_or_create_default()
            profile_id = profile.id
        result = await self.database.execute(
            select(PersonalMemory)
            .where(
                PersonalMemory.profile_id == profile_id,
                PersonalMemory.active.is_(True),
            )
            .order_by(PersonalMemory.updated_at.desc())
        )
        return list(result.scalars().all())

    async def remember(
        self,
        candidate: MemoryCandidate,
        source_reference: str | None = None,
    ) -> PersonalMemory | None:
        # Suggestions are candidates only; P1-A never activates them.
        if candidate.source_type != "explicit_user" or candidate.sensitivity != "low":
            return None
        value = validate_memory_value(candidate.key, candidate.value)
        kind = KEY_KINDS[candidate.key]
        if candidate.kind is not None and candidate.kind != kind:
            raise ValueError("Memory kind does not match its key")

        profile = await self.profiles.get_or_create_default(commit=False)
        current = (
            await self.database.execute(
                select(PersonalMemory).where(
                    PersonalMemory.profile_id == profile.id,
                    PersonalMemory.kind == kind,
                    PersonalMemory.key == candidate.key,
                    PersonalMemory.scope == candidate.scope,
                    PersonalMemory.active.is_(True),
                )
            )
        ).scalar_one_or_none()
        encoded = json.dumps(value, ensure_ascii=False)
        now = datetime.utcnow()
        if current is not None and current.value_json == encoded:
            current.last_confirmed_at = now
            current.updated_at = now
            await self.database.commit()
            await self.database.refresh(current)
            return current

        new_memory = PersonalMemory(
            id=str(uuid4()),
            profile_id=profile.id,
            kind=kind,
            key=candidate.key,
            value_json=encoded,
            source_type=MemorySource.EXPLICIT_USER,
            source_reference=source_reference,
            confidence=1.0,
            sensitivity=MemorySensitivity.LOW,
            scope=candidate.scope,
            active=True,
            last_confirmed_at=now,
        )
        if current is not None:
            current.active = False
            current.superseded_by = new_memory.id
            current.updated_at = now
            self.database.add(
                MemoryCorrection(
                    id=str(uuid4()),
                    profile_id=profile.id,
                    memory_id=current.id,
                    operation=MemoryCorrectionOperation.CORRECTED,
                    source_reference=source_reference,
                )
            )
            await self.database.flush()
        self.database.add(new_memory)
        if candidate.key == "preferred_name":
            profile.display_name = str(value)
            profile.updated_at = now
        await self.database.commit()
        await self.database.refresh(new_memory)
        return new_memory

    async def update(self, memory_id: str, value: Any) -> PersonalMemory:
        current = await self._active_memory(memory_id)
        candidate = MemoryCandidate(
            key=current.key,
            value=validate_memory_value(current.key, value),
            kind=current.kind,
        )
        replacement = await self.remember(candidate, source_reference=f"memory:{memory_id}")
        if replacement is None:
            raise RuntimeError("Explicit memory update was not persisted")
        return replacement

    async def deactivate(
        self,
        memory_id: str,
        operation: str = "deactivated",
        source_reference: str | None = None,
    ) -> PersonalMemory:
        memory = await self._active_memory(memory_id)
        try:
            correction_operation = MemoryCorrectionOperation(operation)
        except ValueError as error:
            raise ValueError("Unsupported memory operation") from error
        if correction_operation == MemoryCorrectionOperation.CORRECTED:
            raise ValueError("Correction requires a replacement value")
        memory.active = False
        memory.updated_at = datetime.utcnow()
        self.database.add(
            MemoryCorrection(
                id=str(uuid4()),
                profile_id=memory.profile_id,
                memory_id=memory.id,
                operation=correction_operation,
                source_reference=source_reference,
            )
        )
        if memory.key == "preferred_name":
            profile = await self.database.get(UserProfile, memory.profile_id)
            if profile is not None:
                profile.display_name = None
                profile.updated_at = datetime.utcnow()
        await self.database.commit()
        await self.database.refresh(memory)
        return memory

    async def deactivate_key(
        self,
        key: str,
        operation: str,
        source_reference: str | None = None,
        expected_value: str | int | None = None,
    ) -> bool:
        if key not in KEY_KINDS:
            return False
        profile = await self.profiles.get_or_create_default()
        memory = (
            await self.database.execute(
                select(PersonalMemory).where(
                    PersonalMemory.profile_id == profile.id,
                    PersonalMemory.key == key,
                    PersonalMemory.active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if memory is None:
            return False
        if expected_value is not None and json.loads(memory.value_json) != expected_value:
            return False
        await self.deactivate(memory.id, operation, source_reference)
        return True

    async def delete_all(self) -> None:
        profile = await self.profiles.get_or_create_default(commit=False)
        from app.services.relationship_memory_service import RelationshipMemoryService
        from app.services.proactive_service import ProactiveService

        await RelationshipMemoryService(self.database).delete_all(profile.id)
        await ProactiveService.delete_history(self.database, profile.id)
        await self.database.execute(
            delete(MemoryCorrection).where(MemoryCorrection.profile_id == profile.id)
        )
        await self.database.execute(
            delete(PersonalMemory).where(PersonalMemory.profile_id == profile.id)
        )
        await self.database.execute(
            delete(HabitProfile).where(HabitProfile.profile_id == profile.id)
        )
        await self.database.execute(
            delete(UserActionEvent).where(UserActionEvent.profile_id == profile.id)
        )
        profile.display_name = None
        profile.relationship_context_on = False
        profile.updated_at = datetime.utcnow()
        await self.database.commit()

    async def _active_memory(self, memory_id: str) -> PersonalMemory:
        memory = await self.database.get(PersonalMemory, memory_id)
        if memory is None or not memory.active:
            raise MemoryNotFoundError("Active memory was not found")
        return memory

    @staticmethod
    def serialize(memory: PersonalMemory) -> dict[str, Any]:
        return {
            "id": memory.id,
            "profile_id": memory.profile_id,
            "kind": memory.kind,
            "key": memory.key,
            "value": json.loads(memory.value_json),
            "source_type": memory.source_type.value,
            "confidence": memory.confidence,
            "sensitivity": memory.sensitivity.value,
            "scope": memory.scope,
            "active": memory.active,
            "created_at": memory.created_at.isoformat() if memory.created_at else None,
            "updated_at": memory.updated_at.isoformat() if memory.updated_at else None,
            "last_confirmed_at": (
                memory.last_confirmed_at.isoformat() if memory.last_confirmed_at else None
            ),
        }
