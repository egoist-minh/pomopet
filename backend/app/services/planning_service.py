from __future__ import annotations

from datetime import date, datetime, timedelta
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Goal,
    GoalStatus,
    PlanDraft,
    PlanHorizon,
    PlanItem,
    PlanItemStatus,
    Priority,
    Session,
    SessionState,
)
from app.utils.logger import get_logger


logger = get_logger("pomopet.planning_service")


class PlanningError(ValueError):
    pass


class PlanningNotFoundError(PlanningError):
    pass


class PlanningConflictError(PlanningError):
    pass


class PlanningService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _enum_value(value):
        return value.value if hasattr(value, "value") else value

    @classmethod
    def serialize_goal(cls, goal: Goal) -> dict:
        return {
            "id": goal.id,
            "title": goal.title,
            "definition_of_done": goal.definition_of_done,
            "deadline": goal.deadline,
            "importance": cls._enum_value(goal.importance),
            "status": cls._enum_value(goal.status),
            "weekly_capacity_minutes": goal.weekly_capacity_minutes,
            "version": goal.version,
            "created_at": goal.created_at.isoformat() if goal.created_at else None,
            "updated_at": goal.updated_at.isoformat() if goal.updated_at else None,
        }

    @classmethod
    def serialize_plan_item(cls, item: PlanItem) -> dict:
        return {
            "id": item.id,
            "goal_id": item.goal_id,
            "parent_id": item.parent_id,
            "horizon": cls._enum_value(item.horizon),
            "title": item.name,
            "importance": cls._enum_value(item.priority),
            "deadline": item.deadline or None,
            "planned_for": item.planned_for,
            "period_start": item.period_start,
            "estimate_minutes": item.estimated_duration,
            "status": cls._enum_value(item.status),
            "version": item.version,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }

    @staticmethod
    def _check_version(entity, expected_version: int | None) -> None:
        if expected_version is not None and entity.version != expected_version:
            raise PlanningConflictError(
                f"Version conflict: expected {expected_version}, current {entity.version}"
            )

    @staticmethod
    def _touch(entity) -> None:
        entity.version = (entity.version or 0) + 1
        entity.updated_at = datetime.utcnow()

    async def _get_goal(self, goal_id: str) -> Goal:
        result = await self.db.execute(select(Goal).where(Goal.id == goal_id))
        goal = result.scalar_one_or_none()
        if goal is None:
            raise PlanningNotFoundError("Goal not found")
        return goal

    async def _get_item(self, item_id: str) -> PlanItem:
        result = await self.db.execute(select(PlanItem).where(PlanItem.id == item_id))
        item = result.scalar_one_or_none()
        if item is None:
            raise PlanningNotFoundError("Plan item not found")
        return item

    async def list_goals(self, include_archived: bool = False) -> list[dict]:
        query = select(Goal)
        if not include_archived:
            query = query.where(Goal.status != GoalStatus.ARCHIVED)
        result = await self.db.execute(query.order_by(Goal.created_at.desc()))
        return [self.serialize_goal(goal) for goal in result.scalars().all()]

    async def get_goal(self, goal_id: str) -> dict:
        return self.serialize_goal(await self._get_goal(goal_id))

    async def create_goal(self, data: dict) -> dict:
        goal = Goal(
            id=str(uuid.uuid4()),
            title=data["title"].strip(),
            definition_of_done=data["definition_of_done"].strip(),
            deadline=data["deadline"],
            importance=Priority(data.get("importance", Priority.MEDIUM)),
            weekly_capacity_minutes=data.get("weekly_capacity_minutes", 0),
            status=GoalStatus.ACTIVE,
            version=1,
        )
        self.db.add(goal)
        await self.db.commit()
        await self.db.refresh(goal)
        logger.info("Created goal %s", goal.id)
        return self.serialize_goal(goal)

    async def update_goal(
        self,
        goal_id: str,
        data: dict,
        expected_version: int | None = None,
    ) -> dict:
        goal = await self._get_goal(goal_id)
        self._check_version(goal, expected_version)
        if data.get("deadline"):
            new_deadline = date.fromisoformat(data["deadline"])
            result = await self.db.execute(
                select(PlanItem).where(PlanItem.goal_id == goal_id)
            )
            for item in result.scalars().all():
                item_date = item.planned_for or item.period_start
                if item_date and date.fromisoformat(item_date) > new_deadline:
                    raise PlanningConflictError(
                        "Move plan items that fall after the new deadline first"
                    )
        for field in (
            "title",
            "definition_of_done",
            "deadline",
            "weekly_capacity_minutes",
        ):
            if field in data:
                setattr(goal, field, data[field].strip() if isinstance(data[field], str) else data[field])
        if "importance" in data:
            goal.importance = Priority(data["importance"])
        self._touch(goal)
        await self.db.commit()
        await self.db.refresh(goal)
        return self.serialize_goal(goal)

    async def complete_goal(
        self, goal_id: str, expected_version: int | None = None
    ) -> dict:
        goal = await self._get_goal(goal_id)
        self._check_version(goal, expected_version)
        result = await self.db.execute(
            select(PlanItem.id).where(
                PlanItem.goal_id == goal_id,
                PlanItem.status == PlanItemStatus.OPEN,
            ).limit(1)
        )
        if result.scalar_one_or_none() is not None:
            raise PlanningConflictError("Goal still has open plan items")
        goal.status = GoalStatus.COMPLETED
        self._touch(goal)
        await self.db.commit()
        await self.db.refresh(goal)
        return self.serialize_goal(goal)

    async def archive_goal(
        self, goal_id: str, expected_version: int | None = None
    ) -> dict:
        goal = await self._get_goal(goal_id)
        self._check_version(goal, expected_version)
        active_result = await self.db.execute(
            select(Session.id)
            .join(PlanItem, Session.task_id == PlanItem.id)
            .where(
                PlanItem.goal_id == goal_id,
                Session.state.in_([SessionState.RUNNING, SessionState.PAUSED]),
            )
            .limit(1)
        )
        if active_result.scalar_one_or_none() is not None:
            raise PlanningConflictError("Cancel or complete the active session first")
        goal.status = GoalStatus.ARCHIVED
        self._touch(goal)
        await self.db.commit()
        await self.db.refresh(goal)
        return self.serialize_goal(goal)

    async def delete_goal(
        self, goal_id: str, expected_version: int | None = None
    ) -> dict:
        goal = await self._get_goal(goal_id)
        self._check_version(goal, expected_version)
        active_result = await self.db.execute(
            select(Session.id)
            .join(PlanItem, Session.task_id == PlanItem.id)
            .where(
                PlanItem.goal_id == goal_id,
                Session.state.in_([SessionState.RUNNING, SessionState.PAUSED]),
            )
            .limit(1)
        )
        if active_result.scalar_one_or_none() is not None:
            raise PlanningConflictError("Cancel or complete the active session first")

        item_result = await self.db.execute(
            select(PlanItem).where(PlanItem.goal_id == goal_id)
        )
        deleted_structure = 0
        moved_to_inbox = 0
        retained_history = 0
        for item in item_result.scalars().all():
            if item.horizon != PlanHorizon.DAY:
                await self.db.delete(item)
                deleted_structure += 1
                continue
            item.goal_id = None
            item.parent_id = None
            if item.status == PlanItemStatus.OPEN:
                item.planned_for = None
                moved_to_inbox += 1
            else:
                retained_history += 1
            self._touch(item)

        draft_result = await self.db.execute(
            select(PlanDraft).where(PlanDraft.goal_id == goal_id)
        )
        for draft in draft_result.scalars().all():
            await self.db.delete(draft)
        await self.db.delete(goal)
        await self.db.commit()
        logger.info("Deleted goal %s while retaining daily history", goal_id)
        return {
            "deleted_goal_id": goal_id,
            "deleted_structure_items": deleted_structure,
            "moved_to_inbox": moved_to_inbox,
            "retained_history_items": retained_history,
        }

    async def list_plan_items(
        self,
        goal_id: str | None = None,
        horizon: PlanHorizon | None = None,
        status: PlanItemStatus | None = None,
        inbox: bool = False,
    ) -> list[dict]:
        query = select(PlanItem)
        if inbox:
            query = query.where(
                PlanItem.horizon == PlanHorizon.DAY,
                PlanItem.goal_id.is_(None),
                PlanItem.planned_for.is_(None),
            )
            if status is None:
                query = query.where(PlanItem.status == PlanItemStatus.OPEN)
        if goal_id is not None:
            query = query.where(PlanItem.goal_id == goal_id)
        if horizon is not None:
            query = query.where(PlanItem.horizon == horizon)
        if status is not None:
            query = query.where(PlanItem.status == status)
        result = await self.db.execute(query.order_by(PlanItem.created_at.desc()))
        return [self.serialize_plan_item(item) for item in result.scalars().all()]

    async def get_plan_item(self, item_id: str) -> dict:
        return self.serialize_plan_item(await self._get_item(item_id))

    @staticmethod
    def _validate_date(value: str | None, field: str) -> None:
        if value is None:
            return
        try:
            date.fromisoformat(value)
        except ValueError as error:
            raise PlanningError(f"{field} must be an ISO local date") from error

    async def _validate_item(self, data: dict, item_id: str | None = None) -> None:
        horizon = PlanHorizon(data["horizon"])
        goal_id = data.get("goal_id")
        parent_id = data.get("parent_id")
        planned_for = data.get("planned_for")
        period_start = data.get("period_start")
        estimate = data.get("estimate_minutes")

        self._validate_date(planned_for, "planned_for")
        self._validate_date(period_start, "period_start")

        goal = None
        if goal_id:
            goal = await self._get_goal(goal_id)
            if goal.status != GoalStatus.ACTIVE:
                raise PlanningConflictError("Plan items can only be added to an active goal")

        if horizon == PlanHorizon.MONTH:
            if not goal_id or parent_id:
                raise PlanningError("A monthly item requires a goal and no parent")
            if not period_start or planned_for:
                raise PlanningError("A monthly item requires period_start and no planned_for")
            if date.fromisoformat(period_start).day != 1:
                raise PlanningError("Monthly period_start must be the first day of a month")
        elif horizon == PlanHorizon.WEEK:
            if not goal_id or not parent_id:
                raise PlanningError("A weekly item requires a goal and monthly parent")
            if not period_start or planned_for:
                raise PlanningError("A weekly item requires period_start and no planned_for")
            if date.fromisoformat(period_start).weekday() != 0:
                raise PlanningError("Weekly period_start must be a Monday")
        else:
            if period_start:
                raise PlanningError("A daily item cannot have period_start")
            if not goal_id and parent_id:
                raise PlanningError("An unlinked daily item cannot have a parent")
            if goal_id and planned_for and not parent_id:
                raise PlanningError(
                    "A scheduled goal-linked daily item requires a weekly parent"
                )
            if parent_id and not planned_for:
                raise PlanningError("A daily item with a weekly parent requires planned_for")

        if horizon != PlanHorizon.DAY and estimate is not None:
            raise PlanningError("Only daily items can have an estimate")
        if estimate is not None and not 5 <= estimate <= 120:
            raise PlanningError("Estimate must be between 5 and 120 minutes")

        if parent_id:
            if parent_id == item_id:
                raise PlanningError("A plan item cannot be its own parent")
            parent = await self._get_item(parent_id)
            expected_parent = {
                PlanHorizon.WEEK: PlanHorizon.MONTH,
                PlanHorizon.DAY: PlanHorizon.WEEK,
            }[horizon]
            if parent.horizon != expected_parent:
                raise PlanningError(
                    f"A {horizon.value} item requires a {expected_parent.value} parent"
                )
            if parent.goal_id != goal_id:
                raise PlanningError("Parent and child must belong to the same goal")
            if parent.status != PlanItemStatus.OPEN:
                raise PlanningConflictError("Parent plan item is not open")
            if horizon == PlanHorizon.DAY:
                week_start = date.fromisoformat(parent.period_start)
                day_date = date.fromisoformat(planned_for)
                if not week_start <= day_date <= week_start + timedelta(days=6):
                    raise PlanningError("Daily planned_for must fall within its parent week")
            elif horizon == PlanHorizon.WEEK:
                month_start = date.fromisoformat(parent.period_start)
                next_month = (
                    date(month_start.year + 1, 1, 1)
                    if month_start.month == 12
                    else date(month_start.year, month_start.month + 1, 1)
                )
                week_start = date.fromisoformat(period_start)
                if week_start + timedelta(days=6) < month_start or week_start >= next_month:
                    raise PlanningError("Weekly period must overlap its parent month")

        if goal:
            goal_deadline = date.fromisoformat(goal.deadline)
            candidate_date = planned_for or period_start
            if candidate_date and date.fromisoformat(candidate_date) > goal_deadline:
                raise PlanningError("Plan item cannot start after the goal deadline")

    async def create_plan_item(self, data: dict) -> dict:
        await self._validate_item(data)
        item = PlanItem(
            id=str(uuid.uuid4()),
            goal_id=data.get("goal_id"),
            parent_id=data.get("parent_id"),
            horizon=PlanHorizon(data["horizon"]),
            name=data["title"].strip(),
            priority=Priority(data.get("importance", Priority.MEDIUM)),
            deadline=data.get("deadline") or "",
            planned_for=data.get("planned_for"),
            period_start=data.get("period_start"),
            estimated_duration=data.get("estimate_minutes"),
            status=PlanItemStatus.OPEN,
            completed=False,
            version=1,
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        logger.info("Created %s plan item %s", item.horizon.value, item.id)
        return self.serialize_plan_item(item)

    async def update_plan_item(
        self,
        item_id: str,
        data: dict,
        expected_version: int | None = None,
    ) -> dict:
        item = await self._get_item(item_id)
        self._check_version(item, expected_version)

        structural_fields = {"goal_id", "parent_id", "horizon"}
        if structural_fields.intersection(data):
            child_result = await self.db.execute(
                select(PlanItem.id).where(PlanItem.parent_id == item_id).limit(1)
            )
            if child_result.scalar_one_or_none() is not None:
                raise PlanningConflictError("Move child items before changing this parent")

        candidate = {
            "goal_id": item.goal_id,
            "parent_id": item.parent_id,
            "horizon": self._enum_value(item.horizon),
            "planned_for": item.planned_for,
            "period_start": item.period_start,
            "estimate_minutes": item.estimated_duration,
        }
        candidate.update(data)
        await self._validate_item(candidate, item_id=item_id)

        if "period_start" in data and item.horizon in {
            PlanHorizon.MONTH,
            PlanHorizon.WEEK,
        }:
            child_result = await self.db.execute(
                select(PlanItem).where(PlanItem.parent_id == item_id)
            )
            children = list(child_result.scalars().all())
            new_start = date.fromisoformat(data["period_start"])
            if item.horizon == PlanHorizon.MONTH:
                next_month = (
                    date(new_start.year + 1, 1, 1)
                    if new_start.month == 12
                    else date(new_start.year, new_start.month + 1, 1)
                )
                for child in children:
                    child_start = date.fromisoformat(child.period_start)
                    if child_start + timedelta(days=6) < new_start or child_start >= next_month:
                        raise PlanningConflictError(
                            "Move weekly outcomes before changing the milestone month"
                        )
            else:
                week_end = new_start + timedelta(days=6)
                for child in children:
                    if child.planned_for is None:
                        continue
                    child_date = date.fromisoformat(child.planned_for)
                    if not new_start <= child_date <= week_end:
                        raise PlanningConflictError(
                            "Move daily tasks before changing the weekly start"
                        )

        field_map = {
            "title": "name",
            "goal_id": "goal_id",
            "parent_id": "parent_id",
            "planned_for": "planned_for",
            "period_start": "period_start",
            "deadline": "deadline",
            "estimate_minutes": "estimated_duration",
        }
        for source, target in field_map.items():
            if source in data:
                value = data[source]
                setattr(item, target, value.strip() if isinstance(value, str) else value)
        if "horizon" in data:
            item.horizon = PlanHorizon(data["horizon"])
        if "importance" in data:
            item.priority = Priority(data["importance"])
        self._touch(item)
        await self.db.commit()
        await self.db.refresh(item)
        return self.serialize_plan_item(item)

    async def complete_plan_item(
        self,
        item_id: str,
        expected_version: int | None = None,
        *,
        source: str = "ui",
        idempotency_key: str | None = None,
        action_context: dict | None = None,
    ) -> dict:
        item = await self._get_item(item_id)
        self._check_version(item, expected_version)
        await self._ensure_no_active_session(item)
        result = await self.db.execute(
            select(PlanItem.id).where(
                PlanItem.parent_id == item_id,
                PlanItem.status == PlanItemStatus.OPEN,
            ).limit(1)
        )
        if result.scalar_one_or_none() is not None:
            raise PlanningConflictError("Plan item still has open children")
        item.status = PlanItemStatus.COMPLETED
        item.completed = True
        self._touch(item)
        await self.db.commit()
        await self.db.refresh(item)
        completed_item = self.serialize_plan_item(item)
        completed_item_id = item.id
        completed_item_name = item.name
        if item.horizon == PlanHorizon.DAY:
            from app.models.models import UserActionSource, UserActionType
            from app.services.habit_service import EventSpec, capture_behavior_events

            await capture_behavior_events(self.db, [EventSpec(
                UserActionType.TASK_COMPLETED,
                UserActionSource(source),
                "task",
                item.id,
                idempotency_key or f"task:{item.id}:completed",
                action_context or {},
            )])
        elif item.horizon == PlanHorizon.MONTH:
            # A monthly milestone is intentionally the smallest automatic
            # episode boundary. Ordinary task/session completion never creates
            # relationship memory, and failure here cannot undo plan progress.
            try:
                from app.services.relationship_memory_service import RelationshipMemoryService

                await RelationshipMemoryService(self.db).capture_milestone(
                    summary=f"Completed milestone: {completed_item_name}",
                    entity_type="plan_item",
                    entity_id=completed_item_id,
                    source_reference=f"plan_item:{completed_item_id}:milestone_completed",
                )
            except Exception as error:
                await self.db.rollback()
                logger.warning(
                    "relationship_episode_capture_failed item_id=%s type=%s",
                    completed_item_id,
                    type(error).__name__,
                )
        return completed_item

    async def drop_plan_item(
        self, item_id: str, expected_version: int | None = None
    ) -> dict:
        item = await self._get_item(item_id)
        self._check_version(item, expected_version)
        await self._ensure_no_active_session(item)
        result = await self.db.execute(
            select(PlanItem.id).where(
                PlanItem.parent_id == item_id,
                PlanItem.status == PlanItemStatus.OPEN,
            ).limit(1)
        )
        if result.scalar_one_or_none() is not None:
            raise PlanningConflictError("Plan item still has open children")
        item.status = PlanItemStatus.DROPPED
        item.completed = False
        self._touch(item)
        await self.db.commit()
        await self.db.refresh(item)
        return self.serialize_plan_item(item)

    async def move_to_inbox(
        self, item_id: str, expected_version: int | None = None
    ) -> dict:
        item = await self._get_item(item_id)
        self._check_version(item, expected_version)
        if item.horizon != PlanHorizon.DAY:
            raise PlanningError("Only daily items can move to Inbox")
        await self._ensure_no_active_session(item)
        item.goal_id = None
        item.parent_id = None
        item.planned_for = None
        item.status = PlanItemStatus.OPEN
        item.completed = False
        self._touch(item)
        await self.db.commit()
        await self.db.refresh(item)
        return self.serialize_plan_item(item)

    async def reschedule_plan_item(
        self,
        item_id: str,
        planned_for: str,
        expected_version: int | None = None,
    ) -> dict:
        item = await self._get_item(item_id)
        self._check_version(item, expected_version)
        if item.horizon != PlanHorizon.DAY:
            raise PlanningError("Only daily items can be rescheduled")
        await self._ensure_no_active_session(item)
        candidate = {
            "goal_id": item.goal_id,
            "parent_id": item.parent_id,
            "horizon": PlanHorizon.DAY,
            "planned_for": planned_for,
            "period_start": None,
            "estimate_minutes": item.estimated_duration,
        }
        await self._validate_item(candidate, item_id=item_id)
        item.planned_for = planned_for
        item.status = PlanItemStatus.OPEN
        item.completed = False
        self._touch(item)
        await self.db.commit()
        await self.db.refresh(item)
        return self.serialize_plan_item(item)

    async def _ensure_no_active_session(self, item: PlanItem) -> None:
        if item.horizon != PlanHorizon.DAY:
            return
        result = await self.db.execute(
            select(Session.id).where(
                Session.task_id == item.id,
                Session.state.in_([SessionState.RUNNING, SessionState.PAUSED]),
            ).limit(1)
        )
        if result.scalar_one_or_none() is not None:
            raise PlanningConflictError("Cancel or complete the active session first")

    async def get_progress(
        self, goal_id: str | None = None, item_id: str | None = None
    ) -> dict:
        if (goal_id is None) == (item_id is None):
            raise PlanningError("Provide exactly one of goal_id or item_id")

        root_item = None
        if goal_id:
            await self._get_goal(goal_id)
            result = await self.db.execute(
                select(PlanItem).where(PlanItem.goal_id == goal_id)
            )
            candidates = list(result.scalars().all())
        else:
            root_item = await self._get_item(item_id)
            if root_item.goal_id:
                result = await self.db.execute(
                    select(PlanItem).where(PlanItem.goal_id == root_item.goal_id)
                )
                candidates = list(result.scalars().all())
            else:
                candidates = [root_item]

        if root_item:
            descendant_ids = {root_item.id}
            changed = True
            while changed:
                changed = False
                for candidate in candidates:
                    if (
                        candidate.parent_id in descendant_ids
                        and candidate.id not in descendant_ids
                    ):
                        descendant_ids.add(candidate.id)
                        changed = True
            items = [item for item in candidates if item.id in descendant_ids]
        else:
            items = candidates

        daily_items = [item for item in items if item.horizon == PlanHorizon.DAY]
        task_ids = [item.id for item in daily_items]
        sessions = []
        if task_ids:
            result = await self.db.execute(
                select(Session).where(
                    Session.task_id.in_(task_ids),
                    Session.state == SessionState.COMPLETED,
                )
            )
            sessions = list(result.scalars().all())

        focus_seconds = sum(
            max(0, (session.duration or 0) - (session.penalty_seconds or 0))
            for session in sessions
        )
        planned_minutes = sum(
            item.estimated_duration or 0
            for item in daily_items
            if item.status != PlanItemStatus.DROPPED
        )
        completed_count = sum(
            1 for item in daily_items if item.status == PlanItemStatus.COMPLETED
        )
        return {
            "goal_id": goal_id or root_item.goal_id,
            "item_id": item_id,
            "planned_minutes": planned_minutes,
            "actual_focus_minutes": round(focus_seconds / 60, 2),
            "focus_session_count": len(sessions),
            "completed_daily_task_count": completed_count,
            "daily_task_count": len(
                [item for item in daily_items if item.status != PlanItemStatus.DROPPED]
            ),
        }
