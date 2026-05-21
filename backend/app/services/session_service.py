from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import Session, SessionState
from datetime import datetime
import uuid

class SessionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.current_session = None

    async def start_session(self, task_id: str, duration: int):
        # Cancel any existing running session
        await self.cancel_session()

        session = Session(
            id=str(uuid.uuid4()),
            task_id=task_id,
            duration=duration,
            time_left=duration,
            state=SessionState.RUNNING,
        )
        self.db.add(session)
        await self.db.commit()
        self.current_session = session
        return {"id": session.id, "message": "Session started"}

    async def pause_session(self):
        if self.current_session and self.current_session.state == SessionState.RUNNING:
            self.current_session.state = SessionState.PAUSED
            await self.db.commit()
            return {"message": "Session paused"}
        return {"error": "No running session"}

    async def resume_session(self):
        if self.current_session and self.current_session.state == SessionState.PAUSED:
            self.current_session.state = SessionState.RUNNING
            await self.db.commit()
            return {"message": "Session resumed"}
        return {"error": "No paused session"}

    async def cancel_session(self):
        if self.current_session:
            self.current_session.state = SessionState.CANCELLED
            self.current_session.completed_at = datetime.utcnow()
            await self.db.commit()
            self.current_session = None
            return {"message": "Session cancelled"}
        return {"message": "No active session"}

    async def extend_session(self, seconds: int):
        if self.current_session:
            self.current_session.time_left += seconds
            self.current_session.duration += seconds
            await self.db.commit()
            return {"message": f"Session extended by {seconds} seconds"}
        return {"error": "No active session"}

    async def get_current_session(self):
        if self.current_session:
            return {
                "id": self.current_session.id,
                "task_id": self.current_session.task_id,
                "time_left": self.current_session.time_left,
                "state": self.current_session.state.value,
            }
        return None
