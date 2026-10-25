from datetime import date
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db
from app.models.models import PlanHorizon, PlanItemStatus, Priority
from app.services.planning_service import (
    PlanningConflictError,
    PlanningError,
    PlanningNotFoundError,
    PlanningService,
)
from app.services.ai_service import ProviderError
from app.services.planner_service import PlannerService
from app.services.planning_schemas import (
    DraftApprovalRequest,
    DraftRegenerateRequest,
    DraftUpdateRequest,
    PlannerRequest,
)
from app.utils.logger import app_logger


router = APIRouter()


def _clean_required(value: str, field: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{field} must not be blank")
    return value


def _validate_iso_date(value: Optional[str], field: str) -> Optional[str]:
    if value in (None, ""):
        return None if value is None else value
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO date") from error
    return value


class GoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    definition_of_done: str = Field(min_length=1, max_length=2000)
    deadline: str
    importance: Priority = Priority.MEDIUM
    weekly_capacity_minutes: int = Field(default=0, ge=0, le=7 * 24 * 60)

    @field_validator("title", "definition_of_done")
    @classmethod
    def required_text(cls, value: str, info) -> str:
        return _clean_required(value, info.field_name)

    @field_validator("deadline")
    @classmethod
    def valid_deadline(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("deadline must not be blank")
        return _validate_iso_date(value, "deadline") or ""


class GoalUpdate(BaseModel):
    title: str = Field(default=None, min_length=1, max_length=200)
    definition_of_done: str = Field(default=None, min_length=1, max_length=2000)
    deadline: str = None
    importance: Priority = None
    weekly_capacity_minutes: int = Field(
        default=None, ge=0, le=7 * 24 * 60
    )
    expected_version: Optional[int] = Field(default=None, ge=1)

    @field_validator("title", "definition_of_done")
    @classmethod
    def optional_text(cls, value: str, info) -> str:
        return _clean_required(value, info.field_name)

    @field_validator("deadline")
    @classmethod
    def valid_deadline(cls, value: str) -> str:
        return _validate_iso_date(value, "deadline")


class VersionRequest(BaseModel):
    expected_version: Optional[int] = Field(default=None, ge=1)
    source: Literal["ui", "chat", "suggestion"] = "ui"
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)
    action_context: dict | None = None


class GoalDeleteRequest(VersionRequest):
    confirm_delete: bool


class PlanItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    horizon: PlanHorizon
    goal_id: Optional[str] = None
    parent_id: Optional[str] = None
    importance: Priority = Priority.MEDIUM
    deadline: Optional[str] = None
    planned_for: Optional[str] = None
    period_start: Optional[str] = None
    estimate_minutes: Optional[int] = Field(default=None, ge=5, le=120)

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _clean_required(value, "title")

    @field_validator("deadline", "planned_for", "period_start")
    @classmethod
    def valid_dates(cls, value: Optional[str], info) -> Optional[str]:
        return _validate_iso_date(value, info.field_name)


class PlanItemUpdate(BaseModel):
    title: str = Field(default=None, min_length=1, max_length=200)
    horizon: PlanHorizon = None
    goal_id: Optional[str] = None
    parent_id: Optional[str] = None
    importance: Priority = None
    deadline: Optional[str] = None
    planned_for: Optional[str] = None
    period_start: Optional[str] = None
    estimate_minutes: Optional[int] = Field(default=None, ge=5, le=120)
    expected_version: Optional[int] = Field(default=None, ge=1)

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _clean_required(value, "title")

    @field_validator("deadline", "planned_for", "period_start")
    @classmethod
    def valid_dates(cls, value: Optional[str], info) -> Optional[str]:
        return _validate_iso_date(value, info.field_name)


class RescheduleRequest(VersionRequest):
    planned_for: str

    @field_validator("planned_for")
    @classmethod
    def valid_planned_for(cls, value: str) -> str:
        return _validate_iso_date(value, "planned_for") or ""


def _raise_http(error: PlanningError):
    if isinstance(error, PlanningNotFoundError):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, PlanningConflictError):
        raise HTTPException(status_code=409, detail=str(error)) from error
    raise HTTPException(status_code=422, detail=str(error)) from error


async def _run(operation):
    try:
        return await operation
    except PlanningError as error:
        _raise_http(error)


async def _run_planner(operation, request_id: str):
    try:
        return await operation
    except PlanningError as error:
        if isinstance(error, PlanningNotFoundError):
            status_code, error_code = 404, "PLANNER_NOT_FOUND"
        elif isinstance(error, PlanningConflictError):
            status_code, error_code = 409, "PLANNER_CONFLICT"
        else:
            status_code, error_code = 422, "AI_DRAFT_INVALID"
        app_logger.warning(
            "ai_planner_rejected request_id=%s error_code=%s status=%s reason=%s",
            request_id,
            error_code,
            status_code,
            str(error),
        )
        return JSONResponse(
            status_code=status_code,
            content={
                "status": "error",
                "message": str(error),
                "error_code": error_code,
                "request_id": request_id,
            },
        )
    except ProviderError as error:
        app_logger.warning(
            "ai_planner_rejected request_id=%s error_code=PROVIDER_UNAVAILABLE status=503",
            request_id,
        )
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": str(error),
                "error_code": "PROVIDER_UNAVAILABLE",
                "request_id": request_id,
            },
        )


@router.get("/goals")
async def list_goals(
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
):
    return await PlanningService(db).list_goals(include_archived)


@router.post("/goals", status_code=201)
async def create_goal(goal: GoalCreate, db: AsyncSession = Depends(get_db)):
    return await _run(PlanningService(db).create_goal(goal.model_dump()))


