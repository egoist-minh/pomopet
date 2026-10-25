import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.session_service import SessionService
from app.services.task_service import TaskService
from app.services.ai_service import ProviderError
from app.services.planner_service import PlannerService
from app.services.planning_service import PlanningError, PlanningService


ACTION_EXPIRY_MINUTES = 10
WRITE_TOOL_TIMEOUT_SECONDS = 5
PLANNER_WRITE_TIMEOUT_SECONDS = 45
PLAN_ACTION_TYPES = {
    "update_goal",
    "update_plan_item",
    "reschedule_plan_task",
    "create_daily_plan_task",
    "regenerate_week_plan",
}


class InvalidActionError(ValueError):
    """The model supplied invalid write-tool arguments."""


class ActionConflictError(RuntimeError):
    """The requested write no longer matches current application state."""


class ActionExecutionError(RuntimeError):
    """A confirmed write failed without exposing internal details."""


class ActionTimeoutError(ActionExecutionError):
    """A confirmed write did not finish within its deadline."""


class CreateTaskInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    priority: Literal["high", "medium", "low"] = "medium"
    deadline: str | None = Field(default=None, max_length=40)
    estimated_duration: int | None = Field(default=None, ge=5, le=120)


class CreateTasksInput(BaseModel):
    tasks: list[CreateTaskInput] = Field(min_length=2, max_length=20)


class StartFocusSessionInput(BaseModel):
    task_id: str = Field(min_length=1, max_length=128)
    duration_minutes: int = Field(ge=5, le=120)


class ExtendFocusSessionInput(BaseModel):
    duration_minutes: int = Field(ge=1, le=120)


class TaskIdInput(BaseModel):
    task_id: str = Field(min_length=1, max_length=128)


class UpdateTaskInput(BaseModel):
    task_id: str = Field(min_length=1, max_length=128)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    priority: Literal["high", "medium", "low"] | None = None
    deadline: str | None = Field(default=None, max_length=40)
    estimated_duration: int | None = Field(default=None, ge=5, le=120)

    @model_validator(mode="after")
    def require_update(self) -> "UpdateTaskInput":
        editable_fields = {"name", "priority", "deadline", "estimated_duration"}
        if not self.model_fields_set.intersection(editable_fields):
            raise ValueError("At least one task field must be updated")
        if "name" in self.model_fields_set:
            if self.name is None or not self.name.strip():
                raise ValueError("Task name must not be blank")
        if "priority" in self.model_fields_set and self.priority is None:
            raise ValueError("Task priority must not be null")
        return self


