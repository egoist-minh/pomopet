import asyncio
import json
import unittest
from typing import Annotated, TypedDict
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
from langchain_core.messages import AIMessage, AnyMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.database import Base
from app.services.pomo_agent import PomoAgent, TOOL_LIMIT_MESSAGE
from app.services.productivity_tools import ProductivityToolError, create_productivity_tools
from app.services.session_service import SessionService
from app.services.task_service import TaskService
from app.services.planning_service import PlanningService


class ToolTestState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    timezone_offset: int


class ProductivityToolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.database = self.session_factory()

        task_service = TaskService(self.database)
        created = await task_service.create_task(
            {
                "name": "Write release notes",
                "priority": "high",
                "deadline": "2026-10-18",
                "estimated_duration": 30,
            }
        )
        self.task_id = created["id"]
        await task_service.add_subtask(self.task_id, "Summarize changes")

    async def asyncTearDown(self):
        await self.database.close()
        await self.engine.dispose()

    async def invoke_tool(self, name: str, arguments: dict | None = None):
        tools = create_productivity_tools(self.database)
        graph_builder = StateGraph(ToolTestState)
        graph_builder.add_node("tools", ToolNode(tools))
        graph_builder.add_edge(START, "tools")
        graph_builder.add_edge("tools", END)
        graph = graph_builder.compile()
        result = await graph.ainvoke(
            {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": name,
                                "args": arguments or {},
                                "id": f"call-{name}",
                                "type": "tool_call",
                            }
                        ],
                    )
                ],
                "timezone_offset": 420,
            }
        )
        return json.loads(result["messages"][-1].content)

    async def test_read_tools_return_concise_productivity_context(self):
        tasks = await self.invoke_tool("list_open_tasks")
        self.assertEqual(tasks["open_task_count"], 1)
        self.assertEqual(
            tasks["tasks"][0],
            {
                "id": self.task_id,
                "name": "Write release notes",
                "priority": "high",
                "deadline": "2026-10-18",
                "estimated_duration_minutes": 30,
                "subtasks": [
                    {
                        "id": tasks["tasks"][0]["subtasks"][0]["id"],
                        "name": "Summarize changes",
                    }
                ],
            },
        )

        self.assertEqual(
            await self.invoke_tool("get_current_focus_session"),
            {"active": False},
        )

        session_service = SessionService(self.database)
        await session_service.start_session(self.task_id, 1500)
        await session_service.add_distraction()
        session = await self.invoke_tool("get_current_focus_session")
        self.assertTrue(session["active"])
        self.assertEqual(session["state"], "running")
        self.assertEqual(session["time_left_seconds"], 1800)
        self.assertEqual(session["distraction_count"], 1)
        self.assertEqual(
            session["task"],
            {"id": self.task_id, "name": "Write release notes"},
        )

        overview = await self.invoke_tool("get_productivity_overview")
        self.assertEqual(overview["open_task_count"], 1)
        self.assertTrue(overview["current_focus_session"]["active"])
        self.assertIn("focus_hours_today", overview)
        self.assertIn("focus_hours_week", overview)

        statistics = await self.invoke_tool("get_focus_statistics")
        self.assertEqual(statistics["current_distraction_chain"], 1)
        self.assertEqual(statistics["total_distractions_week"], 1)
        self.assertNotIn("distractionData", statistics)

        planning = PlanningService(self.database)
        goal = await planning.create_goal({
            "title": "IELTS",
            "definition_of_done": "Band 7",
            "deadline": "2026-12-30",
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
            "title": "Current outcome",
            "period_start": "2026-10-19",
        })
        inbox = await planning.create_plan_item({
            "goal_id": goal["id"],
            "horizon": "day",
            "title": "Unscheduled practice",
            "estimate_minutes": 25,
        })
        context = await self.invoke_tool("get_planning_context")
        self.assertEqual(context["goals"][0]["id"], goal["id"])
        self.assertEqual(context["goals"][0]["definition_of_done"], "Band 7")
        self.assertEqual(context["goals"][0]["weekly_capacity_minutes"], 300)
        self.assertEqual(
            context["goals"][0]["monthly_milestones"][0]["id"], month["id"]
        )
        self.assertEqual(
            context["goals"][0]["monthly_milestones"][0]["weekly_outcomes"][0]["id"],
            week["id"],
        )
        self.assertEqual(context["views"]["inbox"][0]["id"], inbox["id"])
        self.assertEqual(context["summary"]["inbox_task_count"], 2)
        self.assertEqual(context["local_time"]["utc_offset_minutes"], 420)
        self.assertTrue(context["local_time"]["now"].endswith("+07:00"))
        self.assertIn("current_week", context)

    async def test_agent_binds_and_executes_read_tool(self):
        model = MagicMock()
        bound_model = MagicMock()
        bound_model.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "list_open_tasks",
                            "args": {},
                            "id": "call-list",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="Bạn có một công việc đang mở."),
            ]
        )
        model.bind_tools.return_value = bound_model

        memory_connection = await aiosqlite.connect(":memory:")
        memory_saver = AsyncSqliteSaver(memory_connection)
        try:
            agent = PomoAgent(
                "openai",
                model=model,
                database=self.database,
                checkpointer=memory_saver,
            )
            response = await agent.chat(
                "Tôi còn việc gì?",
                thread_id="tool-memory-test",
                timezone_offset=420,
            )

            snapshot = await agent.graph.aget_state(
                {"configurable": {"thread_id": "tool-memory-test"}}
            )
            checkpoint_messages = snapshot.values["messages"]
            self.assertEqual(len(checkpoint_messages), 2)
            self.assertEqual(checkpoint_messages[0].content, "Tôi còn việc gì?")
            self.assertEqual(
                checkpoint_messages[1].content,
                "Bạn có một công việc đang mở.",
            )
            async with memory_connection.execute(
                "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?",
                ("tool-memory-test",),
            ) as cursor:
                checkpoint_count = (await cursor.fetchone())[0]
            self.assertGreaterEqual(checkpoint_count, 1)
        finally:
            await memory_connection.close()

        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["message"], "Bạn có một công việc đang mở.")
        bound_names = {bound_tool.name for bound_tool in model.bind_tools.call_args.args[0]}
        self.assertEqual(
            bound_names,
            {
                "get_productivity_overview",
                "list_open_tasks",
                "get_current_focus_session",
                "get_focus_statistics",
                "create_task",
                "create_tasks",
                "start_focus_session",
                "pause_focus_session",
                "resume_focus_session",
                "extend_focus_session",
                "complete_task",
                "update_task",
                "delete_task",
                "get_planning_context",
                "update_goal",
                "delete_goal",
                "update_plan_item",
                "reschedule_plan_task",
                "create_daily_plan_task",
                "regenerate_week_plan",
            },
        )
        for bound_tool in model.bind_tools.call_args.args[0]:
            self.assertNotIn(
                "timezone_offset",
                bound_tool.tool_call_schema.model_json_schema().get("properties", {}),
            )
        second_model_messages = bound_model.ainvoke.await_args_list[1].args[0]
        tool_message = second_model_messages[-1]
        self.assertEqual(tool_message.name, "list_open_tasks")
        self.assertIn("Write release notes", tool_message.content)
        first_model_messages = bound_model.ainvoke.await_args_list[0].args[0]
        self.assertIn("UTC offset +420 minutes", first_model_messages[0].content)

    async def test_agent_rejects_tool_batch_over_limit_without_execution(self):
        model = MagicMock()
        bound_model = MagicMock()
        bound_model.ainvoke = AsyncMock(
            return_value=AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "list_open_tasks",
                        "args": {},
                        "id": f"call-{index}",
                        "type": "tool_call",
                    }
                    for index in range(5)
                ],
            )
        )
        model.bind_tools.return_value = bound_model

        response = await PomoAgent(
            "openai", model=model, database=self.database
        ).chat("Read everything")

        self.assertEqual(response["message"], TOOL_LIMIT_MESSAGE)
        bound_model.ainvoke.assert_awaited_once()

    async def test_tool_timeout_surfaces_as_safe_error(self):
        async def slow_task_query(_service):
            await asyncio.sleep(0.05)
            raise RuntimeError("sensitive database details")

        model = MagicMock()
        bound_model = MagicMock()
        bound_model.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "list_open_tasks",
                            "args": {},
                            "id": "call-timeout",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="Mình chưa thể đọc danh sách công việc."),
            ]
        )
        model.bind_tools.return_value = bound_model

        with patch(
            "app.services.productivity_tools.TOOL_TIMEOUT_SECONDS", 0.001
        ), patch.object(TaskService, "get_all_tasks", slow_task_query):
            with self.assertRaisesRegex(ProductivityToolError, "took too long") as error:
                await PomoAgent(
                    "openai", model=model, database=self.database
                ).chat("Tôi còn việc gì?")

        self.assertNotIn("sensitive database details", str(error.exception))
        bound_model.ainvoke.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
