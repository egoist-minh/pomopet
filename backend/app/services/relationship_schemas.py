from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class EpisodeCandidate(BaseModel):
    kind: Literal["milestone", "recovery", "shared_event", "important_correction"]
    summary: str = Field(min_length=1, max_length=300)
    source_type: Literal["explicit_user", "verified_app_event", "agent_suggestion"]
    source_reference: str = Field(min_length=1, max_length=200)
    entity_type: str | None = Field(default=None, max_length=40)
    entity_id: str | None = Field(default=None, max_length=128)
    salience: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    emotional_tone: Literal["positive", "neutral", "difficult"] | None = None
    sensitivity: Literal["low", "sensitive"] = "low"
    scope: str = "global"

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Episode summary cannot be blank")
        return normalized

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        if value != "global":
            raise ValueError("Only global relationship scope is supported")
        return value


class RitualCandidate(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=300)
    source_reference: str = Field(min_length=1, max_length=200)
    explicitly_confirmed: bool = False
    confidence: float = Field(default=1.0, ge=0, le=1)
    scope: str = "global"

    @field_validator("label", "description")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Ritual text cannot be blank")
        return normalized

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        if value != "global":
            raise ValueError("Only global relationship scope is supported")
        return value


class RelationshipActionRequest(BaseModel):
    action: Literal["archived", "deleted", "never_mention"] = "archived"
