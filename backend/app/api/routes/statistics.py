from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import get_db
from app.services.statistics_service import StatisticsService

router = APIRouter()

@router.get("/")
async def get_statistics(
    timezone_offset: int = Query(default=0, ge=-720, le=840),
    db: AsyncSession = Depends(get_db),
):
    service = StatisticsService(db)
    return await service.get_all_statistics(timezone_offset)

@router.get("/daily")
async def get_daily_statistics(
    timezone_offset: int = Query(default=0, ge=-720, le=840),
    db: AsyncSession = Depends(get_db),
):
    service = StatisticsService(db)
    return await service.get_daily_statistics(timezone_offset)

@router.get("/weekly")
async def get_weekly_statistics(
    timezone_offset: int = Query(default=0, ge=-720, le=840),
    db: AsyncSession = Depends(get_db),
):
    service = StatisticsService(db)
    return await service.get_weekly_statistics(timezone_offset)

@router.get("/distractions")
async def get_distraction_statistics(
    timezone_offset: int = Query(default=0, ge=-720, le=840),
    db: AsyncSession = Depends(get_db),
):
    service = StatisticsService(db)
    return await service.get_distraction_statistics(timezone_offset)
