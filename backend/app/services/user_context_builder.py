from __future__ import annotations

import json
import re
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.memory_extractor import personalization_feature_enabled
from app.services.personal_memory_service import PersonalMemoryService
from app.services.profile_service import ProfileService
from app.services.relationship_memory_service import RelationshipMemoryService


class UserContextBuilder:
    MAX_MEMORIES = 12

    def __init__(self, database: AsyncSession):
        self.database = database

    @staticmethod
    def _relevant(memory, message: str) -> bool:
        if memory.key in {"preferred_name", "preferred_address", "communication_style"}:
            return True
        lowered = message.casefold()
        if re.search(r"\b(nhớ gì|remember|profile|preference|sở thích)\b", lowered):
            return True
        if memory.key == "explicit_focus_duration":
            return bool(re.search(r"\b(focus|pomodoro|session|tập trung|phút|minute)\b", lowered))
        if memory.key == "productivity_preference":
            return bool(re.search(r"\b(task|plan|focus|work|học|làm việc|kế hoạch)\b", lowered))
        value_tokens = {
            token for token in re.findall(r"\w{3,}", str(json.loads(memory.value_json)).casefold())
        }
        message_tokens = set(re.findall(r"\w{3,}", lowered))
        return bool(value_tokens & message_tokens)

    async def build(self, message: str = "") -> dict:
        if not personalization_feature_enabled():
            return {}
        profile = await ProfileService(self.database).get_or_create_default()
        if not profile.personalization_on:
            return {}
        memories = await PersonalMemoryService(self.database).list_active(profile.id)
        relevant = [memory for memory in memories if self._relevant(memory, message)]
        context = {
            "explicit_preferences": [
                {
                    "key": memory.key,
                    "value": json.loads(memory.value_json),
                    "source": memory.source_type.value,
                    "confidence": memory.confidence,
                }
                for memory in relevant[: self.MAX_MEMORIES]
            ]
        }
        # Separate opt-in: episodes, rituals, inferred habits and relational
        # state are never covered by the explicit-preference consent.
        if not profile.relationship_context_on:
            return context
        try:
            relationship = RelationshipMemoryService(self.database)
            episodes = await relationship.retrieve(message, limit=4)
            rituals = (await relationship.list_rituals())[:3]
            state = await relationship.get_relational_state()
            context["relationship_context"] = {
                "shared_episodes": [
                    {
                        "kind": episode.kind.value,
                        "summary": episode.summary,
                        "confidence": episode.confidence,
                    }
                    for episode in episodes
                ],
                "confirmed_rituals": [
                    {
                        "label": ritual.label,
                        "description": ritual.description,
                        "confidence": ritual.confidence,
                    }
                    for ritual in rituals
                ],
                "expression_state": RelationshipMemoryService.serialize_state(state),
                "expression_policy": {
                    "facts_require_retrieved_evidence": True,
                    "current_instruction_overrides": True,
                    "explicit_preferences_override_state": True,
                    "forbidden": ["guilt", "loneliness", "jealousy", "dependency", "biological_emotion_claims"],
                },
            }
        except Exception:
            await self.database.rollback()
        return context
