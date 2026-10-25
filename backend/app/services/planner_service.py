from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import uuid

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    GoalStatus,
    PlanDraft,
    PlanDraftStatus,
    PlanHorizon,
    PlanItem,
    PlanItemStatus,
)
from app.services.ai_service import (
    ModelFactory,
    ProviderError,
    provider_failure_diagnostics,
    provider_model_name,
)
from app.services.planning_schemas import (
    CapacitySummary,
    DraftItem,
    DraftApprovalRequest,
    DraftRegenerateRequest,
    PlannerBranchPayload,
    PlannerDraftPayload,
    PlannerRequest,
)
from app.services.planning_service import (
    PlanningConflictError,
    PlanningError,
    PlanningNotFoundError,
    PlanningService,
)
from app.utils.logger import error_logger


PLANNER_SYSTEM_PROMPT = """You create conservative, executable long-term plans.
Return only the requested structured object. Build monthly outcome milestones through the goal
deadline, weekly outcomes only for the nearest 2-4 weeks, and daily actions only for the current
ISO week. Monthly and weekly items are outcomes, never actions. Keep every daily estimate within
the requested session duration when practical. State assumptions explicitly when topics are
missing. Never change the goal deadline or definition of done.
Use null (not an invented value) for fields that do not apply: month items have no parent,
planned_for, or estimate_minutes; week items have no planned_for or estimate_minutes; day items
have no period_start. Monthly period_start is the first day of its month. Weekly period_start is
a Monday. Every day item is inside its parent week. Client IDs use only letters, digits, dot,
underscore, colon, or hyphen."""

PLANNER_BRANCH_SYSTEM_PROMPT = """Regenerate only the requested planning branch.
Return the selected milestone or week as the root plus only its descendants. Preserve the supplied
root client_id, parent_client_id and horizon exactly. Use fresh unique client IDs for replacement
descendants. Monthly and weekly items are outcomes; daily items are executable actions. Only the
current ISO week may contain daily actions. Never change the goal deadline or definition of done."""

# Keep Gemini's constrained-decoding schema deliberately small. The provider rejects complex
# Pydantic schemas with large array bounds and too many optional branches before generation.
GEMINI_DRAFT_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "client_id": {"type": "string"},
        "parent_client_id": {"type": ["string", "null"]},
        "horizon": {"type": "string", "enum": ["month", "week", "day"]},
        "title": {"type": "string"},
        "period_start": {"type": ["string", "null"]},
        "planned_for": {"type": ["string", "null"]},
        "estimate_minutes": {"type": ["integer", "null"]},
    },
    "required": [
        "client_id",
        "parent_client_id",
        "horizon",
        "title",
        "period_start",
        "planned_for",
        "estimate_minutes",
    ],
}

GEMINI_DRAFT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "integer", "enum": [1]},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "items": {"type": "array", "items": GEMINI_DRAFT_ITEM_SCHEMA},
    },
    "required": ["schema_version", "assumptions", "items"],
}

GEMINI_BRANCH_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "items": {"type": "array", "items": GEMINI_DRAFT_ITEM_SCHEMA},
    },
    "required": ["assumptions", "items"],
}


