from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db
from app.services.proactive_service import (
    ProactiveDecisionConflict,
    ProactiveDecisionNotFound,
    ProactiveService,
    utc_iso,
)


router = APIRouter()


class ProactiveEvaluateRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    trigger: str = Field(min_length=1, max_length=64)
    session_state: Literal["idle", "running", "paused", "break"]
    timezone_offset: int = Field(ge=-720, le=840)
    provider: Literal["openai", "gemini"] = "openai"
    thread_id: str | None = Field(
        default=None,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )


@router.post("/evaluate")
async def evaluate(
    request: ProactiveEvaluateRequest,
    database: AsyncSession = Depends(get_db),
):
    decision = await ProactiveService(database).evaluate(**request.model_dump())
    return ProactiveService.serialize(decision)


@router.post("/decisions/{decision_id}/executed")
async def mark_executed(
    decision_id: str,
    database: AsyncSession = Depends(get_db),
):
    try:
        decision = await ProactiveService(database).mark_executed(decision_id)
    except ProactiveDecisionNotFound:
        return JSONResponse(status_code=404, content={
            "status": "error", "message": "Decision not found", "error_code": "DECISION_NOT_FOUND"
        })
    except ProactiveDecisionConflict as error:
        return JSONResponse(status_code=409, content={
            "status": "error", "message": str(error), "error_code": "INVALID_DECISION_STATE"
        })
    return ProactiveService.serialize(decision)


@router.get("/runs")
async def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    database: AsyncSession = Depends(get_db),
):
    service = ProactiveService(database)
    return [service.serialize(item) for item in await service.list_runs(limit)]


@router.get("/runs/{decision_id}")
async def get_run(
    decision_id: str,
    database: AsyncSession = Depends(get_db),
):
    service = ProactiveService(database)
    try:
        decision, events = await service.get_run(decision_id)
    except ProactiveDecisionNotFound:
        return JSONResponse(status_code=404, content={
            "status": "error", "message": "Decision not found", "error_code": "DECISION_NOT_FOUND"
        })
    return {
        **service.serialize(decision),
        "state_snapshot": json.loads(decision.state_snapshot_json),
        "candidate_actions": json.loads(decision.candidate_actions_json),
        "trace": [{
            "sequence": event.sequence,
            "stage": event.stage,
            "details": json.loads(event.details_json),
            "created_at": utc_iso(event.created_at),
        } for event in events],
    }
