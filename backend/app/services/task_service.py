from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.models import Task, Subtask, Priority
from app.utils.logger import get_logger, log_error
import uuid

logger = get_logger("pomopet.task_service")

class TaskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_tasks(self):
        logger.info("Fetching all tasks")
        result = await self.db.execute(
            select(Task).where(Task.completed == False).order_by(Task.created_at.desc())
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
                "subtasks": [
                    {"id": s.id, "name": s.name, "completed": s.completed}
                    for s in subtasks
                ]
            }
            task_list.append(task_dict)
        
        logger.info(f"Retrieved {len(task_list)} tasks")
        return task_list

    async def create_task(self, task_data: dict):
        priority_str = task_data.get("priority", "medium")
        task = Task(
            id=str(uuid.uuid4()),
            name=task_data["name"],
            priority=Priority(priority_str),
            deadline=task_data.get("deadline", ""),
        )
        self.db.add(task)
        await self.db.commit()
        logger.info(f"Created task: {task.id} - {task.name}")
        return {"id": task.id, "message": "Task created"}

    async def update_task(self, task_id: str, task_data: dict):
        result = await self.db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if task:
            if "name" in task_data:
                task.name = task_data["name"]
            if "priority" in task_data:
                task.priority = Priority(task_data["priority"])
            if "deadline" in task_data:
                task.deadline = task_data["deadline"]
            await self.db.commit()
            return {"message": "Task updated"}
        return {"error": "Task not found"}

    async def delete_task(self, task_id: str):
        result = await self.db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if task:
            await self.db.execute(delete(Subtask).where(Subtask.task_id == task_id))
            await self.db.delete(task)
            await self.db.commit()
            logger.info(f"Deleted task: {task_id}")
            return {"message": "Task deleted"}
        logger.warning(f"Task not found for deletion: {task_id}")
        return {"error": "Task not found"}

    async def complete_task(self, task_id: str):
        result = await self.db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if task:
            task.completed = True
            await self.db.commit()
            logger.info(f"Completed task: {task_id}")
            return {"message": "Task completed"}
        logger.warning(f"Task not found for completion: {task_id}")
        return {"error": "Task not found"}

    async def add_subtask(self, task_id: str, name: str):
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
