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

    async def get_weekly_statistics(self):
        week_ago = datetime.utcnow() - timedelta(days=7)
        
        # Get completed sessions from the past week
        result = await self.db.execute(
            select(Session).where(
                Session.state == SessionState.COMPLETED,
                Session.completed_at >= week_ago
            )
        )
        sessions = result.scalars().all()
        
        # Calculate total focus time in hours
        total_seconds = sum(s.duration - s.time_left for s in sessions)
        focus_hours = total_seconds / 3600
        
        return {
            "focusHoursWeek": round(focus_hours, 2),
            "sessionsCompleted": len(sessions)
        }

    async def get_distraction_statistics(self):
        week_ago = datetime.utcnow() - timedelta(days=7)
        
        # Get all sessions from the past week
        result = await self.db.execute(
            select(Session).where(
                Session.started_at >= week_ago
            )
        )
        sessions = result.scalars().all()
        
        # Get current distraction chain (from most recent active session)
        current_result = await self.db.execute(
            select(Session).where(
                Session.state.in_([SessionState.RUNNING, SessionState.PAUSED])
            ).order_by(Session.started_at.desc())
        )
        current_session = current_result.scalar_one_or_none()
        distraction_chain = current_session.distraction_count if current_session else 0
        
        # Group distractions by hour
        hourly_distractions = {}
        for session in sessions:
            if session.distraction_count > 0 and session.started_at:
                hour = session.started_at.hour
                bin_hour = (hour // 2) * 2
                key = f"{bin_hour:02d}:00"
                hourly_distractions[key] = hourly_distractions.get(key, 0) + session.distraction_count
        
        # Format for chart
        distraction_data = []
        for i in range(12):
            hour = i * 2
            key = f"{hour:02d}:00"
            distraction_data.append({
                "time": key,
                "distractions": hourly_distractions.get(key, 0)
            })
        
        return {
            "distractionChain": distraction_chain,
            "distractionData": distraction_data,
            "totalDistractionsWeek": sum(s.distraction_count for s in sessions)
        }

    async def get_all_statistics(self):
        daily = await self.get_daily_statistics()
        weekly = await self.get_weekly_statistics()
        distractions = await self.get_distraction_statistics()
        
        return {
            "focusHoursToday": daily["focusHoursToday"],
            "focusHoursWeek": weekly["focusHoursWeek"],
            "sessionsCompleted": daily["sessionsCompleted"],
            "distractionChain": distractions["distractionChain"],
            "distractionData": distractions["distractionData"],
            "totalDistractionsWeek": distractions["totalDistractionsWeek"]
        }
