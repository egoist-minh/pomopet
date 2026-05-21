from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.models import Session, SessionState
from datetime import datetime, timedelta

class StatisticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_daily_statistics(self):
        today = datetime.utcnow().date()
        
        # Get completed sessions from today
        result = await self.db.execute(
            select(Session).where(
                Session.state == SessionState.COMPLETED,
                func.date(Session.completed_at) == today
            )
        )
        sessions = result.scalars().all()
        
        # Calculate total focus time in hours
        total_seconds = sum(s.duration - s.time_left for s in sessions)
        focus_hours = total_seconds / 3600
        
        return {
            "focusHoursToday": round(focus_hours, 2),
            "sessionsCompleted": len(sessions)
        }