@router.get("/goals/{goal_id}")
async def get_goal(goal_id: str, db: AsyncSession = Depends(get_db)):
    return await _run(PlanningService(db).get_goal(goal_id))


@router.patch("/goals/{goal_id}")
async def update_goal(
    goal_id: str,
    update: GoalUpdate,
    db: AsyncSession = Depends(get_db),
):
    data = update.model_dump(exclude_unset=True)
    expected_version = data.pop("expected_version", None)
    return await _run(
        PlanningService(db).update_goal(goal_id, data, expected_version)
    )


@router.post("/goals/{goal_id}/complete")
async def complete_goal(
    goal_id: str,
    request: VersionRequest,
    db: AsyncSession = Depends(get_db),
):
    return await _run(
        PlanningService(db).complete_goal(goal_id, request.expected_version)
    )


@router.post("/goals/{goal_id}/archive")
async def archive_goal(
    goal_id: str,
    request: VersionRequest,
    db: AsyncSession = Depends(get_db),
):
    return await _run(
        PlanningService(db).archive_goal(goal_id, request.expected_version)
    )


@router.delete("/goals/{goal_id}")
async def delete_goal(
    goal_id: str,
    request: GoalDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    if not request.confirm_delete:
        raise HTTPException(status_code=422, detail="Explicit delete confirmation is required")
    return await _run(
        PlanningService(db).delete_goal(goal_id, request.expected_version)
    )


@router.get("/goals/{goal_id}/progress")
async def get_goal_progress(goal_id: str, db: AsyncSession = Depends(get_db)):
    return await _run(PlanningService(db).get_progress(goal_id=goal_id))


@router.post("/goals/{goal_id}/drafts", status_code=201)
async def generate_plan_draft(
    goal_id: str,
    request: PlannerRequest,
    db: AsyncSession = Depends(get_db),
):
    request_id = str(uuid4())
    service = PlannerService(db, request_id=request_id)
    return await _run_planner(service.generate(goal_id, request), request_id)


@router.get("/drafts/{draft_id}")
async def get_plan_draft(draft_id: str, db: AsyncSession = Depends(get_db)):
    return await _run(PlannerService(db).get(draft_id))


@router.patch("/drafts/{draft_id}")
async def update_plan_draft(
    draft_id: str,
    request: DraftUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    return await _run(PlannerService(db).update(draft_id, request.draft))


@router.post("/drafts/{draft_id}/cancel")
async def cancel_plan_draft(draft_id: str, db: AsyncSession = Depends(get_db)):
    return await _run(PlannerService(db).cancel(draft_id))


@router.post("/drafts/{draft_id}/regenerate")
async def regenerate_plan_draft_branch(
    draft_id: str,
    request: DraftRegenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    request_id = str(uuid4())
    service = PlannerService(db, request_id=request_id)
    return await _run_planner(
        service.regenerate_branch(draft_id, request),
        request_id,
    )


@router.post("/drafts/{draft_id}/approve")
async def approve_plan_draft(
    draft_id: str,
    request: DraftApprovalRequest,
    db: AsyncSession = Depends(get_db),
):
    return await _run(PlannerService(db).approve(draft_id, request))


@router.get("/plan-items")
async def list_plan_items(
    goal_id: Optional[str] = None,
    horizon: Optional[PlanHorizon] = None,
    status: Optional[PlanItemStatus] = None,
    inbox: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    return await PlanningService(db).list_plan_items(
        goal_id=goal_id,
        horizon=horizon,
        status=status,
        inbox=inbox,
    )


@router.post("/plan-items", status_code=201)
async def create_plan_item(
    item: PlanItemCreate,
    db: AsyncSession = Depends(get_db),
):
    return await _run(PlanningService(db).create_plan_item(item.model_dump()))


@router.get("/plan-items/{item_id}")
async def get_plan_item(item_id: str, db: AsyncSession = Depends(get_db)):
    return await _run(PlanningService(db).get_plan_item(item_id))


@router.patch("/plan-items/{item_id}")
async def update_plan_item(
    item_id: str,
    update: PlanItemUpdate,
    db: AsyncSession = Depends(get_db),
):
    data = update.model_dump(exclude_unset=True)
    expected_version = data.pop("expected_version", None)
    return await _run(
        PlanningService(db).update_plan_item(item_id, data, expected_version)
    )


@router.post("/plan-items/{item_id}/complete")
async def complete_plan_item(
    item_id: str,
    request: VersionRequest,
    db: AsyncSession = Depends(get_db),
):
    return await _run(
        PlanningService(db).complete_plan_item(
            item_id,
            request.expected_version,
            source=request.source,
            idempotency_key=request.idempotency_key,
            action_context=request.action_context,
        )
    )


@router.post("/plan-items/{item_id}/drop")
async def drop_plan_item(
    item_id: str,
    request: VersionRequest,
    db: AsyncSession = Depends(get_db),
):
    return await _run(
        PlanningService(db).drop_plan_item(item_id, request.expected_version)
    )


@router.post("/plan-items/{item_id}/inbox")
async def move_to_inbox(
    item_id: str,
    request: VersionRequest,
    db: AsyncSession = Depends(get_db),
):
    return await _run(
        PlanningService(db).move_to_inbox(item_id, request.expected_version)
    )


@router.post("/plan-items/{item_id}/reschedule")
async def reschedule_plan_item(
    item_id: str,
    request: RescheduleRequest,
    db: AsyncSession = Depends(get_db),
):
    return await _run(
        PlanningService(db).reschedule_plan_item(
            item_id,
            request.planned_for,
            request.expected_version,
        )
    )


@router.get("/plan-items/{item_id}/progress")
async def get_plan_item_progress(
    item_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await _run(PlanningService(db).get_progress(item_id=item_id))
