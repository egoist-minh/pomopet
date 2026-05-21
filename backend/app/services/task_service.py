from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import Task
import uuid

class TaskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_tasks(self):
        result = await self.db.execute(select(Task))
        tasks = result.scalars().all()
        return [
            {
                "id": task.id,
                "name": task.name,
                "priority": task.priority.value,
                "deadline": task.deadline,
            }
            for task in tasks
        ]

    async def create_task(self, task_data: dict):
        task = Task(
            id=str(uuid.uuid4()),
            name=task_data["name"],
            priority=task_data["priority"],
            deadline=task_data["deadline"],
        )
        self.db.add(task)
        await self.db.commit()
        return {"id": task.id, "message": "Task created"}

    async def delete_task(self, task_id: str):
        result = await self.db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if task:
            await self.db.delete(task)
            await self.db.commit()
            return {"message": "Task deleted"}
        return {"error": "Task not found"}

    async def complete_task(self, task_id: str):
        # For MVP, completing a task just deletes it
        return await self.delete_task(task_id)
