from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db
from app.services.personal_memory_schemas import (
    MemoryActionRequest,
    MemoryEditRequest,
    ProfileUpdateRequest,
)
from app.services.personal_memory_service import MemoryNotFoundError, PersonalMemoryService
from app.services.profile_service import ProfileService
from app.services.habit_service import HabitService
from app.services.relationship_memory_service import (
    RelationshipMemoryNotFoundError,
    RelationshipMemoryService,
)
from app.services.relationship_schemas import RelationshipActionRequest


router = APIRouter()


def _not_found() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "status": "error",
            "message": "Active memory was not found",
            "error_code": "MEMORY_NOT_FOUND",
        },
    )


@router.get("/profile")
async def get_profile(database: AsyncSession = Depends(get_db)):
    profile = await ProfileService(database).get_or_create_default()
    return ProfileService.serialize(profile)


@router.patch("/profile")
async def update_profile(
    request: ProfileUpdateRequest,
    database: AsyncSession = Depends(get_db),
):
    profile = await ProfileService(database).update_default(
        request.model_dump(exclude_unset=True)
    )
    return ProfileService.serialize(profile)


@router.get("/memories")
async def list_memories(database: AsyncSession = Depends(get_db)):
    service = PersonalMemoryService(database)
    return [service.serialize(memory) for memory in await service.list_active()]


@router.get("/habits")
async def list_habits(database: AsyncSession = Depends(get_db)):
    service = HabitService(database)
    return [service.serialize(habit) for habit in await service.list_active()]


@router.get("/episodes")
async def list_episodes(database: AsyncSession = Depends(get_db)):
    service = RelationshipMemoryService(database)
    return [service.serialize_episode(item) for item in await service.list_episodes()]


@router.delete("/episodes/{episode_id}")
async def update_episode_status(
    episode_id: str,
    request: RelationshipActionRequest | None = None,
    database: AsyncSession = Depends(get_db),
):
    service = RelationshipMemoryService(database)
    action = request.action if request is not None else "archived"
    try:
        episode = await service.set_episode_status(
            episode_id, action, source_reference=f"episode:{episode_id}"
        )
    except RelationshipMemoryNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Active episode was not found", "error_code": "EPISODE_NOT_FOUND"},
        )
    return {"id": episode.id, "status": episode.status.value}


@router.get("/rituals")
async def list_rituals(database: AsyncSession = Depends(get_db)):
    service = RelationshipMemoryService(database)
    return [service.serialize_ritual(item) for item in await service.list_rituals()]


@router.delete("/rituals/{ritual_id}")
async def update_ritual_status(
    ritual_id: str,
    request: RelationshipActionRequest | None = None,
    database: AsyncSession = Depends(get_db),
):
    service = RelationshipMemoryService(database)
    action = request.action if request is not None else "archived"
    try:
        ritual = await service.set_ritual_status(
            ritual_id, action, source_reference=f"ritual:{ritual_id}"
        )
    except RelationshipMemoryNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Active ritual was not found", "error_code": "RITUAL_NOT_FOUND"},
        )
    return {"id": ritual.id, "status": ritual.status.value}


@router.get("/relational-state")
async def get_relational_state(database: AsyncSession = Depends(get_db)):
    service = RelationshipMemoryService(database)
    return service.serialize_state(await service.get_relational_state())


@router.delete("/habits/{habit_id}")
async def dismiss_habit(habit_id: str, database: AsyncSession = Depends(get_db)):
    if not await HabitService(database).dismiss(habit_id):
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Habit was not found", "error_code": "HABIT_NOT_FOUND"},
        )
    return {"id": habit_id, "active": False}


@router.get("/focus-suggestion")
async def get_focus_suggestion(
    view: str = Query(default="today", pattern="^(inbox|today|week)$"),
    timezone_offset: int = Query(default=0, ge=-720, le=840),
    task_id: str | None = Query(default=None, min_length=1, max_length=128),
    goal_id: str | None = Query(default=None, min_length=1, max_length=128),
    database: AsyncSession = Depends(get_db),
):
    return await HabitService(database).focus_suggestion(
        view=view,
        timezone_offset=timezone_offset,
        task_id=task_id,
        goal_id=goal_id,
    )


@router.patch("/memories/{memory_id}")
async def update_memory(
    memory_id: str,
    request: MemoryEditRequest,
    database: AsyncSession = Depends(get_db),
):
    service = PersonalMemoryService(database)
    try:
        memory = await service.update(memory_id, request.value)
    except MemoryNotFoundError:
        return _not_found()
    except ValueError as error:
        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "message": str(error),
                "error_code": "INVALID_MEMORY_VALUE",
            },
        )
    return service.serialize(memory)


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    request: MemoryActionRequest | None = None,
    database: AsyncSession = Depends(get_db),
):
    service = PersonalMemoryService(database)
    try:
        memory = await service.deactivate(
            memory_id,
            (request.action if request is not None else "deleted"),
            source_reference=f"memory:{memory_id}",
        )
    except MemoryNotFoundError:
        return _not_found()
    return {"id": memory.id, "active": False}


@router.delete("/data")
async def delete_relationship_data(database: AsyncSession = Depends(get_db)):
    await PersonalMemoryService(database).delete_all()
    return {"status": "deleted"}