class PlannerService:
    def __init__(
        self,
        db: AsyncSession,
        today: date | None = None,
        request_id: str = "unknown",
    ):
        self.db = db
        self.today = today or date.today()
        self.request_id = request_id
        self.planning = PlanningService(db)

    def _log_ai_failure(self, provider: str, operation: str, error: BaseException) -> None:
        details = provider_failure_diagnostics(error)
        validation_issues = "none"
        if isinstance(error, ValidationError):
            validation_issues = ",".join(
                f"{'.'.join(str(part) for part in issue['loc'])}:{issue['type']}"
                for issue in error.errors(include_url=False, include_context=False, include_input=False)[:8]
            ) or "unknown"
        error_logger.error(
            "ai_planner_failure request_id=%s provider=%s model=%s operation=%s "
            "category=%s status=%s reason=%s domain=%s error_types=%s "
            "validation_issues=%s trace=%s",
            self.request_id,
            provider,
            provider_model_name(provider),
            operation,
            details["category"],
            details["status"],
            details["reason"],
            details["domain"],
            details["error_types"],
            validation_issues,
            details["trace"],
        )

    @staticmethod
    def _structured_output(model, schema, provider: str):
        # Gemini's native JSON schema mode constrains the response before Pydantic parses it.
        # Use a flat transport schema here, then enforce all domain rules with Pydantic.
        if provider == "gemini":
            transport_schema = (
                GEMINI_BRANCH_RESPONSE_SCHEMA
                if schema is PlannerBranchPayload
                else GEMINI_DRAFT_RESPONSE_SCHEMA
            )
            return model.with_structured_output(transport_schema, method="json_schema")
        return model.with_structured_output(schema)

    @staticmethod
    def _json(model) -> str:
        return model.model_dump_json()

    def _capacity(self, request: PlannerRequest, draft: PlannerDraftPayload) -> CapacitySummary:
        available = len(request.available_weekdays) * request.minutes_per_day
        limit = int(available * 0.8)
        planned = sum(item.estimate_minutes or 0 for item in draft.items if item.horizon == "day")
        return CapacitySummary(
            available_minutes=available,
            planning_limit_minutes=limit,
            planned_minutes=planned,
            over_capacity=planned > limit,
        )

    def _validate_window(self, draft: PlannerDraftPayload, deadline: str) -> None:
        goal_deadline = date.fromisoformat(deadline)
        week_start = self.today - timedelta(days=self.today.weekday())
        week_end = week_start + timedelta(days=6)
        detailed_week_limit = week_start + timedelta(weeks=4)
        for item in draft.items:
            item_date = date.fromisoformat(item.planned_for or item.period_start)
            if item_date > goal_deadline:
                raise PlanningError("Draft contains an item after the goal deadline")
            if item.horizon == "week" and item_date >= detailed_week_limit:
                raise PlanningError("Weekly detail is limited to the nearest four weeks")
            if item.horizon == "day" and not week_start <= item_date <= week_end:
                raise PlanningError("Daily detail is limited to the current ISO week")

    async def _invoke(self, request: PlannerRequest, goal) -> PlannerDraftPayload:
        prompt = {
            "today": self.today.isoformat(),
            "goal": {
                "title": goal.title,
                "definition_of_done": goal.definition_of_done,
                "deadline": goal.deadline,
                "importance": goal.importance.value,
            },
            "current_state": request.current_state,
            "weaknesses": request.weaknesses,
            "topics": request.topics,
            "available_weekdays": request.available_weekdays,
            "minutes_per_day": request.minutes_per_day,
            "default_session_duration": request.default_session_duration,
            "capacity_policy": "Plan no more than 80% of weekly availability.",
        }
        try:
            model = ModelFactory.create(
                request.provider,
                max_tokens=3000,
                temperature=0.2,
            )
            structured = self._structured_output(model, PlannerDraftPayload, request.provider)
            result = await structured.ainvoke([
                SystemMessage(PLANNER_SYSTEM_PROMPT),
                HumanMessage(json.dumps(prompt, ensure_ascii=False)),
            ])
            return result if isinstance(result, PlannerDraftPayload) else PlannerDraftPayload.model_validate(result)
        except ValidationError as error:
            self._log_ai_failure(request.provider, "generate", error)
            raise PlanningError("AI returned a draft that does not match the planning schema") from error
        except ProviderError as error:
            self._log_ai_failure(request.provider, "generate", error)
            raise
        except Exception as error:
            self._log_ai_failure(request.provider, "generate", error)
            raise ProviderError(f"{request.provider.title()} planner is unavailable") from error

    async def _invoke_branch(
        self,
        request: PlannerRequest,
        goal,
        target,
        branch_items: list,
    ) -> PlannerBranchPayload:
        prompt = {
            "today": self.today.isoformat(),
            "goal": {
                "title": goal.title,
                "definition_of_done": goal.definition_of_done,
                "deadline": goal.deadline,
            },
            "planner_input": request.model_dump(exclude={"provider"}),
            "selected_root": target.model_dump(),
            "current_branch": [item.model_dump() for item in branch_items],
            "capacity_policy": "Plan no more than 80% of weekly availability.",
        }
        try:
            model = ModelFactory.create(request.provider, max_tokens=1800, temperature=0.3)
            structured = self._structured_output(model, PlannerBranchPayload, request.provider)
            result = await structured.ainvoke([
                SystemMessage(PLANNER_BRANCH_SYSTEM_PROMPT),
                HumanMessage(json.dumps(prompt, ensure_ascii=False)),
            ])
            return result if isinstance(result, PlannerBranchPayload) else PlannerBranchPayload.model_validate(result)
        except ValidationError as error:
            self._log_ai_failure(request.provider, "regenerate_branch", error)
            raise PlanningError("AI returned a branch that does not match the planning schema") from error
        except ProviderError as error:
            self._log_ai_failure(request.provider, "regenerate_branch", error)
            raise
        except Exception as error:
            self._log_ai_failure(request.provider, "regenerate_branch", error)
            raise ProviderError(f"{request.provider.title()} planner is unavailable") from error

    @staticmethod
    def _subtree_ids(items: list, root_id: str) -> set[str]:
        subtree = {root_id}
        changed = True
        while changed:
            before = len(subtree)
            subtree.update(item.client_id for item in items if item.parent_client_id in subtree)
            changed = len(subtree) != before
        return subtree

    async def generate(self, goal_id: str, request: PlannerRequest) -> dict:
        goal = await self.planning._get_goal(goal_id)
        if goal.status != GoalStatus.ACTIVE:
            raise PlanningConflictError("Only active goals can be planned")
        draft = await self._invoke(request, goal)
        self._validate_window(draft, goal.deadline)
        record = PlanDraft(
            id=str(uuid.uuid4()),
            goal_id=goal.id,
            goal_version=goal.version,
            schema_version=draft.schema_version,
            input_payload=self._json(request),
            payload=self._json(draft),
            status=PlanDraftStatus.DRAFT,
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return self._serialize(record)

    async def _get(self, draft_id: str) -> PlanDraft:
        result = await self.db.execute(select(PlanDraft).where(PlanDraft.id == draft_id))
        record = result.scalar_one_or_none()
        if record is None:
            raise PlanningNotFoundError("Plan draft not found")
        return record

    def _serialize(self, record: PlanDraft) -> dict:
        request = PlannerRequest.model_validate_json(record.input_payload)
        draft = PlannerDraftPayload.model_validate_json(record.payload)
        return {
            "id": record.id,
            "goal_id": record.goal_id,
            "goal_version": record.goal_version,
            "status": record.status.value,
            "input": request.model_dump(),
            "draft": draft.model_dump(),
            "capacity": self._capacity(request, draft).model_dump(),
            "approval_result": json.loads(record.approval_result) if record.approval_result else None,
        }

    async def get(self, draft_id: str) -> dict:
        return self._serialize(await self._get(draft_id))

    async def update(self, draft_id: str, draft: PlannerDraftPayload) -> dict:
        record = await self._get(draft_id)
        if record.status != PlanDraftStatus.DRAFT:
            raise PlanningConflictError("Only an open draft can be edited")
        goal = await self.planning._get_goal(record.goal_id)
        self._validate_window(draft, goal.deadline)
        record.payload = self._json(draft)
        record.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(record)
        return self._serialize(record)

    async def regenerate_branch(
        self,
        draft_id: str,
        request: DraftRegenerateRequest,
    ) -> dict:
        record = await self._get(draft_id)
        if record.status != PlanDraftStatus.DRAFT:
            raise PlanningConflictError("Only an open draft can be regenerated")
        goal = await self.planning._get_goal(record.goal_id)
        if goal.version != record.goal_version or goal.status != GoalStatus.ACTIVE:
            raise PlanningConflictError("Goal changed after this draft was generated")
        current = request.draft or PlannerDraftPayload.model_validate_json(record.payload)
        self._validate_window(current, goal.deadline)
        target = next((item for item in current.items if item.client_id == request.client_id), None)
        if target is None:
            raise PlanningNotFoundError("Draft branch not found")
        if target.horizon == "day":
            raise PlanningError("Only a monthly milestone or weekly outcome can be regenerated")

        subtree_ids = self._subtree_ids(current.items, target.client_id)
        branch_items = [item for item in current.items if item.client_id in subtree_ids]
        planner_input = PlannerRequest.model_validate_json(record.input_payload)
        replacement = await self._invoke_branch(planner_input, goal, target, branch_items)
        replacement_root = next(
            (item for item in replacement.items if item.client_id == target.client_id),
            None,
        )
        if (
            replacement_root is None
            or replacement_root.horizon != target.horizon
            or replacement_root.parent_client_id != target.parent_client_id
        ):
            raise PlanningError("Regenerated branch must preserve its root identity and parent")

        replacement_ids = {item.client_id for item in replacement.items}
        protected_ids = {item.client_id for item in current.items} - subtree_ids
        if replacement_ids & protected_ids:
            raise PlanningError("Regenerated branch reuses an ID outside the selected branch")
        if self._subtree_ids(replacement.items, target.client_id) != replacement_ids:
            raise PlanningError("Regenerated branch contains disconnected items")

        merged_items = []
        for item in current.items:
            if item.client_id == target.client_id:
                merged_items.extend(replacement.items)
            elif item.client_id not in subtree_ids:
                merged_items.append(item)
        assumptions = list(dict.fromkeys([*current.assumptions, *replacement.assumptions]))
        merged = PlannerDraftPayload(
            schema_version=current.schema_version,
            assumptions=assumptions[:30],
            items=merged_items,
        )
        self._validate_window(merged, goal.deadline)
        record.payload = self._json(merged)
        record.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(record)
        return self._serialize(record)

    async def regenerate_approved_week(
        self,
        week_item_id: str,
        provider: str,
    ) -> dict:
        """Replace open daily actions in the current approved week after confirmation."""
        week = await self.planning._get_item(week_item_id)
        if week.horizon != PlanHorizon.WEEK or week.status != PlanItemStatus.OPEN:
            raise PlanningConflictError("The selected weekly plan is no longer open")
        current_week_start = self.today - timedelta(days=self.today.weekday())
        if week.period_start != current_week_start.isoformat():
            raise PlanningError("Only the current week can be regenerated")

        goal = await self.planning._get_goal(week.goal_id)
        if goal.status != GoalStatus.ACTIVE:
            raise PlanningConflictError("Only an active goal can be replanned")

        result = await self.db.execute(
            select(PlanItem)
            .where(PlanItem.parent_id == week.id)
            .order_by(PlanItem.created_at.asc())
        )
        children = list(result.scalars().all())
        open_children = [item for item in children if item.status == PlanItemStatus.OPEN]
        target = DraftItem(
            client_id=week.id,
            parent_client_id=week.parent_id,
            horizon="week",
            title=week.name,
            period_start=week.period_start,
        )
        branch_items = [
            target,
            *[
                DraftItem(
                    client_id=item.id,
                    parent_client_id=week.id,
                    horizon="day",
                    title=item.name,
                    planned_for=item.planned_for,
                    estimate_minutes=item.estimated_duration,
                )
                for item in open_children
            ],
        ]

        draft_result = await self.db.execute(
            select(PlanDraft)
            .where(
                PlanDraft.goal_id == goal.id,
                PlanDraft.status == PlanDraftStatus.APPROVED,
            )
            .order_by(PlanDraft.approved_at.desc())
            .limit(1)
        )
        latest_draft = draft_result.scalar_one_or_none()
        if latest_draft is not None:
            planner_input = PlannerRequest.model_validate_json(latest_draft.input_payload)
            planner_input = planner_input.model_copy(update={"provider": provider})
        else:
            daily_minutes = max(5, min(720, (goal.weekly_capacity_minutes or 420) // 7))
            planner_input = PlannerRequest(
                provider=provider,
                current_state="Regenerate the current approved week.",
                available_weekdays=list(range(7)),
                minutes_per_day=daily_minutes,
                default_session_duration=min(25, daily_minutes),
            )

        replacement = await self._invoke_branch(
            planner_input,
            goal,
            target,
            branch_items,
        )
        replacement_root = next(
            (item for item in replacement.items if item.client_id == week.id),
            None,
        )
        if (
            replacement_root is None
            or replacement_root.horizon != "week"
            or replacement_root.parent_client_id != week.parent_id
        ):
            raise PlanningError("Regenerated week must preserve its root")

        new_days = [item for item in replacement.items if item.client_id != week.id]
        if not new_days:
            raise PlanningError("Regenerated week must contain at least one daily action")
        if any(
            item.horizon != "day" or item.parent_client_id != week.id
            for item in new_days
        ):
            raise PlanningError("Regenerated week may only contain direct daily actions")
        if len({item.client_id for item in replacement.items}) != len(replacement.items):
            raise PlanningError("Regenerated week contains duplicate IDs")
        week_end = current_week_start + timedelta(days=6)
        for item in new_days:
            if item.planned_for is None or item.estimate_minutes is None:
                raise PlanningError("Regenerated daily actions require a date and estimate")
            planned = date.fromisoformat(item.planned_for)
            if not current_week_start <= planned <= week_end:
                raise PlanningError("Regenerated daily action falls outside the current week")
            if planned > date.fromisoformat(goal.deadline):
                raise PlanningError("Regenerated daily action falls after the goal deadline")
            await self.planning._validate_item(
                {
                    "goal_id": goal.id,
                    "parent_id": week.id,
                    "horizon": PlanHorizon.DAY,
                    "planned_for": item.planned_for,
                    "period_start": None,
                    "estimate_minutes": item.estimate_minutes,
                }
            )

        for item in open_children:
            await self.planning._ensure_no_active_session(item)

        created: list[dict] = []
        try:
            for item in open_children:
                item.status = PlanItemStatus.DROPPED
                item.completed = False
                self.planning._touch(item)
            week.name = replacement_root.title
            self.planning._touch(week)
            for item in new_days:
                entity = PlanItem(
                    id=str(uuid.uuid4()),
                    goal_id=goal.id,
                    parent_id=week.id,
                    horizon=PlanHorizon.DAY,
                    name=item.title,
                    priority=goal.importance,
                    deadline="",
                    planned_for=item.planned_for,
                    period_start=None,
                    estimated_duration=item.estimate_minutes,
                    status=PlanItemStatus.OPEN,
                    completed=False,
                    version=1,
                )
                self.db.add(entity)
                created.append({
                    "id": entity.id,
                    "title": entity.name,
                    "planned_for": entity.planned_for,
                })
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return {
            "regenerated_week_id": week.id,
            "replaced_open_daily_tasks": len(open_children),
            "created_daily_tasks": created,
            "retained_history_tasks": len(children) - len(open_children),
        }

    async def cancel(self, draft_id: str) -> dict:
        record = await self._get(draft_id)
        if record.status == PlanDraftStatus.APPROVED:
            raise PlanningConflictError("An approved draft cannot be cancelled")
        record.status = PlanDraftStatus.CANCELLED
        record.updated_at = datetime.utcnow()
        await self.db.commit()
        return self._serialize(record)

    async def approve(self, draft_id: str, request: DraftApprovalRequest) -> dict:
        record = await self._get(draft_id)
        if record.status == PlanDraftStatus.APPROVED:
            if record.approval_key == request.idempotency_key:
                return self._serialize(record)
            raise PlanningConflictError("Draft has already been approved")
        if record.status != PlanDraftStatus.DRAFT:
            raise PlanningConflictError("Draft is not open")

        duplicate = await self.db.execute(
            select(PlanDraft.id).where(
                PlanDraft.approval_key == request.idempotency_key,
                PlanDraft.id != draft_id,
            )
        )
        if duplicate.scalar_one_or_none() is not None:
            raise PlanningConflictError("Idempotency key has already been used")

        goal = await self.planning._get_goal(record.goal_id)
        if goal.version != record.goal_version or goal.status != GoalStatus.ACTIVE:
            raise PlanningConflictError("Goal changed after this draft was generated")

        draft = request.draft or PlannerDraftPayload.model_validate_json(record.payload)
        planner_input = PlannerRequest.model_validate_json(record.input_payload)
        self._validate_window(draft, goal.deadline)
        capacity = self._capacity(planner_input, draft)
        if capacity.over_capacity and not request.override_capacity:
            raise PlanningConflictError("Draft exceeds the 80% capacity limit")

        id_map = {item.client_id: str(uuid.uuid4()) for item in draft.items}
        created = []
        try:
            for draft_item in draft.items:
                item = PlanItem(
                    id=id_map[draft_item.client_id],
                    goal_id=goal.id,
                    parent_id=id_map.get(draft_item.parent_client_id),
                    horizon=PlanHorizon(draft_item.horizon),
                    name=draft_item.title,
                    priority=goal.importance,
                    deadline="",
                    planned_for=draft_item.planned_for,
                    period_start=draft_item.period_start,
                    estimated_duration=draft_item.estimate_minutes,
                    status=PlanItemStatus.OPEN,
                    completed=False,
                    version=1,
                )
                self.db.add(item)
                created.append({
                    "client_id": draft_item.client_id,
                    "id": item.id,
                    "horizon": draft_item.horizon,
                })
            record.payload = self._json(draft)
            record.status = PlanDraftStatus.APPROVED
            record.approval_key = request.idempotency_key
            record.approval_result = json.dumps({"created_items": created})
            record.approved_at = datetime.utcnow()
            record.updated_at = datetime.utcnow()
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        await self.db.refresh(record)
        return self._serialize(record)
