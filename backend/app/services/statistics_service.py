from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import DistractionEvent, Session, SessionState
from datetime import datetime, time, timedelta

class StatisticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _day_bounds(timezone_offset: int, days_ago: int = 0):
        offset = timedelta(minutes=timezone_offset)
        local_date = (datetime.utcnow() + offset).date() - timedelta(days=days_ago)
        local_start = datetime.combine(local_date, time.min)
        return local_start - offset, local_start + timedelta(days=1) - offset

    @staticmethod
    def _focus_seconds(session: Session) -> int:
        return max(0, session.duration - (session.penalty_seconds or 0))

    async def get_daily_statistics(self, timezone_offset: int = 0):
        day_start, day_end = self._day_bounds(timezone_offset)

        result = await self.db.execute(
            select(Session).where(
                Session.state == SessionState.COMPLETED,
                Session.completed_at >= day_start,
                Session.completed_at < day_end,
            )
        )
        sessions = result.scalars().all()

        total_seconds = sum(self._focus_seconds(session) for session in sessions)
        focus_hours = total_seconds / 3600

        return {
            "focusHoursToday": round(focus_hours, 2),
            "sessionsCompleted": len(sessions)
        }

    async def get_weekly_statistics(self, timezone_offset: int = 0):
        week_start, _ = self._day_bounds(timezone_offset, days_ago=6)
        _, today_end = self._day_bounds(timezone_offset)

        result = await self.db.execute(
            select(Session).where(
                Session.state == SessionState.COMPLETED,
                Session.completed_at >= week_start,
                Session.completed_at < today_end,
            )
        )
        sessions = result.scalars().all()

        total_seconds = sum(self._focus_seconds(session) for session in sessions)
        focus_hours = total_seconds / 3600

        return {
            "focusHoursWeek": round(focus_hours, 2),
            "sessionsCompleted": len(sessions)
        }

    async def get_distraction_statistics(self, timezone_offset: int = 0):
        week_ago, _ = self._day_bounds(timezone_offset, days_ago=6)
        offset = timedelta(minutes=timezone_offset)

        # Get all sessions from the past week
        result = await self.db.execute(
            select(Session).where(
                Session.started_at >= week_ago
            )
        )
        sessions = result.scalars().all()

        event_result = await self.db.execute(
            select(DistractionEvent).where(DistractionEvent.started_at >= week_ago)
        )
        events = event_result.scalars().all()

        # Get current distraction chain (from most recent active session)
        current_result = await self.db.execute(
            select(Session).where(
                Session.state.in_([SessionState.RUNNING, SessionState.PAUSED])
            ).order_by(Session.started_at.desc())
        )
        current_session = current_result.scalar_one_or_none()
        distraction_chain = current_session.distraction_count if current_session else 0

        # Prefer event timestamps for new records, while retaining aggregate-only
        # legacy session counts from databases created before distraction events.
        hourly_distractions = {}
        event_counts_by_session = {}
        for event in events:
            event_counts_by_session[event.session_id] = event_counts_by_session.get(event.session_id, 0) + 1
            hour = (event.started_at + offset).hour
            bin_hour = (hour // 2) * 2
            key = f"{bin_hour:02d}:00"
            hourly_distractions[key] = hourly_distractions.get(key, 0) + 1

        for session in sessions:
            legacy_count = max(
                0,
                session.distraction_count - event_counts_by_session.get(session.id, 0),
            )
            if legacy_count > 0 and session.started_at:
                hour = (session.started_at + offset).hour
                bin_hour = (hour // 2) * 2
                key = f"{bin_hour:02d}:00"
                hourly_distractions[key] = hourly_distractions.get(key, 0) + legacy_count

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

    async def get_all_statistics(self, timezone_offset: int = 0):
        daily = await self.get_daily_statistics(timezone_offset)
        weekly = await self.get_weekly_statistics(timezone_offset)
        distractions = await self.get_distraction_statistics(timezone_offset)

        return {
            "focusHoursToday": daily["focusHoursToday"],
            "focusHoursWeek": weekly["focusHoursWeek"],
            "sessionsCompleted": daily["sessionsCompleted"],
            "distractionChain": distractions["distractionChain"],
            "distractionData": distractions["distractionData"],
            "totalDistractionsWeek": distractions["totalDistractionsWeek"]
        }
