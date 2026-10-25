from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import get_db
from app.services.session_service import SessionService
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

router = APIRouter()

class SessionStart(BaseModel):
    task_id: str
    duration: int = Field(ge=60, le=4 * 60 * 60)  # in seconds
    source: Literal["ui", "chat", "suggestion"] = "ui"
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)
    action_context: dict | None = None

class TimeUpdate(BaseModel):
    time_left: int = Field(ge=0)


class ActionMetadata(BaseModel):
    source: Literal["ui", "chat", "suggestion"] = "ui"
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)


class AutomaticDistractionCreate(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    source: Literal["app_switch", "idle"]
    application: str | None = Field(default=None, max_length=120)
    confidence: float = Field(ge=0, le=1)
    started_at: datetime


class AutomaticDistractionFinish(BaseModel):
    ended_at: datetime


def require_success(result: dict | None, status_code: int = 409):
    if not result or "error" in result:
        detail = result.get("error", "No active session") if result else "No active session"
        raise HTTPException(status_code=status_code, detail=detail)
    return result

@router.post("/start")
async def start_session(data: SessionStart, db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    result = await service.start_session(
        data.task_id,
        data.duration,
        source=data.source,
        idempotency_key=data.idempotency_key,
        action_context=data.action_context,
    )
    status_code = 404 if result.get("error") == "Task not found" else 409
    return require_success(result, status_code=status_code)

@router.post("/pause")
async def pause_session(db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    return require_success(await service.pause_session())

@router.post("/resume")
async def resume_session(db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    return require_success(await service.resume_session())

@router.post("/cancel")
async def cancel_session(
    data: ActionMetadata | None = None,
    db: AsyncSession = Depends(get_db),
):
    service = SessionService(db)
    metadata = data or ActionMetadata()
    return require_success(await service.cancel_session(
        source=metadata.source, idempotency_key=metadata.idempotency_key,
    ))

@router.post("/complete")
async def complete_session(db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    return require_success(await service.complete_session())

class ExtendRequest(BaseModel):
    minutes: int = Field(ge=1, le=120)
    source: Literal["ui", "chat", "suggestion"] = "ui"
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)

@router.post("/extend")
async def extend_session(data: ExtendRequest, db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    return require_success(await service.extend_session(
        data.minutes * 60,
        source=data.source,
        idempotency_key=data.idempotency_key,
    ))

@router.post("/distraction")
async def add_distraction(db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    return require_success(await service.add_distraction())


@router.post("/distraction/automatic")
async def add_automatic_distraction(
    data: AutomaticDistractionCreate,
    db: AsyncSession = Depends(get_db),
):
    service = SessionService(db)
    return require_success(await service.add_automatic_distraction(**data.model_dump()))


@router.patch("/distraction/{event_id}")
async def finish_automatic_distraction(
    event_id: str,
    data: AutomaticDistractionFinish,
    db: AsyncSession = Depends(get_db),
):
    service = SessionService(db)
    result = await service.finish_automatic_distraction(event_id, data.ended_at)
    status_code = 404 if result.get("error") == "Distraction event not found" else 409
    return require_success(result, status_code=status_code)

@router.post("/update-time")
async def update_time_left(data: TimeUpdate, db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    return require_success(await service.update_time_left(data.time_left))

@router.get("/current")
async def get_current_session(db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    return await service.get_current_session()
