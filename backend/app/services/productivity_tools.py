import asyncio
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any, TypeVar

from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import InjectedState
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.session_service import SessionService
from app.services.planning_service import PlanningService
from app.services.statistics_service import StatisticsService
from app.services.task_service import TaskService


TOOL_TIMEOUT_SECONDS = 5
_Result = TypeVar("_Result")


class ProductivityToolError(RuntimeError):
    """Safe, user-displayable failure raised by a productivity read tool."""


class ProductivityToolTimeoutError(ProductivityToolError):
    """A productivity read exceeded its deadline."""


async def _with_timeout(operation: Awaitable[_Result]) -> _Result:
    try:
        return await asyncio.wait_for(operation, timeout=TOOL_TIMEOUT_SECONDS)
    except TimeoutError as error:
        raise ProductivityToolTimeoutError("Productivity data took too long to load.") from error
    except ProductivityToolError:
        raise
    except Exception as error:
        raise ProductivityToolError("Productivity data is temporarily unavailable.") from error


def create_productivity_tools(database: AsyncSession) -> list[BaseTool]:
    task_service = TaskService(database)
    session_service = SessionService(database)
    statistics_service = StatisticsService(database)
    planning_service = PlanningService(database)
    database_lock = asyncio.Lock()

    async def run_tool(operation: Callable[[], Awaitable[_Result]]) -> _Result:
        async def run_serially() -> _Result:
            async with database_lock:
                return await operation()

        return await _with_timeout(run_serially())

    async def current_session_summary() -> dict[str, Any]:
        session = await session_service.get_current_session()
        if session is None:
            return {"active": False}

        task = await task_service.get_task_summary(session["task_id"])
        return {
            "active": True,
            "id": session["id"],
            "state": session["state"],
            "time_left_seconds": session["time_left"],
            "distraction_count": session["distraction_count"],
            "task": task or {"id": session["task_id"], "name": None},
        }

    @tool
    async def get_productivity_overview(
        timezone_offset: Annotated[int, InjectedState("timezone_offset")],
    ) -> dict[str, Any]:
        """Get a concise overview of open tasks, the active focus session, and focus totals."""
        async def read_overview() -> dict[str, Any]:
            tasks = await task_service.get_all_tasks()
            session = await current_session_summary()
            statistics = await statistics_service.get_all_statistics(timezone_offset)
            return {
                "open_task_count": len(tasks),
                "current_focus_session": session,
                "focus_hours_today": statistics["focusHoursToday"],
                "focus_hours_week": statistics["focusHoursWeek"],
            }

        return await run_tool(read_overview)

    @tool
    async def list_open_tasks() -> dict[str, Any]:
        """List current open tasks with priority, deadline, duration, and unfinished subtasks."""
        async def read_tasks() -> dict[str, Any]:
            tasks = await task_service.get_all_tasks()
            summaries = [
                {
                    "id": task["id"],
                    "name": task["name"],
                    "priority": task["priority"],
                    "deadline": task["deadline"] or None,
                    "estimated_duration_minutes": task["estimatedDuration"],
                    "subtasks": [
                        {"id": subtask["id"], "name": subtask["name"]}
                        for subtask in task["subtasks"]
                    ],
                }
                for task in tasks
            ]
            return {"open_task_count": len(summaries), "tasks": summaries}

        return await run_tool(read_tasks)

    @tool
    async def get_current_focus_session() -> dict[str, Any]:
        """Get the active focus session state, remaining time, distractions, and related task."""
        return await run_tool(current_session_summary)

    @tool
    async def get_focus_statistics(
        timezone_offset: Annotated[int, InjectedState("timezone_offset")],
    ) -> dict[str, Any]:
        """Get today's and this week's focus statistics in the client's timezone."""
        async def read_statistics() -> dict[str, Any]:
            statistics = await statistics_service.get_all_statistics(timezone_offset)
            return {
                "focus_hours_today": statistics["focusHoursToday"],
                "focus_hours_week": statistics["focusHoursWeek"],
                "sessions_completed_today": statistics["sessionsCompleted"],
                "current_distraction_chain": statistics["distractionChain"],
                "total_distractions_week": statistics["totalDistractionsWeek"],
            }

        return await run_tool(read_statistics)

    @tool
    async def get_planning_context(
        timezone_offset: Annotated[int, InjectedState("timezone_offset")],
    ) -> dict[str, Any]:
        """Get the user's local calendar and current Plan views, hierarchy, and IDs.

        Use this before answering questions about the current Plan or changing a goal,
        monthly milestone, weekly outcome, or daily task.
        """
        async def read_planning() -> dict[str, Any]:
            user_timezone = timezone(timedelta(minutes=timezone_offset))
            local_now = datetime.now(timezone.utc).astimezone(user_timezone)
            local_today = local_now.date()
            week_start = local_today - timedelta(days=local_today.weekday())
            week_end = week_start + timedelta(days=6)
            goals = await planning_service.list_goals()
            open_items = await planning_service.list_plan_items(status="open")
            completed_items = await planning_service.list_plan_items(status="completed")

            def plan_item(item: dict[str, Any]) -> dict[str, Any]:
                return {
                    "id": item["id"],
                    "goal_id": item["goal_id"],
                    "parent_id": item["parent_id"],
                    "horizon": item["horizon"],
                    "title": item["title"],
                    "importance": item["importance"],
                    "deadline": item["deadline"],
                    "planned_for": item["planned_for"],
                    "period_start": item["period_start"],
                    "estimate_minutes": item["estimate_minutes"],
                    "status": item["status"],
                    "version": item["version"],
                }

            def daily_in_window(item: dict[str, Any], start: date, end: date) -> bool:
                return (
                    item["horizon"] == "day"
                    and item["planned_for"] is not None
                    and start <= date.fromisoformat(item["planned_for"]) <= end
                )

            completed_this_week = [
                item for item in completed_items
                if daily_in_window(item, week_start, week_end)
            ]
            visible_items = [*open_items, *completed_this_week]

            inbox = [
                item for item in open_items
                if item["horizon"] == "day" and item["planned_for"] is None
            ]
            today = [
                item for item in open_items
                if item["horizon"] == "day"
                and item["planned_for"] == local_today.isoformat()
            ]
            current_week_tasks = [
                item for item in visible_items
                if daily_in_window(item, week_start, week_end)
            ]
            overdue = [
                item for item in open_items
                if item["horizon"] == "day"
                and item["planned_for"] is not None
                and date.fromisoformat(item["planned_for"]) < local_today
            ]

            def sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
                return sorted(
                    items,
                    key=lambda item: (
                        item["planned_for"] or item["period_start"] or "9999-12-31",
                        item["title"].casefold(),
                        item["id"],
                    ),
                )

            goal_contexts: list[dict[str, Any]] = []
            for goal in goals:
                goal_items = [
                    item for item in visible_items if item["goal_id"] == goal["id"]
                ]
                goal_weeks = [
                    item for item in goal_items if item["horizon"] == "week"
                ]
                goal_days = [
                    item for item in goal_items if item["horizon"] == "day"
                ]
                milestones = []
                for month in sort_items([
                    item for item in goal_items if item["horizon"] == "month"
                ]):
                    weekly_outcomes = []
                    for week in sort_items([
                        item for item in goal_weeks if item["parent_id"] == month["id"]
                    ]):
                        weekly_outcomes.append({
                            **plan_item(week),
                            "daily_tasks": [
                                plan_item(item)
                                for item in sort_items([
                                    day for day in goal_days
                                    if day["parent_id"] == week["id"]
                                ])
                            ],
                        })
                    milestones.append({
                        **plan_item(month),
                        "weekly_outcomes": weekly_outcomes,
                    })

                week_goal_tasks = [
                    item for item in current_week_tasks if item["goal_id"] == goal["id"]
                ]
                planned_minutes = sum(
                    item["estimate_minutes"] or 0 for item in week_goal_tasks
                )
                capacity_minutes = goal["weekly_capacity_minutes"]
                goal_contexts.append({
                    "id": goal["id"],
                    "title": goal["title"],
                    "definition_of_done": goal["definition_of_done"],
                    "deadline": goal["deadline"],
                    "importance": goal["importance"],
                    "status": goal["status"],
                    "weekly_capacity_minutes": capacity_minutes,
                    "version": goal["version"],
                    "current_week": {
                        "planned_minutes": planned_minutes,
                        "capacity_minutes": capacity_minutes,
                        "over_capacity": (
                            capacity_minutes > 0 and planned_minutes > capacity_minutes
                        ),
                        "open_daily_task_count": sum(
                            item["status"] == "open" for item in week_goal_tasks
                        ),
                        "completed_daily_task_count": sum(
                            item["status"] == "completed" for item in week_goal_tasks
                        ),
                    },
                    "inbox_tasks": [
                        plan_item(item)
                        for item in sort_items([
                            item for item in inbox if item["goal_id"] == goal["id"]
                        ])
                    ],
                    "monthly_milestones": milestones,
                })

            return {
                "local_time": {
                    "now": local_now.isoformat(timespec="minutes"),
                    "date": local_today.isoformat(),
                    "weekday": local_today.strftime("%A"),
                    "utc_offset_minutes": timezone_offset,
                },
                # Retain these top-level keys for compatibility with existing prompts.
                "today": local_today.isoformat(),
                "current_week": {
                    "start": week_start.isoformat(),
                    "end": week_end.isoformat(),
                },
                "summary": {
                    "active_goal_count": sum(
                        goal["status"] == "active" for goal in goals
                    ),
                    "open_plan_item_count": len(open_items),
                    "inbox_task_count": len(inbox),
                    "overdue_task_count": len(overdue),
                    "today_task_count": len(today),
                    "current_week_task_count": len(current_week_tasks),
                },
                "views": {
                    "inbox": [plan_item(item) for item in sort_items(inbox)],
                    "today": [plan_item(item) for item in sort_items(today)],
                    "current_week": [
                        plan_item(item) for item in sort_items(current_week_tasks)
                    ],
                    "overdue": [plan_item(item) for item in sort_items(overdue)],
                },
                "goals": goal_contexts,
                # Flat open list remains useful for exact-ID resolution and compatibility.
                "plan_items": [
                    plan_item(item) for item in sort_items(open_items)
                ],
                "completed_this_week": [
                    plan_item(item) for item in sort_items(completed_this_week)
                ],
            }

        return await run_tool(read_planning)

    return [
        get_productivity_overview,
        list_open_tasks,
        get_current_focus_session,
        get_focus_statistics,
        get_planning_context,
    ]
