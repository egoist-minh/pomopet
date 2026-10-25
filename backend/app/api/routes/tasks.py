from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import get_db
from app.services.task_service import TaskService
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional
from app.models.models import Priority

router = APIRouter()

class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    priority: Priority = Priority.MEDIUM
    deadline: Optional[str] = ""
    estimated_duration: Optional[int] = Field(default=None, ge=5, le=120)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Task name must not be blank")
        return value

class TaskUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    priority: Optional[Priority] = None
    deadline: Optional[str] = None
    estimated_duration: Optional[int] = Field(default=None, ge=5, le=120)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Task name must not be blank")
        return value

class SubtaskCreate(BaseModel):
    task_id: str
    name: str = Field(min_length=1, max_length=200)


class TaskActionRequest(BaseModel):
    source: Literal["ui", "chat", "suggestion"] = "ui"
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)
    action_context: dict | None = None


def require_task(result: dict):
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result

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
    return require_task(await service.update_task(task_id, task.model_dump(exclude_unset=True)))

@router.delete("/{task_id}")
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db)):
    service = TaskService(db)
    return require_task(await service.delete_task(task_id))

@router.post("/{task_id}/complete")
async def complete_task(
    task_id: str,
    request: TaskActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    service = TaskService(db)
    metadata = request or TaskActionRequest()
    return require_task(await service.complete_task(
        task_id,
        source=metadata.source,
        idempotency_key=metadata.idempotency_key,
        action_context=metadata.action_context,
    ))

@router.post("/subtasks")
async def add_subtask(subtask: SubtaskCreate, db: AsyncSession = Depends(get_db)):
    service = TaskService(db)
    return require_task(await service.add_subtask(subtask.task_id, subtask.name.strip()))

@router.delete("/subtasks/{subtask_id}")
async def delete_subtask(subtask_id: str, db: AsyncSession = Depends(get_db)):
    service = TaskService(db)
    return require_task(await service.delete_subtask(subtask_id))

@router.post("/subtasks/{subtask_id}/complete")
async def complete_subtask(subtask_id: str, db: AsyncSession = Depends(get_db)):
    service = TaskService(db)
    return require_task(await service.complete_subtask(subtask_id))
