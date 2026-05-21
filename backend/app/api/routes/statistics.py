from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import get_db
from app.services.statistics_service import StatisticsService

router = APIRouter()

@router.get("/")
async def get_statistics(db: AsyncSession = Depends(get_db)):
    service = StatisticsService(db)
    return await service.get_daily_statistics()
