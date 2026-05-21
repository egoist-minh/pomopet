from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import get_db
from app.services.task_service import TaskService
from pydantic import BaseModel

router = APIRouter()

class TaskCreate(BaseModel):
    name: str
    priority: str
    deadline: str

@router.get("/")
async def get_tasks(db: AsyncSession = Depends(get_db)):
    service = TaskService(db)
    return await service.get_all_tasks()

@router.post("/")
async def create_task(task: TaskCreate, db: AsyncSession = Depends(get_db)):
    service = TaskService(db)
    return await service.create_task(task.dict())

@router.delete("/{task_id}")
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db)):
    service = TaskService(db)
    return await service.delete_task(task_id)

@router.post("/{task_id}/complete")
async def complete_task(task_id: str, db: AsyncSession = Depends(get_db)):
    service = TaskService(db)
    return await service.complete_task(task_id)
