from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import UserProfile


class ProfileService:
    """Owns the stable single-user profile stored in the business database."""

    def __init__(self, database: AsyncSession):
        self.database = database

    async def get_or_create_default(self, *, commit: bool = True) -> UserProfile:
        profile = (
            await self.database.execute(
                select(UserProfile)
                .order_by(UserProfile.created_at.asc(), UserProfile.id.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if profile is not None:
            return profile
        profile = UserProfile(id=str(uuid4()))
        self.database.add(profile)
        await self.database.flush()
        if commit:
            await self.database.commit()
            await self.database.refresh(profile)
        return profile

    async def update_default(self, changes: dict[str, bool]) -> UserProfile:
        profile = await self.get_or_create_default(commit=False)
        for field in (
            "personalization_on",
            "memory_prompts_on",
            "relationship_context_on",
            "proactive_enabled",
            "proactive_jokes_on",
            "proactive_planning_on",
        ):
            if field in changes and changes[field] is not None:
                setattr(profile, field, changes[field])
        profile.updated_at = datetime.utcnow()
        await self.database.commit()
        await self.database.refresh(profile)
        return profile

    @staticmethod
    def serialize(profile: UserProfile) -> dict:
        return {
            "id": profile.id,
            "display_name": profile.display_name,
            "personalization_on": profile.personalization_on,
            "memory_prompts_on": profile.memory_prompts_on,
            "relationship_context_on": profile.relationship_context_on,
            "proactive_enabled": profile.proactive_enabled,
            "proactive_jokes_on": profile.proactive_jokes_on,
            "proactive_planning_on": profile.proactive_planning_on,
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
        }
