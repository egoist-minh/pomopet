from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import (
    PlanHorizon,
    PlanItemStatus,
    Task,
    Subtask,
    Priority,
    UserActionSource,
    UserActionType,
)
from app.services.habit_service import EventSpec, capture_behavior_events
from app.utils.logger import get_logger, log_error
import uuid

logger = get_logger("pomopet.task_service")

class TaskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_tasks(self):
        logger.info("Fetching all tasks")
        result = await self.db.execute(
            select(Task).where(
                Task.completed == False,
                Task.status == PlanItemStatus.OPEN,
                Task.horizon == PlanHorizon.DAY,
            ).order_by(Task.created_at.desc())
        )
        tasks = result.scalars().all()

        task_list = []
        for task in tasks:
            subtask_result = await self.db.execute(
                select(Subtask).where(Subtask.task_id == task.id, Subtask.completed == False)
            )
            subtasks = subtask_result.scalars().all()

            task_dict = {
                "id": task.id,
                "name": task.name,
                "priority": task.priority.value,
                "deadline": task.deadline,
                "completed": task.completed,
                "estimatedDuration": task.estimated_duration,
                "subtasks": [
                    {"id": s.id, "name": s.name, "completed": s.completed}
                    for s in subtasks
                ]
            }
            task_list.append(task_dict)

        logger.info(f"Retrieved {len(task_list)} tasks")
        return task_list

    async def get_task_summary(self, task_id: str):
        result = await self.db.execute(
            select(Task).where(
                Task.id == task_id,
                Task.status != PlanItemStatus.DROPPED,
                Task.horizon == PlanHorizon.DAY,
            )
        )
        task = result.scalar_one_or_none()
        if task is None:
            return None
        return {"id": task.id, "name": task.name}

    async def get_open_task_summary(self, task_id: str):
        result = await self.db.execute(
            select(Task).where(
                Task.id == task_id,
                Task.completed == False,
                Task.status == PlanItemStatus.OPEN,
                Task.horizon == PlanHorizon.DAY,
            )
        )
        task = result.scalar_one_or_none()
        if task is None:
            return None
        return {"id": task.id, "name": task.name}

    async def create_task(self, task_data: dict):
        priority_str = task_data.get("priority", "medium")
        estimated_duration = task_data.get("estimated_duration")

        if estimated_duration is not None:
            if estimated_duration < 5 or estimated_duration > 120:
                raise ValueError("Duration must be between 5 and 120 minutes")

        task = Task(
            id=str(uuid.uuid4()),
            name=task_data["name"],
            priority=Priority(priority_str),
            deadline=task_data.get("deadline", ""),
            estimated_duration=estimated_duration,
            horizon=PlanHorizon.DAY,
            status=PlanItemStatus.OPEN,
        )
        self.db.add(task)
        await self.db.commit()
        logger.info(f"Created task: {task.id} - {task.name} (duration: {estimated_duration}m)")
        return {"id": task.id, "message": "Task created"}

    async def create_tasks(self, tasks_data: list[dict]):
        """Create a batch of tasks with a single database commit."""
        tasks = []
        for task_data in tasks_data:
            priority_str = task_data.get("priority", "medium")
            estimated_duration = task_data.get("estimated_duration")

            if estimated_duration is not None:
                if estimated_duration < 5 or estimated_duration > 120:
                    raise ValueError("Duration must be between 5 and 120 minutes")

            tasks.append(
                Task(
                    id=str(uuid.uuid4()),
                    name=task_data["name"],
                    priority=Priority(priority_str),
                    deadline=task_data.get("deadline", ""),
                    estimated_duration=estimated_duration,
                    horizon=PlanHorizon.DAY,
                    status=PlanItemStatus.OPEN,
                )
            )

        self.db.add_all(tasks)
        await self.db.commit()
        logger.info("Created task batch containing %s tasks", len(tasks))
        return {
            "ids": [task.id for task in tasks],
            "count": len(tasks),
            "message": "Tasks created",
        }

    async def update_task(self, task_id: str, task_data: dict):
        result = await self.db.execute(
            select(Task).where(
                Task.id == task_id,
                Task.horizon == PlanHorizon.DAY,
                Task.status != PlanItemStatus.DROPPED,
            )
        )
        task = result.scalar_one_or_none()
        if task:
            if "name" in task_data:
                task.name = task_data["name"]
            if "priority" in task_data:
                task.priority = Priority(task_data["priority"])
            if "deadline" in task_data:
                task.deadline = task_data["deadline"]
            if "estimated_duration" in task_data:
                estimated_duration = task_data["estimated_duration"]
                if estimated_duration is not None:
                    if estimated_duration < 5 or estimated_duration > 120:
                        raise ValueError("Duration must be between 5 and 120 minutes")
                task.estimated_duration = estimated_duration
            task.version = (task.version or 0) + 1
            await self.db.commit()
            logger.info(f"Updated task: {task_id}")
            return {"message": "Task updated"}
        return {"error": "Task not found"}

    async def delete_task(self, task_id: str):
        result = await self.db.execute(
            select(Task).where(
                Task.id == task_id,
                Task.horizon == PlanHorizon.DAY,
                Task.status != PlanItemStatus.DROPPED,
            )
        )
        task = result.scalar_one_or_none()
        if task:
            task.status = PlanItemStatus.DROPPED
            task.completed = False
            task.version = (task.version or 0) + 1
            await self.db.commit()
            logger.info(f"Dropped task through legacy delete API: {task_id}")
            return {"message": "Task deleted"}
        logger.warning(f"Task not found for deletion: {task_id}")
        return {"error": "Task not found"}

    async def complete_task(
        self,
        task_id: str,
        *,
        source: str = "ui",
        idempotency_key: str | None = None,
        action_context: dict | None = None,
    ):
        result = await self.db.execute(
            select(Task).where(
                Task.id == task_id,
                Task.horizon == PlanHorizon.DAY,
                Task.status == PlanItemStatus.OPEN,
            )
        )
        task = result.scalar_one_or_none()
        if task:
            task.completed = True
            task.status = PlanItemStatus.COMPLETED
            task.version = (task.version or 0) + 1
            await self.db.commit()
            await capture_behavior_events(self.db, [EventSpec(
                UserActionType.TASK_COMPLETED, UserActionSource(source), "task", task_id,
                idempotency_key or f"task:{task_id}:completed",
                action_context or {},
            )])
            logger.info(f"Completed task: {task_id}")
            return {"message": "Task completed"}
        logger.warning(f"Task not found for completion: {task_id}")
        return {"error": "Task not found"}

    async def add_subtask(self, task_id: str, name: str):
        result = await self.db.execute(
            select(Task).where(
                Task.id == task_id,
                Task.horizon == PlanHorizon.DAY,
                Task.status != PlanItemStatus.DROPPED,
            )
        )
        if result.scalar_one_or_none() is None:
            return {"error": "Task not found"}

        subtask = Subtask(
            id=str(uuid.uuid4()),
            task_id=task_id,
            name=name,
        )
        self.db.add(subtask)
        await self.db.commit()
        return {"id": subtask.id, "message": "Subtask added"}

    async def delete_subtask(self, subtask_id: str):
        result = await self.db.execute(select(Subtask).where(Subtask.id == subtask_id))
        subtask = result.scalar_one_or_none()
        if subtask:
            await self.db.delete(subtask)
            await self.db.commit()
            return {"message": "Subtask deleted"}
        return {"error": "Subtask not found"}

    async def complete_subtask(self, subtask_id: str):
        result = await self.db.execute(select(Subtask).where(Subtask.id == subtask_id))
        subtask = result.scalar_one_or_none()
        if subtask:
            subtask.completed = True
            await self.db.commit()
            return {"message": "Subtask completed"}
        return {"error": "Subtask not found"}
