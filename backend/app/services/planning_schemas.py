from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class PlannerRequest(BaseModel):
    provider: Literal["openai", "gemini"] = "openai"
    current_state: str = Field(default="", max_length=2000)
    weaknesses: list[str] = Field(default_factory=list, max_length=30)
    topics: list[str] = Field(default_factory=list, max_length=100)
    available_weekdays: list[int] = Field(min_length=1, max_length=7)
    minutes_per_day: int = Field(ge=5, le=720)
    default_session_duration: int = Field(default=25, ge=5, le=120)

    @field_validator("available_weekdays")
    @classmethod
    def weekdays_are_unique(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value) or len(set(value)) != len(value):
            raise ValueError("available_weekdays must contain unique values from 0 to 6")
        return sorted(value)


class DraftItem(BaseModel):
    client_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    parent_client_id: str | None = Field(default=None, max_length=80)
    horizon: Literal["month", "week", "day"]
    title: str = Field(min_length=1, max_length=200)
    period_start: str | None = None
    planned_for: str | None = None
    estimate_minutes: int | None = Field(default=None, ge=5, le=120)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value

    @field_validator("period_start", "planned_for")
    @classmethod
    def valid_dates(cls, value: str | None) -> str | None:
        if value is not None:
            date.fromisoformat(value)
        return value


class PlannerBranchPayload(BaseModel):
    assumptions: list[str] = Field(default_factory=list, max_length=15)
    items: list[DraftItem] = Field(min_length=1, max_length=60)

    @model_validator(mode="after")
    def unique_client_ids(self):
        if len({item.client_id for item in self.items}) != len(self.items):
            raise ValueError("Branch client IDs must be unique")
        return self


class PlannerDraftPayload(BaseModel):
    schema_version: Literal[1] = 1
    assumptions: list[str] = Field(default_factory=list, max_length=30)
    items: list[DraftItem] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def valid_hierarchy(self):
        by_id = {item.client_id: item for item in self.items}
        if len(by_id) != len(self.items):
            raise ValueError("Draft client IDs must be unique")
        for item in self.items:
            if item.horizon == "month":
                if item.parent_client_id or not item.period_start or item.planned_for:
                    raise ValueError("Monthly items require period_start and no parent/planned_for")
                if date.fromisoformat(item.period_start).day != 1:
                    raise ValueError("Monthly period_start must be the first day")
            elif item.horizon == "week":
                parent = by_id.get(item.parent_client_id or "")
                if not parent or parent.horizon != "month" or not item.period_start or item.planned_for:
                    raise ValueError("Weekly items require a monthly parent and period_start")
                if date.fromisoformat(item.period_start).weekday() != 0:
                    raise ValueError("Weekly period_start must be Monday")
            else:
                parent = by_id.get(item.parent_client_id or "")
                if not parent or parent.horizon != "week" or not item.planned_for or item.period_start:
                    raise ValueError("Daily items require a weekly parent and planned_for")
                if item.estimate_minutes is None:
                    raise ValueError("Daily items require estimate_minutes")
                week_start = date.fromisoformat(parent.period_start)
                planned = date.fromisoformat(item.planned_for)
                if not week_start <= planned <= week_start + timedelta(days=6):
                    raise ValueError("Daily item must fall within its parent week")
            if item.horizon != "day" and item.estimate_minutes is not None:
                raise ValueError("Only daily items can have estimate_minutes")
        return self


class CapacitySummary(BaseModel):
    available_minutes: int
    planning_limit_minutes: int
    planned_minutes: int
    over_capacity: bool


class PlanDraftResponse(BaseModel):
    id: str
    goal_id: str
    goal_version: int
    status: Literal["draft", "approved", "cancelled"]
    input: PlannerRequest
    draft: PlannerDraftPayload
    capacity: CapacitySummary
    approval_result: dict | None = None


class DraftUpdateRequest(BaseModel):
    draft: PlannerDraftPayload


class DraftRegenerateRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    draft: PlannerDraftPayload | None = None


class DraftApprovalRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    override_capacity: bool = False
    draft: PlannerDraftPayload | None = None
