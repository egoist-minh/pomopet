from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import Session, SessionState
from app.utils.logger import get_logger
from datetime import datetime
import uuid

logger = get_logger("pomopet.session_service")

class SessionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_active_session(self) -> Session | None:
        result = await self.db.execute(
            select(Session).where(
                Session.state.in_([SessionState.RUNNING, SessionState.PAUSED])
            )
        )
        return result.scalar_one_or_none()

    async def start_session(self, task_id: str, duration: int):
        active_session = await self._get_active_session()
        if active_session:
            active_session.state = SessionState.CANCELLED
            active_session.completed_at = datetime.utcnow()
            logger.info(f"Cancelled previous session: {active_session.id}")

        session = Session(
            id=str(uuid.uuid4()),
            task_id=task_id,
            duration=duration,
            time_left=duration,
            state=SessionState.RUNNING,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        logger.info(f"Started session: {session.id} for task {task_id}, duration {duration}s")
        return {"id": session.id, "task_id": task_id, "duration": duration, "time_left": duration, "state": "running", "message": "Session started"}

    async def pause_session(self):
        active_session = await self._get_active_session()
        if active_session and active_session.state == SessionState.RUNNING:
            active_session.state = SessionState.PAUSED
            await self.db.commit()
            return {"message": "Session paused", "time_left": active_session.time_left}
        return {"error": "No running session"}

    async def resume_session(self):
        active_session = await self._get_active_session()
        if active_session and active_session.state == SessionState.PAUSED:
            active_session.state = SessionState.RUNNING
            await self.db.commit()
            return {"message": "Session resumed", "time_left": active_session.time_left}
        return {"error": "No paused session"}

    async def cancel_session(self):
        active_session = await self._get_active_session()
        if active_session:
            active_session.state = SessionState.CANCELLED
            active_session.completed_at = datetime.utcnow()
            await self.db.commit()
            return {"message": "Session cancelled"}
        return {"message": "No active session"}

    async def extend_session(self, seconds: int):
        active_session = await self._get_active_session()
        if active_session:
            active_session.time_left += seconds
            active_session.duration += seconds
            await self.db.commit()
            return {"message": f"Session extended by {seconds} seconds", "time_left": active_session.time_left, "duration": active_session.duration}
        return {"error": "No active session"}

    async def complete_session(self):
        active_session = await self._get_active_session()
        if active_session:
            active_session.state = SessionState.COMPLETED
            active_session.completed_at = datetime.utcnow()
            active_session.time_left = 0
            await self.db.commit()
            logger.info(f"Completed session: {active_session.id}, duration: {active_session.duration}s")
            return {"message": "Session completed", "duration": active_session.duration}
        return {"error": "No active session"}

    async def add_distraction(self):
        active_session = await self._get_active_session()
        if active_session:
            active_session.distraction_count += 1
            active_session.time_left += 300
            active_session.duration += 300
            await self.db.commit()
            logger.warning(f"Distraction added to session {active_session.id}, count: {active_session.distraction_count}")
            return {"message": "Distraction recorded", "distraction_count": active_session.distraction_count, "time_left": active_session.time_left}
        return {"error": "No active session"}

    async def update_time_left(self, time_left: int):
        active_session = await self._get_active_session()
        if active_session:
            active_session.time_left = time_left
            await self.db.commit()
            return {"time_left": time_left}
        return None

    async def get_current_session(self):
        active_session = await self._get_active_session()
        if active_session:
            return {
                "id": active_session.id,
                "task_id": active_session.task_id,
                "duration": active_session.duration,
                "time_left": active_session.time_left,
                "state": active_session.state.value,
                "distraction_count": active_session.distraction_count,
                "started_at": active_session.started_at.isoformat() if active_session.started_at else None,
            }
        return None
