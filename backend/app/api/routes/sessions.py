from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import get_db
from app.services.session_service import SessionService
from pydantic import BaseModel

router = APIRouter()

class SessionStart(BaseModel):
    task_id: str
    duration: int  # in seconds

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

@router.post("/extend")
async def extend_session(minutes: int, db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    return await service.extend_session(minutes * 60)

@router.get("/current")
async def get_current_session(db: AsyncSession = Depends(get_db)):
    service = SessionService(db)
    return await service.get_current_session()
