import asyncio
import unittest
import os
from datetime import datetime
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage
from google.api_core.exceptions import DeadlineExceeded, ResourceExhausted
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes.chat import ChatMessage, ProviderKey
from app.api.routes.sessions import SessionStart
from app.api.routes.tasks import TaskCreate
from app.database.database import Base, _migrate_schema
from app.services.ai_service import (
    ModelFactory,
    ProviderError,
    ProviderRateLimitError,
    provider_failure_diagnostics,
)
from app.services.pomo_agent import ModelTimeoutError, PomoAgent
from app.services.session_service import SessionService
from app.services.statistics_service import StatisticsService
from app.services.task_service import TaskService
from app.models.models import DistractionEvent, PlanItemStatus, Task


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_provider_diagnostics_are_specific_without_leaking_messages(self):
        secret = "secret-api-key-and-private-syllabus"
        try:
            raise RuntimeError(f"model not found {secret}")
        except RuntimeError as cause:
            error = ProviderError("Gemini planner is unavailable")
            error.__cause__ = cause

        diagnostics = provider_failure_diagnostics(error)
        self.assertEqual(diagnostics["category"], "model_not_found")
        self.assertIn("ProviderError", diagnostics["error_types"])
        self.assertNotIn(secret, " ".join(diagnostics.values()))

    async def test_task_lifecycle(self):
        async with self.session_factory() as database:
            service = TaskService(database)
            created = await service.create_task({
                "name": "Ship PomoPet",
                "priority": "high",
                "deadline": "",
                "estimated_duration": 25,
            })
            task_id = created["id"]

            tasks = await service.get_all_tasks()
            self.assertEqual(tasks[0]["estimatedDuration"], 25)
            self.assertEqual(
                await service.update_task(task_id, {"name": "Ship MVP"}),
                {"message": "Task updated"},
            )
            self.assertEqual(
                await service.complete_task(task_id),
                {"message": "Task completed"},
            )
            self.assertEqual(await service.get_all_tasks(), [])
            self.assertEqual(
                await service.delete_task(task_id),
                {"message": "Task deleted"},
            )

    async def test_session_lifecycle(self):
        async with self.session_factory() as database:
            task = await TaskService(database).create_task({
                "name": "Test Session",
                "priority": "medium",
                "deadline": "",
                "estimated_duration": 25,
            })
            service = SessionService(database)

            started = await service.start_session(task["id"], 1500)
            self.assertEqual(started["state"], "running")
            self.assertEqual((await service.pause_session())["time_left"], 1500)
            self.assertEqual((await service.get_current_session())["state"], "paused")
            self.assertEqual((await service.resume_session())["time_left"], 1500)
            self.assertEqual((await service.extend_session(60))["time_left"], 1560)
            distracted = await service.add_distraction()
            self.assertEqual(distracted["distraction_count"], 1)
            self.assertEqual(distracted["time_left"], 1860)
            completed = await service.complete_session()
            self.assertEqual(completed["duration"], 1860)
            self.assertTrue(completed["task_completed"])
            self.assertIsNone(await service.get_current_session())
            completed_task = await database.get(Task, task["id"])
            self.assertTrue(completed_task.completed)
            self.assertEqual(completed_task.status, PlanItemStatus.COMPLETED)
            statistics = await StatisticsService(database).get_daily_statistics()
            self.assertEqual(statistics["focusHoursToday"], 0.43)

            self.assertEqual(
                await service.start_session(task["id"], 300),
                {"error": "Only open daily tasks can start focus sessions"},
            )
            next_task = await TaskService(database).create_task({
                "name": "Next task",
                "priority": "medium",
                "deadline": "",
                "estimated_duration": 5,
            })
            await service.start_session(next_task["id"], 300)
            self.assertEqual(
                await service.cancel_session(),
                {"message": "Session cancelled"},
            )

    async def test_automatic_distraction_is_idempotent_and_has_no_penalty(self):
        async with self.session_factory() as database:
            task = await TaskService(database).create_task({
                "name": "Automatic distraction",
                "priority": "medium",
                "deadline": "",
                "estimated_duration": 25,
            })
            service = SessionService(database)
            await service.start_session(task["id"], 1500)
            started_at = datetime(2026, 1, 1, 12, 0, 0)

            first = await service.add_automatic_distraction(
                event_id="auto-event-1",
                source="app_switch",
                application="Discord",
                confidence=0.95,
                started_at=started_at,
            )
            duplicate = await service.add_automatic_distraction(
                event_id="auto-event-1",
                source="app_switch",
                application="Discord",
                confidence=0.95,
                started_at=started_at,
            )
            session = await service.get_current_session()

            self.assertEqual(first["distraction_count"], 1)
            self.assertEqual(duplicate["distraction_count"], 1)
            self.assertEqual(session["penalty_seconds"], 0)
            self.assertEqual(session["time_left"], 1500)

            finished = await service.finish_automatic_distraction(
                "auto-event-1",
                datetime(2026, 1, 1, 12, 0, 42),
            )
            self.assertEqual(finished["duration_seconds"], 42)
            event = (
                await database.execute(
                    select(DistractionEvent).where(DistractionEvent.id == "auto-event-1")
                )
            ).scalar_one()
            self.assertEqual(event.application, "Discord")

    async def test_session_requires_existing_task(self):
        async with self.session_factory() as database:
            result = await SessionService(database).start_session("missing", 300)
            self.assertEqual(result, {"error": "Task not found"})

    def test_request_validation(self):
        with self.assertRaises(ValidationError):
            TaskCreate(name="   ", priority="medium", estimated_duration=25)
        with self.assertRaises(ValidationError):
            TaskCreate(name="Task", priority="urgent", estimated_duration=25)
        with self.assertRaises(ValidationError):
            TaskCreate(name="Task", priority="medium", estimated_duration=2)
        with self.assertRaises(ValidationError):
            SessionStart(task_id="task", duration=0)
        with self.assertRaises(ValidationError):
            ChatMessage(
                message="   ",
                provider="gemini",
                thread_id="thread-123",
                timezone_offset=420,
            )
        with self.assertRaises(ValidationError):
            ChatMessage(
                message="Hello",
                provider="gemini",
                thread_id="../invalid-thread",
                timezone_offset=420,
            )
        with self.assertRaises(ValidationError):
            ChatMessage(
                message="Hello",
                provider="gemini",
                thread_id="thread-123",
                timezone_offset=900,
            )
        with self.assertRaises(ValidationError):
            ProviderKey(api_key="short")

    def test_runtime_api_key_is_configured_without_exposing_it(self):
        try:
            ModelFactory.configure_api_key("gemini", "runtime-secret-key")
            status = ModelFactory.configured_providers()
            self.assertTrue(status["gemini"])
            self.assertNotIn("runtime-secret-key", repr(status))
        finally:
            ModelFactory._runtime_api_keys.pop("gemini", None)

    def test_model_factory_uses_native_gemini_provider(self):
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "gemini-test"},
        ), patch("app.services.ai_service.ChatGoogleGenerativeAI") as model_class:
            model = ModelFactory.create("gemini")

        self.assertIs(model, model_class.return_value)
        model_class.assert_called_once_with(
            api_key="test-key",
            model="gemini-test",
            temperature=0.7,
            max_tokens=200,
            request_timeout=30,
            retries=0,
        )

    def test_model_factory_defaults_to_flash_lite_for_gemini(self):
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "test-key"},
            clear=True,
        ), patch("app.services.ai_service.ChatGoogleGenerativeAI") as model_class:
            ModelFactory.create("gemini")

        self.assertEqual(
            model_class.call_args.kwargs["model"],
            "gemini-3.1-flash-lite",
        )

    def test_model_factory_uses_openai_provider(self):
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "openai-test"},
        ), patch("app.services.ai_service.ChatOpenAI") as model_class:
            model = ModelFactory.create("openai")

        self.assertIs(model, model_class.return_value)
        model_class.assert_called_once_with(
            api_key="test-key",
            model="openai-test",
            temperature=0.7,
            max_completion_tokens=200,
            timeout=30,
            max_retries=0,
        )

    def test_model_factory_rejects_missing_key_and_unknown_provider(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProviderError):
                ModelFactory.create("openai")
        with self.assertRaises(ValueError):
            ModelFactory.create("unknown")

    def test_model_factory_hides_provider_error_details(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch(
            "app.services.ai_service.ChatOpenAI",
            side_effect=RuntimeError("request contained test-key"),
        ):
            with self.assertRaisesRegex(ProviderError, "Openai chat is unavailable") as error:
                ModelFactory.create("openai")

        self.assertNotIn("test-key", str(error.exception))

    async def test_pomo_agent_runs_minimal_graph(self):
        model = AsyncMock()
        model.ainvoke.return_value = AIMessage(content="Stay focused!")

        response = await PomoAgent("openai", model=model).chat("Help me focus")

        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["message"], "Stay focused!")
        messages = model.ainvoke.await_args.args[0]
        self.assertEqual(messages[-1].content, "Help me focus")
        self.assertIn("same language", messages[0].content)

    async def test_pomo_agent_normalizes_model_failure_and_timeout(self):
        failed_model = AsyncMock()
        failed_model.ainvoke.side_effect = RuntimeError("secret provider payload")
        with self.assertRaisesRegex(ProviderError, "Openai chat is unavailable") as error:
            await PomoAgent("openai", model=failed_model).chat("Hello")
        self.assertNotIn("secret provider payload", str(error.exception))

        async def slow_response(_messages):
            await asyncio.sleep(0.05)
            return AIMessage(content="too late")

        slow_model = AsyncMock()
        slow_model.ainvoke.side_effect = slow_response
        with patch("app.services.agent_runtime.MODEL_TIMEOUT_SECONDS", 0.001):
            with self.assertRaises(ModelTimeoutError):
                await PomoAgent("openai", model=slow_model).chat("Hello")

    async def test_pomo_agent_normalizes_gemini_quota_failure(self):
        failed_model = AsyncMock()
        failed_model.ainvoke.side_effect = ResourceExhausted("quota payload")

        with self.assertRaisesRegex(
            ProviderRateLimitError,
            "Gemini quota or rate limit was reached",
        ) as error:
            await PomoAgent("gemini", model=failed_model).chat("Hello")

        self.assertNotIn("quota payload", str(error.exception))

    async def test_pomo_agent_retries_after_timeout(self):
        model = AsyncMock()
        model.ainvoke.side_effect = [TimeoutError(), AIMessage(content="Recovered")]

        with patch("app.services.agent_runtime.MODEL_TIMEOUT_RETRIES", 1), patch(
            "app.services.agent_runtime.asyncio.sleep",
            AsyncMock(),
        ) as sleep:
            response = await PomoAgent("openai", model=model).chat("Hello")

        self.assertEqual(response["message"], "Recovered")
        self.assertEqual(model.ainvoke.await_count, 2)
        sleep.assert_awaited_once_with(1.0)

    async def test_pomo_agent_falls_back_after_google_deadline(self):
        primary = AsyncMock()
        primary.ainvoke.side_effect = DeadlineExceeded("deadline")
        fallback = AsyncMock()
        fallback.ainvoke.return_value = AIMessage(content="Fallback reply")

        with patch("app.services.agent_runtime.MODEL_TIMEOUT_RETRIES", 0), patch(
            "app.services.agent_runtime.ModelFactory.create",
            return_value=fallback,
        ) as create_model:
            response = await PomoAgent("gemini", model=primary).chat("Hello")

        self.assertEqual(response["message"], "Fallback reply")
        create_model.assert_called_once_with("gemini", model="gemini-3.5-flash-lite")

    def test_schema_migration_is_repeatable(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE tasks (id VARCHAR PRIMARY KEY)")
            connection.exec_driver_sql("CREATE TABLE sessions (id VARCHAR PRIMARY KEY)")
            _migrate_schema(connection)
            _migrate_schema(connection)

            task_columns = {column["name"] for column in inspect(connection).get_columns("tasks")}
            session_columns = {column["name"] for column in inspect(connection).get_columns("sessions")}
            self.assertIn("estimated_duration", task_columns)
            self.assertIn("penalty_seconds", session_columns)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
