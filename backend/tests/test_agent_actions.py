import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.database import Base
from app.services.agent_memory import AgentMemory
from app.services.pomo_agent import ACTION_CANCELLED_MESSAGE, PomoAgent
from app.services.productivity_actions import (
    ActionConflictError,
    InvalidActionError,
    ProductivityActionService,
)
from app.services.planning_service import PlanningService
from app.services.task_service import TaskService


def action_call(name: str, arguments: dict, call_id: str = "write-1") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": arguments,
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


def action_calls(calls: list[tuple[str, dict, str]]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": arguments, "id": call_id, "type": "tool_call"}
            for name, arguments, call_id in calls
        ],
    )


class AgentActionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.database = self.session_factory()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.memory_path = Path(self.temporary_directory.name) / "agent-actions.db"
        self.memory = AgentMemory()
        await self.memory.start(self.memory_path)

    async def asyncTearDown(self):
        await self.memory.close()
        self.temporary_directory.cleanup()
        await self.database.close()
        await self.engine.dispose()

    def make_agent(self, responses: list[AIMessage]) -> tuple[PomoAgent, AsyncMock]:
        model = MagicMock()
        bound_model = MagicMock()
        bound_model.ainvoke = AsyncMock(side_effect=responses)
        model.bind_tools.return_value = bound_model
        return (
            PomoAgent(
                "openai",
                model=model,
                database=self.database,
                checkpointer=self.memory.checkpointer,
                action_store=self.memory,
            ),
            bound_model.ainvoke,
        )

    async def test_create_task_waits_for_confirm_and_executes_once(self):
        agent, model_call = self.make_agent(
            [
                action_call(
                    "create_task",
                    {
                        "name": "Ship agent mode",
                        "priority": "high",
                        "deadline": "2026-10-19",
                        "estimated_duration": 30,
                    },
                ),
            ]
        )

        prepared = await agent.chat(
            "Create the release task",
            thread_id="thread-create-action",
            timezone_offset=420,
            request_id="request-prepare",
        )
        self.assertEqual(prepared["status"], "confirmation_required")
        self.assertEqual(prepared["action"]["type"], "create_task")
        self.assertIn("Ship agent mode", prepared["action"]["preview"])
        self.assertEqual(await TaskService(self.database).get_all_tasks(), [])

        action_id = prepared["action"]["id"]
        self.assertTrue(await self.memory.set_action_status(action_id, "confirmed"))
        self.assertFalse(await self.memory.set_action_status(action_id, "confirmed"))
        completed = await agent.resolve_action(
            action_id,
            "confirm",
            "thread-create-action",
            "request-confirm",
        )

        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["message"], "Task created successfully.")
        tasks = await TaskService(self.database).get_all_tasks()
        self.assertEqual([task["name"] for task in tasks], ["Ship agent mode"])
        self.assertEqual(model_call.await_count, 1)

        snapshot = await agent.graph.aget_state(
            {"configurable": {"thread_id": "thread-create-action"}}
        )
        self.assertIsNone(snapshot.values["pending_action"])
        self.assertEqual(len(snapshot.values["messages"]), 2)

    async def test_create_multiple_tasks_with_one_confirmation(self):
        agent, model_call = self.make_agent(
            [
                action_call(
                    "create_tasks",
                    {
                        "tasks": [
                            {"name": "Write outline", "priority": "high"},
                            {
                                "name": "Review draft",
                                "priority": "medium",
                                "estimated_duration": 30,
                            },
                            {"name": "Send report", "priority": "low"},
                        ]
                    },
                ),
            ]
        )

        prepared = await agent.chat(
            "Create three tasks",
            thread_id="thread-create-task-batch",
            timezone_offset=420,
            request_id="request-prepare-batch",
        )

        self.assertEqual(prepared["status"], "confirmation_required")
        self.assertEqual(prepared["action"]["type"], "create_tasks")
        self.assertIn("Create 3 tasks", prepared["action"]["preview"])
        self.assertEqual(await TaskService(self.database).get_all_tasks(), [])

        action_id = prepared["action"]["id"]
        self.assertTrue(await self.memory.set_action_status(action_id, "confirmed"))
        completed = await agent.resolve_action(
            action_id,
            "confirm",
            "thread-create-task-batch",
            "request-confirm-batch",
        )

        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["message"], "Tasks created successfully.")
        tasks = await TaskService(self.database).get_all_tasks()
        self.assertCountEqual(
            [task["name"] for task in tasks],
            ["Write outline", "Review draft", "Send report"],
        )
        self.assertEqual(model_call.await_count, 1)

    async def test_parallel_create_task_calls_are_normalized_to_one_batch(self):
        agent, _ = self.make_agent(
            [
                action_calls(
                    [
                        ("create_task", {"name": "First task"}, "create-1"),
                        ("create_task", {"name": "Second task"}, "create-2"),
                    ]
                )
            ]
        )

        prepared = await agent.chat(
            "Create first task and second task",
            thread_id="thread-normalize-task-batch",
        )

        self.assertEqual(prepared["status"], "confirmation_required")
        self.assertEqual(prepared["action"]["type"], "create_tasks")
        self.assertIn("First task", prepared["action"]["preview"])
        self.assertIn("Second task", prepared["action"]["preview"])

    async def test_cancel_resumes_graph_without_database_change(self):
        agent, model_call = self.make_agent(
            [action_call("create_task", {"name": "Do not create", "priority": "low"})]
        )
        prepared = await agent.chat(
            "Create a task",
            thread_id="thread-cancel-action",
        )
        action_id = prepared["action"]["id"]
        self.assertTrue(await self.memory.set_action_status(action_id, "cancelled"))

        cancelled = await agent.resolve_action(
            action_id,
            "cancel",
            "thread-cancel-action",
        )

        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["message"], ACTION_CANCELLED_MESSAGE)
        self.assertEqual(await TaskService(self.database).get_all_tasks(), [])
        model_call.assert_awaited_once()

    async def test_pending_action_survives_memory_restart(self):
        agent, _ = self.make_agent(
            [action_call("create_task", {"name": "Restart-safe task"})]
        )
        prepared = await agent.chat(
            "Create after restart",
            thread_id="thread-restart-action",
        )
        action_id = prepared["action"]["id"]
        await self.memory.close()

        self.memory = AgentMemory()
        await self.memory.start(self.memory_path)
        restored_record = await self.memory.get_action(action_id)
        self.assertEqual(restored_record["status"], "pending")

        restored_model = MagicMock()
        restored_model.bind_tools.return_value = MagicMock()
        restored_agent = PomoAgent(
            "openai",
            model=restored_model,
            database=self.database,
            checkpointer=self.memory.checkpointer,
            action_store=self.memory,
        )
        self.assertTrue(await self.memory.set_action_status(action_id, "cancelled"))
        result = await restored_agent.resolve_action(
            action_id,
            "cancel",
            "thread-restart-action",
        )
        self.assertEqual(result["status"], "cancelled")

    async def test_write_arguments_and_current_state_are_revalidated(self):
        service = ProductivityActionService(self.database)
        with self.assertRaises(InvalidActionError):
            await service.prepare(
                action_call("create_task", {"name": "   "}).tool_calls[0],
                "openai",
                "thread-validation",
            )
        with self.assertRaises(ActionConflictError):
            await service.prepare(
                action_call(
                    "complete_task",
                    {"task_id": "missing-task"},
                ).tool_calls[0],
                "openai",
                "thread-validation",
            )
        with self.assertRaises(InvalidActionError):
            await service.prepare(
                action_call("update_task", {"task_id": "task-without-changes"}).tool_calls[0],
                "openai",
                "thread-validation",
            )

    async def test_focus_and_completion_write_tools_apply_valid_transitions(self):
        task_service = TaskService(self.database)
        created = await task_service.create_task(
            {"name": "Focus task", "priority": "medium", "estimated_duration": 25}
        )
        service = ProductivityActionService(self.database)

        start = await service.prepare(
            action_call(
                "start_focus_session",
                {"task_id": created["id"], "duration_minutes": 25},
                "start-1",
            ).tool_calls[0],
            "openai",
            "thread-transitions",
        )
        started = await service.execute(start)
        self.assertEqual(started["state"], "running")

        extend = await service.prepare(
            action_call(
                "extend_focus_session",
                {"duration_minutes": 12},
                "extend-1",
            ).tool_calls[0],
            "openai",
            "thread-transitions",
        )
        self.assertIn("12 minutes", extend["preview"])
        extended = await service.execute(extend)
        self.assertEqual(extended["time_left"], 2220)

        pause = await service.prepare(
            action_call("pause_focus_session", {}, "pause-1").tool_calls[0],
            "openai",
            "thread-transitions",
        )
        await service.execute(pause)

        resume = await service.prepare(
            action_call("resume_focus_session", {}, "resume-1").tool_calls[0],
            "openai",
            "thread-transitions",
        )
        await service.execute(resume)

        complete = await service.prepare(
            action_call(
                "complete_task",
                {"task_id": created["id"]},
                "complete-1",
            ).tool_calls[0],
            "openai",
            "thread-transitions",
        )
        await service.execute(complete)
        self.assertIsNone(await task_service.get_open_task_summary(created["id"]))

    async def test_update_task_waits_for_confirmation(self):
        task_service = TaskService(self.database)
        created = await task_service.create_task(
            {"name": "Draft report", "priority": "low", "estimated_duration": 25}
        )
        agent, _ = self.make_agent(
            [
                action_call(
                    "update_task",
                    {
                        "task_id": created["id"],
                        "name": "Finish report",
                        "priority": "high",
                    },
                )
            ]
        )

        prepared = await agent.chat(
            "Rename the report task and make it high priority",
            thread_id="thread-update-task",
        )

        self.assertEqual(prepared["status"], "confirmation_required")
        self.assertEqual(prepared["action"]["type"], "update_task")
        self.assertIn("Finish report", prepared["action"]["preview"])
        self.assertEqual((await task_service.get_all_tasks())[0]["name"], "Draft report")

        action_id = prepared["action"]["id"]
        self.assertTrue(await self.memory.set_action_status(action_id, "confirmed"))
        completed = await agent.resolve_action(
            action_id,
            "confirm",
            "thread-update-task",
        )

        self.assertEqual(completed["message"], "Task updated successfully.")
        updated = (await task_service.get_all_tasks())[0]
        self.assertEqual(updated["name"], "Finish report")
        self.assertEqual(updated["priority"], "high")

    async def test_delete_task_waits_for_confirmation_and_can_be_cancelled(self):
        task_service = TaskService(self.database)
        created = await task_service.create_task(
            {"name": "Obsolete task", "priority": "medium"}
        )
        agent, _ = self.make_agent(
            [action_call("delete_task", {"task_id": created["id"]})]
        )

        prepared = await agent.chat(
            "Delete the obsolete task",
            thread_id="thread-delete-task",
        )

        self.assertEqual(prepared["status"], "confirmation_required")
        self.assertEqual(prepared["action"]["type"], "delete_task")
        self.assertIn("Obsolete task", prepared["action"]["preview"])
        action_id = prepared["action"]["id"]
        self.assertTrue(await self.memory.set_action_status(action_id, "cancelled"))

        cancelled = await agent.resolve_action(
            action_id,
            "cancel",
            "thread-delete-task",
        )
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertIsNotNone(await task_service.get_open_task_summary(created["id"]))

    async def test_confirmed_delete_removes_task(self):
        task_service = TaskService(self.database)
        created = await task_service.create_task(
            {"name": "Remove me", "priority": "medium"}
        )
        agent, _ = self.make_agent(
            [action_call("delete_task", {"task_id": created["id"]})]
        )
        prepared = await agent.chat(
            "Delete Remove me",
            thread_id="thread-confirm-delete",
        )
        action_id = prepared["action"]["id"]
        self.assertTrue(await self.memory.set_action_status(action_id, "confirmed"))

        completed = await agent.resolve_action(
            action_id,
            "confirm",
            "thread-confirm-delete",
        )

        self.assertEqual(completed["message"], "Task deleted successfully.")
        self.assertIsNone(await task_service.get_task_summary(created["id"]))

    async def test_goal_update_waits_for_confirmation(self):
        planning = PlanningService(self.database)
        goal = await planning.create_goal({
            "title": "IELTS",
            "definition_of_done": "Reach band 7",
            "deadline": "2026-12-20",
            "importance": "high",
            "weekly_capacity_minutes": 300,
        })
        agent, model_call = self.make_agent([
            action_call("update_goal", {
                "goal_id": goal["id"],
                "deadline": "2026-12-30",
            })
        ])

        prepared = await agent.chat(
            "Đổi deadline Goal IELTS sang 30/12",
            thread_id="thread-update-goal",
        )
        self.assertEqual(prepared["status"], "confirmation_required")
        self.assertEqual((await planning.get_goal(goal["id"]))["deadline"], "2026-12-20")

        action_id = prepared["action"]["id"]
        self.assertTrue(await self.memory.set_action_status(action_id, "confirmed"))
        completed = await agent.resolve_action(action_id, "confirm", "thread-update-goal")
        self.assertEqual(completed["message"], "Goal updated successfully.")
        self.assertTrue(completed["plan_changed"])
        self.assertEqual((await planning.get_goal(goal["id"]))["deadline"], "2026-12-30")
        self.assertEqual(model_call.await_count, 1)

    async def test_plan_item_update_waits_for_confirmation(self):
        planning = PlanningService(self.database)
        goal = await planning.create_goal({
            "title": "IELTS",
            "definition_of_done": "Reach band 7",
            "deadline": "2026-12-31",
            "importance": "high",
            "weekly_capacity_minutes": 300,
        })
        month = await planning.create_plan_item({
            "goal_id": goal["id"],
            "horizon": "month",
            "title": "October milestone",
            "period_start": "2026-10-01",
        })
        week = await planning.create_plan_item({
            "goal_id": goal["id"],
            "parent_id": month["id"],
            "horizon": "week",
            "title": "Old weekly outcome",
            "period_start": "2026-10-19",
        })
        agent, model_call = self.make_agent([
            action_call("update_plan_item", {
                "plan_item_id": week["id"],
                "title": "Practice two mock tests",
                "importance": "high",
            })
        ])

        prepared = await agent.chat(
            "Đổi weekly outcome thành Practice two mock tests, ưu tiên cao",
            thread_id="thread-update-plan-item",
        )
        self.assertEqual(prepared["status"], "confirmation_required")
        self.assertEqual(
            (await planning.get_plan_item(week["id"]))["title"],
            "Old weekly outcome",
        )

        action_id = prepared["action"]["id"]
        self.assertTrue(await self.memory.set_action_status(action_id, "confirmed"))
        completed = await agent.resolve_action(
            action_id, "confirm", "thread-update-plan-item"
        )
        updated = await planning.get_plan_item(week["id"])
        self.assertEqual(completed["message"], "Plan updated successfully.")
        self.assertTrue(completed["plan_changed"])
        self.assertEqual(updated["title"], "Practice two mock tests")
        self.assertEqual(updated["importance"], "high")
        self.assertEqual(model_call.await_count, 1)

    async def test_multiple_plan_edits_share_one_confirmation(self):
        planning = PlanningService(self.database)
        goal = await planning.create_goal({
            "title": "IELTS",
            "definition_of_done": "Reach band 7",
            "deadline": "2026-12-31",
            "importance": "medium",
            "weekly_capacity_minutes": 300,
        })
        month = await planning.create_plan_item({
            "goal_id": goal["id"],
            "horizon": "month",
            "title": "October milestone",
            "period_start": "2026-10-01",
        })
        week = await planning.create_plan_item({
            "goal_id": goal["id"],
            "parent_id": month["id"],
            "horizon": "week",
            "title": "Old weekly outcome",
            "period_start": "2026-10-19",
        })
        agent, model_call = self.make_agent([
            action_calls([
                (
                    "update_goal",
                    {"goal_id": goal["id"], "importance": "high"},
                    "write-goal",
                ),
                (
                    "update_plan_item",
                    {"plan_item_id": week["id"], "title": "Two mock tests"},
                    "write-week",
                ),
            ])
        ])

        prepared = await agent.chat(
            "Tối ưu goal và weekly outcome này",
            thread_id="thread-multiple-plan-edits",
        )

        self.assertEqual(prepared["status"], "confirmation_required")
        self.assertEqual(prepared["action"]["type"], "edit_plan")
        self.assertIn("Apply 2 plan changes", prepared["action"]["preview"])
        self.assertEqual((await planning.get_goal(goal["id"]))["importance"], "medium")
        self.assertEqual(
            (await planning.get_plan_item(week["id"]))["title"],
            "Old weekly outcome",
        )

        action_id = prepared["action"]["id"]
        self.assertTrue(await self.memory.set_action_status(action_id, "confirmed"))
        completed = await agent.resolve_action(
            action_id, "confirm", "thread-multiple-plan-edits"
        )
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["message"], "Plan changes applied successfully.")
        self.assertTrue(completed["plan_changed"])
        self.assertEqual((await planning.get_goal(goal["id"]))["importance"], "high")
        self.assertEqual((await planning.get_plan_item(week["id"]))["title"], "Two mock tests")
        self.assertEqual(model_call.await_count, 1)

    async def test_plan_item_update_rejects_fields_for_wrong_horizon(self):
        planning = PlanningService(self.database)
        goal = await planning.create_goal({
            "title": "IELTS",
            "definition_of_done": "Reach band 7",
            "deadline": "2026-12-31",
            "importance": "high",
            "weekly_capacity_minutes": 300,
        })
        month = await planning.create_plan_item({
            "goal_id": goal["id"],
            "horizon": "month",
            "title": "October milestone",
            "period_start": "2026-10-01",
        })
        service = ProductivityActionService(self.database)

        with self.assertRaisesRegex(InvalidActionError, "planned_for"):
            await service.prepare(
                action_call("update_plan_item", {
                    "plan_item_id": month["id"],
                    "planned_for": "2026-10-23",
                }).tool_calls[0],
                "gemini",
                "thread-invalid-plan-item",
            )

    async def test_plan_actions_create_reschedule_and_delete_goal(self):
        planning = PlanningService(self.database)
        goal = await planning.create_goal({
            "title": "Learn React",
            "definition_of_done": "Ship an app",
            "deadline": "2026-12-31",
            "importance": "medium",
            "weekly_capacity_minutes": 300,
        })
        month = await planning.create_plan_item({
            "goal_id": goal["id"],
            "horizon": "month",
            "title": "October milestone",
            "period_start": "2026-10-01",
        })
        week = await planning.create_plan_item({
            "goal_id": goal["id"],
            "parent_id": month["id"],
            "horizon": "week",
            "title": "Current week",
            "period_start": "2026-10-19",
        })
        service = ProductivityActionService(self.database, provider="gemini")

        create = await service.prepare(
            action_call("create_daily_plan_task", {
                "title": "Build component",
                "weekly_parent_id": week["id"],
                "planned_for": "2026-10-22",
                "estimate_minutes": 25,
            }).tool_calls[0],
            "gemini",
            "thread-plan-actions",
        )
        created = await service.execute(create)
        self.assertEqual(created["goal_id"], goal["id"])

        move = await service.prepare(
            action_call("reschedule_plan_task", {
                "task_id": created["id"],
                "planned_for": "2026-10-23",
            }).tool_calls[0],
            "gemini",
            "thread-plan-actions",
        )
        moved = await service.execute(move)
        self.assertEqual(moved["planned_for"], "2026-10-23")

        inbox = await planning.create_plan_item({
            "goal_id": goal["id"],
            "horizon": "day",
            "title": "Inbox task",
            "estimate_minutes": 25,
        })
        schedule_inbox = await service.prepare(
            action_call("reschedule_plan_task", {
                "task_id": inbox["id"],
                "planned_for": "2026-10-25",
                "weekly_parent_id": week["id"],
            }).tool_calls[0],
            "gemini",
            "thread-plan-actions",
        )
        scheduled_inbox = await service.execute(schedule_inbox)
        self.assertEqual(scheduled_inbox["planned_for"], "2026-10-25")
        self.assertEqual(scheduled_inbox["parent_id"], week["id"])
        self.assertEqual(scheduled_inbox["goal_id"], goal["id"])

        delete = await service.prepare(
            action_call("delete_goal", {"goal_id": goal["id"]}).tool_calls[0],
            "gemini",
            "thread-plan-actions",
        )
        result = await service.execute(delete)
        self.assertEqual(result["deleted_goal_id"], goal["id"])
        self.assertEqual(result["moved_to_inbox"], 2)


if __name__ == "__main__":
    unittest.main()