class UpdateGoalInput(BaseModel):
    goal_id: str = Field(min_length=1, max_length=128)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    definition_of_done: str | None = Field(default=None, min_length=1, max_length=1000)
    deadline: str | None = Field(default=None, max_length=10)
    importance: Literal["high", "medium", "low"] | None = None
    weekly_capacity_minutes: int | None = Field(default=None, ge=0, le=10080)

    @model_validator(mode="after")
    def require_update(self) -> "UpdateGoalInput":
        editable = {
            "title", "definition_of_done", "deadline", "importance",
            "weekly_capacity_minutes",
        }
        if not self.model_fields_set.intersection(editable):
            raise ValueError("At least one goal field must be updated")
        for field in ("title", "definition_of_done", "deadline", "importance"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        if self.deadline is not None:
            date.fromisoformat(self.deadline)
        return self


class UpdatePlanItemInput(BaseModel):
    plan_item_id: str = Field(min_length=1, max_length=128)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    importance: Literal["high", "medium", "low"] | None = None
    period_start: str | None = Field(default=None, max_length=10)
    planned_for: str | None = Field(default=None, max_length=10)
    estimate_minutes: int | None = Field(default=None, ge=5, le=120)

    @model_validator(mode="after")
    def require_update(self) -> "UpdatePlanItemInput":
        editable = {
            "title", "importance", "period_start", "planned_for", "estimate_minutes",
        }
        if not self.model_fields_set.intersection(editable):
            raise ValueError("At least one plan field must be updated")
        for field in editable:
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        if self.title is not None and not self.title.strip():
            raise ValueError("Plan item title must not be blank")
        for field in ("period_start", "planned_for"):
            value = getattr(self, field)
            if value is not None:
                date.fromisoformat(value)
        return self


class GoalIdInput(BaseModel):
    goal_id: str = Field(min_length=1, max_length=128)


class ReschedulePlanTaskInput(BaseModel):
    task_id: str = Field(min_length=1, max_length=128)
    planned_for: str = Field(max_length=10)
    weekly_parent_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_date(self) -> "ReschedulePlanTaskInput":
        date.fromisoformat(self.planned_for)
        return self


class CreateDailyPlanTaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    weekly_parent_id: str = Field(min_length=1, max_length=128)
    planned_for: str = Field(max_length=10)
    importance: Literal["high", "medium", "low"] = "medium"
    estimate_minutes: int = Field(default=25, ge=5, le=120)

    @model_validator(mode="after")
    def validate_values(self) -> "CreateDailyPlanTaskInput":
        if not self.title.strip():
            raise ValueError("Daily task title must not be blank")
        date.fromisoformat(self.planned_for)
        return self


class RegenerateWeekPlanInput(BaseModel):
    week_item_id: str = Field(min_length=1, max_length=128)


class EmptyInput(BaseModel):
    pass


class ProductivityActionService:
    def __init__(self, database: AsyncSession, provider: str = "gemini"):
        self.task_service = TaskService(database)
        self.session_service = SessionService(database)
        self.planning_service = PlanningService(database)
        self.planner_service = PlannerService(database)
        self.provider = provider
        self._execution_idempotency_key: str | None = None
        self.tools = self._create_tools()
        self.tools_by_name = {tool.name: tool for tool in self.tools}

    def _create_tools(self) -> list[BaseTool]:
        return [
            StructuredTool.from_function(
                coroutine=self._create_task,
                name="create_task",
                description=(
                    "Prepare exactly one new task. For two or more tasks, use "
                    "create_tasks instead. This requires explicit user confirmation."
                ),
                args_schema=CreateTaskInput,
            ),
            StructuredTool.from_function(
                coroutine=self._create_tasks,
                name="create_tasks",
                description=(
                    "Prepare between 2 and 20 new tasks as one batch. Use this when the "
                    "user asks to create multiple tasks. The whole batch requires one "
                    "explicit user confirmation."
                ),
                args_schema=CreateTasksInput,
            ),
            StructuredTool.from_function(
                coroutine=self._start_focus_session,
                name="start_focus_session",
                description=(
                    "Prepare a focus session for an open task. This requires explicit "
                    "user confirmation before the session starts."
                ),
                args_schema=StartFocusSessionInput,
            ),
            StructuredTool.from_function(
                coroutine=self._pause_focus_session,
                name="pause_focus_session",
                description=(
                    "Prepare to pause the running focus session. This requires explicit "
                    "user confirmation."
                ),
                args_schema=EmptyInput,
            ),
            StructuredTool.from_function(
                coroutine=self._resume_focus_session,
                name="resume_focus_session",
                description=(
                    "Prepare to resume the paused focus session. This requires explicit "
                    "user confirmation."
                ),
                args_schema=EmptyInput,
            ),
            StructuredTool.from_function(
                coroutine=self._extend_focus_session,
                name="extend_focus_session",
                description=(
                    "Prepare to extend the currently running focus session by a user-specified "
                    "number of minutes. Use this when the user asks for more focus time. This "
                    "requires explicit user confirmation."
                ),
                args_schema=ExtendFocusSessionInput,
            ),
            StructuredTool.from_function(
                coroutine=self._complete_task,
                name="complete_task",
                description=(
                    "Prepare to mark an open task complete. This requires explicit user "
                    "confirmation."
                ),
                args_schema=TaskIdInput,
            ),
            StructuredTool.from_function(
                coroutine=self._update_task,
                name="update_task",
                description=(
                    "Prepare changes to one open task. Supply only the fields the user "
                    "asked to change. Use null to clear the deadline or estimated "
                    "duration. This requires explicit user confirmation."
                ),
                args_schema=UpdateTaskInput,
            ),
            StructuredTool.from_function(
                coroutine=self._delete_task,
                name="delete_task",
                description=(
                    "Prepare to permanently delete one open task. This requires "
                    "explicit user confirmation."
                ),
                args_schema=TaskIdInput,
            ),
            StructuredTool.from_function(
                coroutine=self._update_goal,
                name="update_goal",
                description=(
                    "Prepare an update to one existing goal as part of a user-requested plan "
                    "change. First use get_planning_context to resolve the goal ID. Dates "
                    "must be ISO YYYY-MM-DD. Requires confirmation; several plan changes "
                    "may be grouped into one confirmation."
                ),
                args_schema=UpdateGoalInput,
            ),
            StructuredTool.from_function(
                coroutine=self._delete_goal,
                name="delete_goal",
                description=(
                    "Prepare to permanently delete one goal. First use get_planning_context "
                    "to resolve its ID. Requires confirmation."
                ),
                args_schema=GoalIdInput,
            ),
            StructuredTool.from_function(
                coroutine=self._update_plan_item,
                name="update_plan_item",
                description=(
                    "Prepare edits to one monthly milestone, weekly outcome, or daily plan "
                    "task. First use get_planning_context to resolve its exact ID. Month/week "
                    "items accept title, importance, and period_start. Daily items accept title, "
                    "importance, planned_for, and estimate_minutes. Dates must be ISO YYYY-MM-DD. "
                    "Requires confirmation; several plan changes may be grouped together."
                ),
                args_schema=UpdatePlanItemInput,
            ),
            StructuredTool.from_function(
                coroutine=self._reschedule_plan_task,
                name="reschedule_plan_task",
                description=(
                    "Prepare to move one daily plan task, including an Inbox task, to an ISO "
                    "date. First use get_planning_context. For a goal-linked Inbox task, pass "
                    "the matching weekly_parent_id; omit it for a general Inbox task or a task "
                    "that already has a weekly parent. Requires confirmation."
                ),
                args_schema=ReschedulePlanTaskInput,
            ),
            StructuredTool.from_function(
                coroutine=self._create_daily_plan_task,
                name="create_daily_plan_task",
                description=(
                    "Prepare one daily task under an open weekly plan outcome. First use "
                    "get_planning_context to resolve the week ID. Requires confirmation."
                ),
                args_schema=CreateDailyPlanTaskInput,
            ),
            StructuredTool.from_function(
                coroutine=self._regenerate_week_plan,
                name="regenerate_week_plan",
                description=(
                    "Prepare AI regeneration of the current week's open daily tasks. First "
                    "use get_planning_context to resolve the weekly plan ID. Completed history "
                    "is retained. Requires confirmation."
                ),
                args_schema=RegenerateWeekPlanInput,
            ),
        ]

    async def _create_task(
        self,
        name: str,
        priority: str = "medium",
        deadline: str | None = None,
        estimated_duration: int | None = None,
    ) -> dict[str, Any]:
        return await self.task_service.create_task(
            {
                "name": name.strip(),
                "priority": priority,
                "deadline": deadline or "",
                "estimated_duration": estimated_duration,
            }
        )

    async def _create_tasks(
        self,
        tasks: list[CreateTaskInput | dict[str, Any]],
    ) -> dict[str, Any]:
        task_values = [
            task.model_dump() if isinstance(task, CreateTaskInput) else task
            for task in tasks
        ]
        return await self.task_service.create_tasks(
            [
                {
                    "name": task["name"].strip(),
                    "priority": task.get("priority", "medium"),
                    "deadline": task.get("deadline") or "",
                    "estimated_duration": task.get("estimated_duration"),
                }
                for task in task_values
            ]
        )

    async def _start_focus_session(
        self,
        task_id: str,
        duration_minutes: int,
    ) -> dict[str, Any]:
        return await self.session_service.start_session(
            task_id,
            duration_minutes * 60,
            source="chat",
            idempotency_key=self._execution_idempotency_key,
            action_context={"duration_source": "chat"},
        )

    async def _pause_focus_session(self) -> dict[str, Any]:
        return await self.session_service.pause_session()

    async def _resume_focus_session(self) -> dict[str, Any]:
        return await self.session_service.resume_session()

    async def _extend_focus_session(self, duration_minutes: int) -> dict[str, Any]:
        return await self.session_service.extend_session(
            duration_minutes * 60,
            source="chat",
            idempotency_key=self._execution_idempotency_key,
        )

    async def _complete_task(self, task_id: str) -> dict[str, Any]:
        return await self.task_service.complete_task(
            task_id,
            source="chat",
            idempotency_key=self._execution_idempotency_key,
        )

    async def _update_task(self, task_id: str, **updates: Any) -> dict[str, Any]:
        if "name" in updates:
            updates["name"] = updates["name"].strip()
        return await self.task_service.update_task(task_id, updates)

    async def _delete_task(self, task_id: str) -> dict[str, Any]:
        return await self.task_service.delete_task(task_id)

    async def _update_goal(self, goal_id: str, **updates: Any) -> dict[str, Any]:
        updates = {field: value for field, value in updates.items() if value is not None}
        for field in ("title", "definition_of_done"):
            if field in updates:
                updates[field] = updates[field].strip()
        return await self.planning_service.update_goal(goal_id, updates)

    async def _delete_goal(self, goal_id: str) -> dict[str, Any]:
        return await self.planning_service.delete_goal(goal_id)

    async def _update_plan_item(
        self, plan_item_id: str, **updates: Any
    ) -> dict[str, Any]:
        updates = {field: value for field, value in updates.items() if value is not None}
        if "title" in updates:
            updates["title"] = updates["title"].strip()
        return await self.planning_service.update_plan_item(plan_item_id, updates)

    async def _reschedule_plan_task(
        self,
        task_id: str,
        planned_for: str,
        weekly_parent_id: str | None = None,
    ) -> dict[str, Any]:
        if weekly_parent_id is not None:
            parent = await self.planning_service.get_plan_item(weekly_parent_id)
            return await self.planning_service.update_plan_item(task_id, {
                "goal_id": parent["goal_id"],
                "parent_id": weekly_parent_id,
                "planned_for": planned_for,
            })
        return await self.planning_service.reschedule_plan_item(task_id, planned_for)

    async def _create_daily_plan_task(
        self,
        title: str,
        weekly_parent_id: str,
        planned_for: str,
        importance: str = "medium",
        estimate_minutes: int = 25,
    ) -> dict[str, Any]:
        parent = await self.planning_service.get_plan_item(weekly_parent_id)
        return await self.planning_service.create_plan_item({
            "goal_id": parent["goal_id"],
            "parent_id": weekly_parent_id,
            "horizon": "day",
            "title": title.strip(),
            "importance": importance,
            "planned_for": planned_for,
            "estimate_minutes": estimate_minutes,
        })

    async def _regenerate_week_plan(self, week_item_id: str) -> dict[str, Any]:
        return await self.planner_service.regenerate_approved_week(
            week_item_id,
            self.provider,
        )

    async def _validate(
        self,
        action_type: str,
        arguments: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        tool = self.tools_by_name.get(action_type)
        if tool is None or tool.args_schema is None:
            raise InvalidActionError("Unsupported action")

        try:
            validated_model = tool.args_schema.model_validate(arguments)
            validated = validated_model.model_dump(
                exclude_unset=action_type in {
                    "update_task", "update_goal", "update_plan_item",
                }
            )
        except ValidationError as error:
            raise InvalidActionError("Action arguments are invalid") from error

        if action_type == "create_task":
            validated["name"] = validated["name"].strip()
            if not validated["name"]:
                raise InvalidActionError("Task name must not be blank")
            details = [f'Create task “{validated["name"]}”']
            details.append(f'priority {validated["priority"]}')
            if validated["deadline"]:
                details.append(f'deadline {validated["deadline"]}')
            if validated["estimated_duration"]:
                details.append(f'{validated["estimated_duration"]} minutes')
            return validated, ", ".join(details)

        if action_type == "create_tasks":
            for task in validated["tasks"]:
                task["name"] = task["name"].strip()
                if not task["name"]:
                    raise InvalidActionError("Task names must not be blank")
            names = ", ".join(f'“{task["name"]}”' for task in validated["tasks"])
            return validated, f'Create {len(validated["tasks"])} tasks: {names}'

        if action_type == "start_focus_session":
            task = await self.task_service.get_open_task_summary(validated["task_id"])
            if task is None:
                raise ActionConflictError("The selected task is no longer open")
            if await self.session_service.get_current_session() is not None:
                raise ActionConflictError("A focus session is already active")
            return (
                validated,
                f'Start a {validated["duration_minutes"]}-minute focus session '
                f'for “{task["name"]}”',
            )

        if action_type == "complete_task":
            task = await self.task_service.get_open_task_summary(validated["task_id"])
            if task is None:
                raise ActionConflictError("The selected task is no longer open")
            return validated, f'Mark “{task["name"]}” complete'

        if action_type == "update_task":
            task = await self.task_service.get_open_task_summary(validated["task_id"])
            if task is None:
                raise ActionConflictError("The selected task is no longer open")
            changes: list[str] = []
            if "name" in validated:
                validated["name"] = validated["name"].strip()
                changes.append(f'name to “{validated["name"]}”')
            if "priority" in validated:
                changes.append(f'priority to {validated["priority"]}')
            if "deadline" in validated:
                changes.append(f'deadline to {validated["deadline"] or "none"}')
            if "estimated_duration" in validated:
                duration = validated["estimated_duration"]
                changes.append(
                    f'duration to {f"{duration} minutes" if duration else "none"}'
                )
            return validated, f'Update “{task["name"]}”: {", ".join(changes)}'

        if action_type == "delete_task":
            task = await self.task_service.get_open_task_summary(validated["task_id"])
            if task is None:
                raise ActionConflictError("The selected task is no longer open")
            return validated, f'Permanently delete “{task["name"]}”'

        if action_type == "update_goal":
            goal = await self.planning_service.get_goal(validated["goal_id"])
            changes: list[str] = []
            if "title" in validated:
                validated["title"] = validated["title"].strip()
                changes.append(f'title to “{validated["title"]}”')
            if "definition_of_done" in validated:
                validated["definition_of_done"] = validated["definition_of_done"].strip()
                changes.append("definition of done")
            if "deadline" in validated:
                changes.append(f'deadline to {validated["deadline"]}')
            if "importance" in validated:
                changes.append(f'importance to {validated["importance"]}')
            if "weekly_capacity_minutes" in validated:
                changes.append(
                    f'weekly capacity to {validated["weekly_capacity_minutes"]} minutes'
                )
            return validated, f'Update Goal “{goal["title"]}”: {", ".join(changes)}'

        if action_type == "delete_goal":
            goal = await self.planning_service.get_goal(validated["goal_id"])
            return (
                validated,
                f'Delete Goal “{goal["title"]}”. Completed history is retained; '
                "open daily tasks move to Inbox",
            )

        if action_type == "update_plan_item":
            item = await self.planning_service.get_plan_item(validated["plan_item_id"])
            if item["status"] != "open":
                raise ActionConflictError("The selected plan item is no longer open")

            allowed = {
                "month": {"title", "importance", "period_start"},
                "week": {"title", "importance", "period_start"},
                "day": {"title", "importance", "planned_for", "estimate_minutes"},
            }[item["horizon"]]
            supplied = set(validated) - {"plan_item_id"}
            unsupported = supplied - allowed
            if unsupported:
                fields = ", ".join(sorted(unsupported))
                raise InvalidActionError(
                    f"Fields not supported for a {item['horizon']} plan item: {fields}"
                )

            changes: list[str] = []
            if "title" in validated:
                validated["title"] = validated["title"].strip()
                changes.append(f'title to “{validated["title"]}”')
            if "importance" in validated:
                changes.append(f'importance to {validated["importance"]}')
            if "period_start" in validated:
                label = "month" if item["horizon"] == "month" else "week start"
                changes.append(f'{label} to {validated["period_start"]}')
            if "planned_for" in validated:
                changes.append(f'date to {validated["planned_for"]}')
            if "estimate_minutes" in validated:
                changes.append(f'duration to {validated["estimate_minutes"]} minutes')
            kind = {
                "month": "Monthly milestone",
                "week": "Weekly outcome",
                "day": "Daily task",
            }[item["horizon"]]
            return (
                validated,
                f'{kind} “{item["title"]}”: {", ".join(changes)}',
            )

        if action_type == "reschedule_plan_task":
            item = await self.planning_service.get_plan_item(validated["task_id"])
            if item["horizon"] != "day" or item["status"] != "open":
                raise ActionConflictError("The selected daily task is no longer open")
            weekly_parent_id = validated.get("weekly_parent_id")
            parent = None
            if weekly_parent_id:
                parent = await self.planning_service.get_plan_item(weekly_parent_id)
                if parent["horizon"] != "week" or parent["status"] != "open":
                    raise ActionConflictError("The selected weekly plan is no longer open")
                if item["goal_id"] and item["goal_id"] != parent["goal_id"]:
                    raise ActionConflictError(
                        "The Inbox task and weekly plan belong to different goals"
                    )
            elif item["goal_id"] and not item["parent_id"]:
                raise InvalidActionError(
                    "A goal-linked Inbox task requires a weekly parent"
                )
            destination = validated["planned_for"]
            if parent:
                destination += f' under week “{parent["title"]}”'
            return (
                validated,
                f'Move “{item["title"]}” from {item["planned_for"] or "Inbox"} '
                f'to {destination}',
            )

        if action_type == "create_daily_plan_task":
            parent = await self.planning_service.get_plan_item(
                validated["weekly_parent_id"]
            )
            if parent["horizon"] != "week" or parent["status"] != "open":
                raise ActionConflictError("The selected weekly plan is no longer open")
            validated["title"] = validated["title"].strip()
            return (
                validated,
                f'Add daily task “{validated["title"]}” on {validated["planned_for"]} '
                f'to week “{parent["title"]}” ({validated["estimate_minutes"]} minutes)',
            )

        if action_type == "regenerate_week_plan":
            week = await self.planning_service.get_plan_item(validated["week_item_id"])
            if week["horizon"] != "week" or week["status"] != "open":
                raise ActionConflictError("The selected weekly plan is no longer open")
            return (
                validated,
                f'Regenerate week “{week["title"]}” with AI. Open daily tasks will be '
                "replaced; completed history is retained",
            )

        session = await self.session_service.get_current_session()
        if action_type == "pause_focus_session":
            if session is None or session["state"] != "running":
                raise ActionConflictError("There is no running focus session")
            return validated, "Pause the current focus session"

        if action_type == "resume_focus_session":
            if session is None or session["state"] != "paused":
                raise ActionConflictError("There is no paused focus session")
            return validated, "Resume the current focus session"

        if action_type == "extend_focus_session":
            if session is None or session["state"] != "running":
                raise ActionConflictError("There is no running focus session")
            return (
                validated,
                f'Extend the current focus session by {validated["duration_minutes"]} minutes',
            )

        raise InvalidActionError("Unsupported action")

    async def prepare(
        self,
        tool_call: dict[str, Any],
        provider: str,
        thread_id: str,
    ) -> dict[str, Any]:
        action_type = tool_call["name"]
        try:
            arguments, preview = await self._validate(
                action_type, tool_call.get("args", {})
            )
        except PlanningError as error:
            raise ActionConflictError(str(error)) from error
        now = datetime.now(timezone.utc)
        return {
            "id": str(uuid4()),
            "type": action_type,
            "tool_call_id": tool_call["id"],
            "arguments": arguments,
            "preview": preview,
            "provider": provider,
            "thread_id": thread_id,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=ACTION_EXPIRY_MINUTES)).isoformat(),
        }

    async def prepare_plan_batch(
        self,
        tool_calls: list[dict[str, Any]],
        provider: str,
        thread_id: str,
    ) -> dict[str, Any]:
        if not 2 <= len(tool_calls) <= 20 or any(
            call.get("name") not in PLAN_ACTION_TYPES for call in tool_calls
        ):
            raise InvalidActionError("A plan batch must contain 2 to 20 plan changes")

        actions: list[dict[str, Any]] = []
        previews: list[str] = []
        for tool_call in tool_calls:
            arguments, preview = await self._validate(
                tool_call["name"], tool_call.get("args", {})
            )
            actions.append({"type": tool_call["name"], "arguments": arguments})
            previews.append(preview)

        now = datetime.now(timezone.utc)
        preview_lines = "\n".join(
            f"{index}. {preview}" for index, preview in enumerate(previews, start=1)
        )
        return {
            "id": str(uuid4()),
            "type": "edit_plan",
            "tool_call_id": tool_calls[0]["id"],
            "arguments": {"actions": actions},
            "preview": f"Apply {len(actions)} plan changes:\n{preview_lines}",
            "provider": provider,
            "thread_id": thread_id,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=ACTION_EXPIRY_MINUTES)).isoformat(),
        }

    async def execute(self, pending_action: dict[str, Any]) -> dict[str, Any]:
        action_type = pending_action["type"]
        if action_type == "edit_plan":
            results = []
            for action in pending_action["arguments"]["actions"]:
                results.append(await self.execute(action))
            return {"updated_count": len(results), "results": results}

        try:
            arguments, _ = await self._validate(
                action_type,
                pending_action["arguments"],
            )
        except PlanningError as error:
            raise ActionConflictError(str(error)) from error
        tool = self.tools_by_name[action_type]
        try:
            timeout = (
                PLANNER_WRITE_TIMEOUT_SECONDS
                if action_type == "regenerate_week_plan"
                else WRITE_TOOL_TIMEOUT_SECONDS
            )
            self._execution_idempotency_key = pending_action.get("id")
            try:
                result = await asyncio.wait_for(
                    tool.ainvoke(arguments),
                    timeout=timeout,
                )
            finally:
                self._execution_idempotency_key = None
        except TimeoutError as error:
            raise ActionTimeoutError("The action timed out") from error
        except (InvalidActionError, ActionConflictError):
            raise
        except PlanningError as error:
            raise ActionConflictError(str(error)) from error
        except ProviderError:
            raise
        except Exception as error:
            raise ActionExecutionError("The action could not be completed") from error

        if not isinstance(result, dict) or "error" in result:
            raise ActionConflictError("Application state changed before confirmation")
        return result
