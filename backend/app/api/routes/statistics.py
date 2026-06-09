from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import get_db
from app.services.statistics_service import StatisticsService

router = APIRouter()

@router.get("/")
async def get_statistics(db: AsyncSession = Depends(get_db)):
    service = StatisticsService(db)
    return await service.get_all_statistics()

@router.get("/daily")
async def get_daily_statistics(db: AsyncSession = Depends(get_db)):
    service = StatisticsService(db)
    return await service.get_daily_statistics()

@router.get("/weekly")
async def get_weekly_statistics(db: AsyncSession = Depends(get_db)):
    service = StatisticsService(db)
    return await service.get_weekly_statistics()

@router.get("/distractions")
async def get_distraction_statistics(db: AsyncSession = Depends(get_db)):
    service = StatisticsService(db)
    return await service.get_distraction_statistics()
