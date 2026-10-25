from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


MemoryKey = Literal[
    "preferred_name",
    "preferred_address",
    "communication_style",
    "explicit_focus_duration",
    "like",
    "dislike",
    "productivity_preference",
]
MemoryAction = Literal["deactivated", "deleted", "never_mention"]


KEY_KINDS: dict[str, str] = {
    "preferred_name": "identity",
    "preferred_address": "identity",
    "communication_style": "communication",
    "explicit_focus_duration": "productivity",
    "like": "interest",
    "dislike": "interest",
    "productivity_preference": "productivity",
}


class MemoryCandidate(BaseModel):
    key: MemoryKey
    value: str | int
    kind: str | None = None
    scope: str = "global"
    confidence: float = Field(default=1.0, ge=0, le=1)
    source_type: Literal["explicit_user", "agent_suggestion"] = "explicit_user"
    sensitivity: Literal["low", "sensitive"] = "low"

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        if value != "global":
            raise ValueError("P1-A only supports global memory scope")
        return value


class MemoryEditRequest(BaseModel):
    value: Any


class MemoryActionRequest(BaseModel):
    action: MemoryAction = "deactivate"


class ProfileUpdateRequest(BaseModel):
    personalization_on: bool | None = None
    memory_prompts_on: bool | None = None
    relationship_context_on: bool | None = None
    proactive_enabled: bool | None = None
    proactive_jokes_on: bool | None = None
    proactive_planning_on: bool | None = None

    @field_validator(
        "personalization_on",
        "memory_prompts_on",
        "relationship_context_on",
        "proactive_enabled",
        "proactive_jokes_on",
        "proactive_planning_on",
    )
    @classmethod
    def reject_null_updates(cls, value: bool | None) -> bool | None:
        return value


def validate_memory_value(key: str, value: Any) -> str | int:
    if key not in KEY_KINDS:
        raise ValueError("Unsupported memory key")
    if key == "explicit_focus_duration":
        if isinstance(value, bool) or not isinstance(value, int) or not 5 <= value <= 240:
            raise ValueError("Focus duration must be an integer from 5 to 240 minutes")
        return value
    if not isinstance(value, str):
        raise ValueError("Memory value must be text")
    normalized = " ".join(value.strip().split())
    maximum = 80 if key in {"preferred_name", "preferred_address"} else 300
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"Memory value must contain 1 to {maximum} characters")
    if key == "communication_style" and normalized not in {
        "concise",
        "detailed",
        "gentle",
        "direct",
        "encouraging",
    }:
        raise ValueError("Unsupported communication style")
    return normalized
