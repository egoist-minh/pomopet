from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import (
    Goal,
    GoalStatus,
    DistractionEvent,
    DistractionSource,
    PlanHorizon,
    PlanItemStatus,
    Session,
    SessionState,
    Task,
    UserActionSource,
    UserActionType,
)
from app.services.habit_service import EventSpec, capture_behavior_events
from app.utils.logger import get_logger
from datetime import datetime, timezone
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

    async def start_session(
        self,
        task_id: str,
        duration: int,
        *,
        source: str = "ui",
        idempotency_key: str | None = None,
        action_context: dict | None = None,
    ):
        task_result = await self.db.execute(
            select(Task).where(Task.id == task_id)
        )
        task = task_result.scalar_one_or_none()
        if task is None:
            return {"error": "Task not found"}
        if (
            task.horizon != PlanHorizon.DAY
            or task.status != PlanItemStatus.OPEN
            or task.completed
        ):
            return {"error": "Only open daily tasks can start focus sessions"}
        if task.goal_id:
            goal_result = await self.db.execute(
                select(Goal.status).where(Goal.id == task.goal_id)
            )
            goal_status = goal_result.scalar_one_or_none()
            if goal_status != GoalStatus.ACTIVE:
                return {"error": "The task's goal is not active"}

        active_session = await self._get_active_session()
        if active_session:
            active_session.state = SessionState.CANCELLED
            active_session.completed_at = datetime.utcnow()
            logger.info(f"Cancelled previous session: {active_session.id}")

        session = Session(
            id=str(uuid.uuid4()),
            task_id=task_id,
            duration=duration,
            initial_duration=duration,
            initial_duration_source="selected",
            time_left=duration,
            state=SessionState.RUNNING,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        logger.info(f"Started session: {session.id} for task {task_id}, duration {duration}s")
        context = dict(action_context or {})
        context.update({
            "duration_minutes": duration // 60,
            "duration_source": context.get("duration_source", "selected"),
            "goal_id": task.goal_id,
            "task_id": task_id,
            "session_id": session.id,
        })
        event_source = UserActionSource(source)
        prefix = idempotency_key or f"session:{session.id}"
        specs = []
        if active_session:
            specs.append(EventSpec(
                UserActionType.SESSION_CANCELLED, event_source, "session", active_session.id,
                f"{prefix}:auto-cancel:{active_session.id}", {"session_id": active_session.id},
            ))
        specs.extend([
            EventSpec(
                UserActionType.TASK_SELECTED, event_source, "task", task_id,
                f"{prefix}:task-selected", context,
            ),
            EventSpec(
                UserActionType.SESSION_STARTED, event_source, "session", session.id,
                f"{prefix}:session-started", context,
            ),
        ])
        suggested_duration = context.get("suggested_duration_minutes")
        suggested_task = context.get("suggested_task_id")
        suggested_rank = context.get("suggested_rank")
        if suggested_duration is not None or suggested_task is not None or suggested_rank is not None:
            accepted = (
                (suggested_duration is None or suggested_duration == duration // 60)
                and (suggested_task is None or suggested_task == task_id)
                and (suggested_rank is None or suggested_rank == context.get("rank"))
            )
            specs.append(EventSpec(
                UserActionType.SUGGESTION_ACCEPTED if accepted else UserActionType.SUGGESTION_CHANGED,
                UserActionSource.SUGGESTION, "session", session.id,
                f"{prefix}:suggestion", context,
            ))
        await capture_behavior_events(self.db, specs)
        return {
            "id": session.id,
            "task_id": task_id,
            "duration": duration,
            "initial_duration": duration,
            "initial_duration_source": "selected",
            "time_left": duration,
            "state": "running",
            "distraction_count": 0,
            "penalty_seconds": 0,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "message": "Session started",
        }

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

    async def cancel_session(
        self, *, source: str = "ui", idempotency_key: str | None = None
    ):
        active_session = await self._get_active_session()
        if active_session:
            active_session.state = SessionState.CANCELLED
            active_session.completed_at = datetime.utcnow()
            await self.db.commit()
            await capture_behavior_events(self.db, [EventSpec(
                UserActionType.SESSION_CANCELLED, UserActionSource(source),
                "session", active_session.id,
                idempotency_key or f"session:{active_session.id}:cancelled",
                {"session_id": active_session.id},
            )])
            return {"message": "Session cancelled"}
        return {"error": "No active session"}

    async def extend_session(
        self,
        seconds: int,
        *,
        source: str = "ui",
        idempotency_key: str | None = None,
    ):
        active_session = await self._get_active_session()
        if active_session:
            active_session.time_left += seconds
            active_session.duration += seconds
            await self.db.commit()
            await capture_behavior_events(self.db, [EventSpec(
                UserActionType.SESSION_EXTENDED, UserActionSource(source),
                "session", active_session.id,
                idempotency_key or f"session:{active_session.id}:extend:{active_session.duration}",
                {
                    "session_id": active_session.id,
                    "extension_minutes": seconds // 60,
                    "duration_minutes": active_session.duration // 60,
                },
            )])
            return {"message": f"Session extended by {seconds} seconds", "time_left": active_session.time_left, "duration": active_session.duration}
        return {"error": "No active session"}

    async def complete_session(self):
        active_session = await self._get_active_session()
        if active_session:
            completed_task = None
            if active_session.task_id:
                task = await self.db.get(Task, active_session.task_id)
                if (
                    task is not None
                    and task.horizon == PlanHorizon.DAY
                    and task.status == PlanItemStatus.OPEN
                    and not task.completed
                ):
                    task.completed = True
                    task.status = PlanItemStatus.COMPLETED
                    task.version = (task.version or 0) + 1
                    task.updated_at = datetime.utcnow()
                    completed_task = task
            active_session.state = SessionState.COMPLETED
            active_session.completed_at = datetime.utcnow()
            active_session.time_left = 0
            await self.db.commit()
            if completed_task is not None:
                await capture_behavior_events(self.db, [EventSpec(
                    UserActionType.TASK_COMPLETED,
                    UserActionSource.UI,
                    "task",
                    completed_task.id,
                    f"session:{active_session.id}:task-completed",
                    {
                        "session_id": active_session.id,
                        "task_id": completed_task.id,
                        "goal_id": completed_task.goal_id,
                    },
                )])
            logger.info(f"Completed session: {active_session.id}, duration: {active_session.duration}s")
            return {
                "message": "Session completed",
                "duration": active_session.duration,
                "task_id": active_session.task_id,
                "task_completed": completed_task is not None,
            }
        return {"error": "No active session"}

    @staticmethod
    def _utc_naive(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    async def add_distraction(self):
        active_session = await self._get_active_session()
        if active_session:
            now = datetime.utcnow()
            event = DistractionEvent(
                id=str(uuid.uuid4()),
                session_id=active_session.id,
                source=DistractionSource.MANUAL,
                confidence=1.0,
                started_at=now,
                ended_at=now,
                duration_seconds=0,
            )
            self.db.add(event)
            active_session.distraction_count += 1
            active_session.penalty_seconds += 300
            active_session.time_left += 300
            active_session.duration += 300
            await self.db.commit()
            logger.warning(f"Distraction added to session {active_session.id}, count: {active_session.distraction_count}")
            return {
                "message": "Distraction recorded",
                "event_id": event.id,
                "distraction_count": active_session.distraction_count,
                "time_left": active_session.time_left,
                "penalty_seconds_added": 300,
            }
        return {"error": "No active session"}

    async def add_automatic_distraction(
        self,
        *,
        event_id: str,
        source: str,
        application: str | None,
        confidence: float,
        started_at: datetime,
    ):
        existing_result = await self.db.execute(
            select(DistractionEvent).where(DistractionEvent.id == event_id)
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            session_result = await self.db.execute(
                select(Session).where(Session.id == existing.session_id)
            )
            session = session_result.scalar_one_or_none()
            return {
                "message": "Distraction already recorded",
                "event_id": existing.id,
                "distraction_count": session.distraction_count if session else 0,
                "time_left": session.time_left if session else 0,
                "penalty_seconds_added": 0,
            }

        active_session = await self._get_active_session()
        if not active_session or active_session.state != SessionState.RUNNING:
            return {"error": "No running session"}

        event = DistractionEvent(
            id=event_id,
            session_id=active_session.id,
            source=DistractionSource(source),
            application=application.strip()[:120] if application and application.strip() else None,
            confidence=max(0.0, min(1.0, confidence)),
            started_at=self._utc_naive(started_at),
            duration_seconds=0,
        )
        self.db.add(event)
        active_session.distraction_count += 1
        await self.db.commit()
        logger.info(
            "Automatic distraction recorded for session %s from %s",
            active_session.id,
            source,
        )
        return {
            "message": "Automatic distraction recorded",
            "event_id": event.id,
            "distraction_count": active_session.distraction_count,
            "time_left": active_session.time_left,
            "penalty_seconds_added": 0,
        }

    async def finish_automatic_distraction(self, event_id: str, ended_at: datetime):
        result = await self.db.execute(
            select(DistractionEvent).where(DistractionEvent.id == event_id)
        )
        event = result.scalar_one_or_none()
        if not event:
            return {"error": "Distraction event not found"}

        normalized_end = self._utc_naive(ended_at)
        if normalized_end < event.started_at:
            return {"error": "Distraction end precedes its start"}

        event.ended_at = normalized_end
        event.duration_seconds = min(
            24 * 60 * 60,
            max(0, round((normalized_end - event.started_at).total_seconds())),
        )
        await self.db.commit()
        return {
            "message": "Distraction event completed",
            "event_id": event.id,
            "duration_seconds": event.duration_seconds,
        }

    async def update_time_left(self, time_left: int):
        active_session = await self._get_active_session()
        if active_session:
            active_session.time_left = time_left
            await self.db.commit()
            return {"time_left": time_left}
        return {"error": "No active session"}

    async def get_current_session(self):
        active_session = await self._get_active_session()
        if active_session:
            return {
                "id": active_session.id,
                "task_id": active_session.task_id,
                "duration": active_session.duration,
                "initial_duration": active_session.initial_duration,
                "initial_duration_source": active_session.initial_duration_source,
                "time_left": active_session.time_left,
                "state": active_session.state.value,
                "distraction_count": active_session.distraction_count,
                "penalty_seconds": active_session.penalty_seconds,
                "started_at": active_session.started_at.isoformat() if active_session.started_at else None,
            }
        return None
