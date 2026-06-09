from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import get_db
from app.services.task_service import TaskService
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class TaskCreate(BaseModel):
    name: str
    priority: str = "medium"
    deadline: Optional[str] = ""

class TaskUpdate(BaseModel):
    name: Optional[str] = None
    priority: Optional[str] = None
    deadline: Optional[str] = None

class SubtaskCreate(BaseModel):
    task_id: str
    name: str

@router.get("/")
async def get_tasks(db: AsyncSession = Depends(get_db)):
    service = TaskService(db)
    return await service.get_all_tasks()

@router.post("/")
async def create_task(task: TaskCreate, db: AsyncSession = Depends(get_db)):
    service = TaskService(db)
    return await service.create_task(task.model_dump())

@router.put("/{task_id}")
async def update_task(task_id: str, task: TaskUpdate, db: AsyncSession = Depends(get_db)):
    service = TaskService(db)
    return await service.update_task(task_id, task.model_dump(exclude_unset=True))

@router.delete("/{task_id}")
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db)):
    service = TaskService(db)
    return await service.delete_task(task_id)

@router.post("/{task_id}/complete")
async def complete_task(task_id: str, db: AsyncSession = Depends(get_db)):
    service = TaskService(db)
    return await service.complete_task(task_id)

@router.post("/subtasks")
async def add_subtask(subtask: SubtaskCreate, db: AsyncSession = Depends(get_db)):
    service = TaskService(db)
    return await service.add_subtask(subtask.task_id, subtask.name)

@router.delete("/subtasks/{subtask_id}")
async def delete_subtask(subtask_id: str, db: AsyncSession = Depends(get_db)):
    service = TaskService(db)
    return await service.delete_subtask(subtask_id)

@router.post("/subtasks/{subtask_id}/complete")
async def complete_subtask(subtask_id: str, db: AsyncSession = Depends(get_db)):
    service = TaskService(db)
    return await service.complete_subtask(subtask_id)
