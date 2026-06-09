from fastapi import APIRouter, Depends, Body
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import get_db
from app.services.session_service import SessionService
from pydantic import BaseModel

router = APIRouter()

class SessionStart(BaseModel):
    task_id: str
    duration: int  # in seconds

class TimeUpdate(BaseModel):
    time_left: int

@router.post("/start")
async def start_session(data: SessionStart, db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    return await service.start_session(data.task_id, data.duration)

@router.post("/pause")
async def pause_session(db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    return await service.pause_session()

@router.post("/resume")
async def resume_session(db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    return await service.resume_session()

@router.post("/cancel")
async def cancel_session(db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    return await service.cancel_session()

@router.post("/complete")
async def complete_session(db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    return await service.complete_session()

class ExtendRequest(BaseModel):
    minutes: int

@router.post("/extend")
async def extend_session(data: ExtendRequest, db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    return await service.extend_session(data.minutes * 60)

@router.post("/distraction")
async def add_distraction(db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    return await service.add_distraction()

@router.post("/update-time")
async def update_time_left(data: TimeUpdate, db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    return await service.update_time_left(data.time_left)

@router.get("/current")
async def get_current_session(db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    return await service.get_current_session()
