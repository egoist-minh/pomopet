import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.database import Base, _migrate_schema, get_db
from app.main import app
from app.models.models import (
    AgentTraceEvent,
    Goal,
    GoalStatus,
    PlanHorizon,
    PlanItem,
    PlanItemStatus,
    ProactiveDecision,
)
from app.services.proactive_service import ProactiveService
from app.services.profile_service import ProfileService


NOW = datetime(2026, 10, 25, 5, 0, 0)  # noon at UTC+07


class FakeDecisionModel:
    def __init__(self, action="TELL_JOKE", *, fail=False):
        self.action = action
        self.fail = fail
        self.calls = []

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    async def ainvoke(self, messages):
        self.calls.append(messages)
        if self.fail:
            raise RuntimeError("provider failure")
        return {
            "action": self.action,
            "message": None if self.action == "STAY_SILENT" else (
                "Mình mở Plan nhé?" if self.action == "SUGGEST_PLAN" else "A short joke"
            ),
            "reason_codes": [f"LLM_SELECTED_{self.action}"],
        }


class ProactiveServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _enable(self, database, **changes):
        return await ProfileService(database).update_default({
            "proactive_enabled": True,
            **changes,
        })

    async def _goal(self, database, goal_id="goal-1"):
        database.add(Goal(
            id=goal_id,
            title="Ship MVP",
            definition_of_done="MVP released",
            deadline="2026-12-01",
            status=GoalStatus.ACTIVE,
        ))
        await database.commit()

    async def test_off_focus_and_quiet_hours_are_silent(self):
        async with self.session_factory() as database:
            service = ProactiveService(database)
            off = await service.evaluate(
                request_id="off", trigger="periodic", session_state="idle",
                timezone_offset=420, now=NOW,
            )
            self.assertEqual(off.selected_action, "STAY_SILENT")
            self.assertEqual(ProactiveService.serialize(off)["reason_codes"], ["PROACTIVE_DISABLED"])

            await self._enable(database)
            focus = await service.evaluate(
                request_id="focus", trigger="periodic", session_state="running",
                timezone_offset=420, now=NOW,
            )
            quiet = await service.evaluate(
                request_id="quiet", trigger="periodic", session_state="idle",
                timezone_offset=420, now=datetime(2026, 10, 25, 16, 0),
            )
            self.assertEqual(ProactiveService.serialize(focus)["reason_codes"], ["FOCUS_ACTIVE"])
            self.assertEqual(ProactiveService.serialize(quiet)["reason_codes"], ["QUIET_HOURS"])

    async def test_planning_suggestion_is_prioritized_and_read_only(self):
        async with self.session_factory() as database:
            await self._enable(database)
            await self._goal(database)
            before = await database.scalar(select(func.count()).select_from(PlanItem))

            model = FakeDecisionModel("SUGGEST_PLAN")
            decision = await ProactiveService(database, model=model).evaluate(
                request_id="plan", trigger="periodic", session_state="idle",
                timezone_offset=420, now=NOW,
            )

            after = await database.scalar(select(func.count()).select_from(PlanItem))
            self.assertEqual(decision.selected_action, "SUGGEST_PLAN")
            self.assertEqual(decision.target, "plan")
            self.assertEqual(before, after)
            self.assertEqual(
                ProactiveService.serialize(decision)["reason_codes"],
                ["LLM_SELECTED_SUGGEST_PLAN"],
            )
            context = __import__("json").loads(model.calls[0][1].content)
            self.assertEqual(context["active_goals"][0]["title"], "Ship MVP")

    async def test_daily_plan_suppresses_planning_and_joke_toggle_is_respected(self):
        async with self.session_factory() as database:
            await self._enable(database, proactive_jokes_on=False)
            await self._goal(database)
            database.add(PlanItem(
                id="today", name="Implement", horizon=PlanHorizon.DAY,
                goal_id="goal-1", planned_for="2026-10-25",
            ))
            await database.commit()

            decision = await ProactiveService(database).evaluate(
                request_id="no-joke", trigger="periodic", session_state="idle",
                timezone_offset=420, now=NOW,
            )
            self.assertEqual(decision.selected_action, "STAY_SILENT")
            self.assertEqual(ProactiveService.serialize(decision)["reason_codes"], ["NO_USEFUL_OPPORTUNITY"])

    async def test_idempotency_and_unexecuted_decision_do_not_start_cooldown(self):
        async with self.session_factory() as database:
            await self._enable(database)
            service = ProactiveService(database, model=FakeDecisionModel("TELL_JOKE"))
            first = await service.evaluate(
                request_id="same", trigger="periodic", session_state="idle",
                timezone_offset=420, now=NOW,
            )
            repeated = await service.evaluate(
                request_id="same", trigger="break_ended", session_state="break",
                timezone_offset=420, now=NOW + timedelta(minutes=1),
            )
            second = await service.evaluate(
                request_id="next", trigger="periodic", session_state="idle",
                timezone_offset=420, now=NOW + timedelta(minutes=1),
            )
            count = await database.scalar(select(func.count()).select_from(ProactiveDecision))
            self.assertEqual(first.id, repeated.id)
            self.assertEqual(count, 2)
            self.assertEqual(second.selected_action, "TELL_JOKE")

    async def test_hydration_has_animation_target_and_recent_copy_is_context(self):
        async with self.session_factory() as database:
            await self._enable(database)
            hydration_model = FakeDecisionModel("GIVE_HYDRATION_TIP")
            service = ProactiveService(database, model=hydration_model)
            first = await service.evaluate(
                request_id="hydrate", trigger="periodic", session_state="break",
                timezone_offset=420, now=NOW,
            )
            self.assertEqual(first.selected_action, "GIVE_HYDRATION_TIP")
            self.assertEqual(first.target, "hydrate")
            candidates = __import__("json").loads(first.candidate_actions_json)
            self.assertTrue({
                "TELL_JOKE", "TELL_DRY_HUMOR", "GIVE_HYDRATION_TIP", "GIVE_FOCUS_TIP"
            }.issubset(candidates))

            await service.mark_executed(first.id, now=NOW)
            dry_model = FakeDecisionModel("TELL_DRY_HUMOR")
            second = await ProactiveService(database, model=dry_model).evaluate(
                request_id="dry", trigger="periodic", session_state="idle",
                timezone_offset=420, now=NOW + timedelta(minutes=6),
            )
            self.assertEqual(second.selected_action, "TELL_DRY_HUMOR")
            context = __import__("json").loads(dry_model.calls[0][1].content)
            self.assertEqual(context["recent_proactive_actions"][0]["action"], "GIVE_HYDRATION_TIP")
            self.assertEqual(context["recent_proactive_actions"][0]["message"], "A short joke")

    async def test_welcome_summarizes_open_tasks_and_recent_conversation(self):
        async with self.session_factory() as database:
            await self._enable(database)
            database.add(PlanItem(
                id="welcome-task", name="Fix timezone trace", horizon=PlanHorizon.DAY,
                planned_for="2026-10-25", status=PlanItemStatus.OPEN,
            ))
            await database.commit()
            model = FakeDecisionModel("WELCOME")
            recent = [
                {"role": "user", "text": "The proactive trace timezone still looks wrong."},
                {"role": "pet", "text": "I will inspect the UTC serialization."},
            ]
            with patch(
                "app.services.proactive_service.agent_memory.get_recent_conversation",
                new=AsyncMock(return_value=recent),
            ):
                decision = await ProactiveService(database, model=model).evaluate(
                    request_id="welcome", trigger="welcome", session_state="running",
                    timezone_offset=420, provider="gemini", thread_id="thread-1234",
                    now=datetime(2026, 10, 25, 23, 0),
                )

            self.assertEqual(decision.selected_action, "WELCOME")
            context = __import__("json").loads(model.calls[0][1].content)
            self.assertEqual(context["open_tasks"][0]["title"], "Fix timezone trace")
            self.assertEqual(context["recent_conversation"], recent)

    async def test_goodbye_is_a_lifecycle_action(self):
        async with self.session_factory() as database:
            await self._enable(database)
            decision = await ProactiveService(
                database, model=FakeDecisionModel("GOODBYE")
            ).evaluate(
                request_id="goodbye", trigger="goodbye", session_state="paused",
                timezone_offset=420, now=datetime(2026, 10, 25, 23, 0),
            )
            self.assertEqual(decision.selected_action, "GOODBYE")

    async def test_executed_actions_enforce_cooldown_without_daily_limit(self):
        async with self.session_factory() as database:
            profile = await self._enable(database)
            service = ProactiveService(database, model=FakeDecisionModel("TELL_JOKE"))
            first = await service.evaluate(
                request_id="first", trigger="periodic", session_state="idle",
                timezone_offset=420, now=NOW,
            )
            await service.mark_executed(first.id, now=NOW)
            cooldown = await service.evaluate(
                request_id="cooldown", trigger="periodic", session_state="idle",
                timezone_offset=420, now=NOW + timedelta(minutes=2),
            )
            self.assertEqual(ProactiveService.serialize(cooldown)["reason_codes"], ["COOLDOWN_ACTIVE"])

            for index in range(2):
                database.add(ProactiveDecision(
                    id=f"executed-{index}", profile_id=profile.id,
                    created_at=NOW - timedelta(hours=index + 2), trigger="periodic",
                    session_state="idle", local_date="2026-10-25",
                    selected_action="TELL_JOKE", reason_codes_json="[]",
                    state_snapshot_json="{}", candidate_actions_json="[]",
                    status="EXECUTED", executed_at=NOW - timedelta(hours=index + 2),
                ))
            await database.commit()
            after_cooldown = await service.evaluate(
                request_id="after-cooldown", trigger="periodic", session_state="idle",
                timezone_offset=420, now=NOW + timedelta(hours=2),
            )
            self.assertEqual(after_cooldown.selected_action, "TELL_JOKE")

    async def test_trace_records_selection_and_execution(self):
        async with self.session_factory() as database:
            await self._enable(database)
            service = ProactiveService(database, model=FakeDecisionModel("TELL_JOKE"))
            decision = await service.evaluate(
                request_id="trace", trigger="periodic", session_state="idle",
                timezone_offset=420, now=NOW,
            )
            await service.mark_executed(decision.id, now=NOW)
            _, events = await service.get_run(decision.id)
            self.assertEqual([event.stage for event in events], [
                "TRIGGER_RECEIVED", "STATE_BUILT", "CANDIDATES_CREATED",
                "SAFETY_APPLIED", "CONTEXT_BUILT", "LLM_DECISION",
                "ACTION_SELECTED", "ACTION_EXECUTED",
            ])
            serialized = ProactiveService.serialize(decision)
            self.assertTrue(serialized["created_at"].endswith("Z"))
            self.assertTrue(serialized["executed_at"].endswith("Z"))

    async def test_invalid_choice_and_failure_fail_closed(self):
        async with self.session_factory() as database:
            await self._enable(database)
            invalid = await ProactiveService(
                database, model=FakeDecisionModel("SUGGEST_PLAN")
            ).evaluate(
                request_id="invalid", trigger="periodic", session_state="idle",
                timezone_offset=420, now=NOW,
            )
            self.assertEqual(invalid.selected_action, "STAY_SILENT")
            self.assertEqual(
                ProactiveService.serialize(invalid)["reason_codes"],
                ["LLM_POLICY_UNAVAILABLE"],
            )

            failed = await ProactiveService(
                database, model=FakeDecisionModel(fail=True)
            ).evaluate(
                request_id="failed", trigger="periodic", session_state="idle",
                timezone_offset=420, now=NOW,
            )
            self.assertEqual(failed.selected_action, "STAY_SILENT")
            self.assertEqual(
                ProactiveService.serialize(failed)["reason_codes"],
                ["LLM_POLICY_UNAVAILABLE"],
            )

    async def test_relationship_delete_removes_proactive_history(self):
        async with self.session_factory() as database:
            await self._enable(database)
            await ProactiveService(database, model=FakeDecisionModel()).evaluate(
                request_id="delete-me", trigger="periodic", session_state="idle",
                timezone_offset=420, now=NOW,
            )

            from app.services.personal_memory_service import PersonalMemoryService
            await PersonalMemoryService(database).delete_all()
            self.assertEqual(await database.scalar(select(func.count()).select_from(ProactiveDecision)), 0)
            self.assertEqual(await database.scalar(select(func.count()).select_from(AgentTraceEvent)), 0)


class ProactiveRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

        async def override_db():
            async with self.session_factory() as database:
                yield database

        app.dependency_overrides[get_db] = override_db
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()

    async def test_evaluate_execute_and_debug_routes(self):
        async with self.session_factory() as database:
            await ProfileService(database).update_default({"proactive_enabled": True})
        with patch(
            "app.services.proactive_service.ModelFactory.create",
            return_value=FakeDecisionModel("TELL_JOKE"),
        ):
            response = await self.client.post("/api/proactive/evaluate", json={
                "request_id": "route-run", "trigger": "periodic",
                "session_state": "idle", "timezone_offset": 420, "provider": "gemini",
            })
        self.assertEqual(response.status_code, 200)
        self.assertIn(response.json()["action"], {"TELL_JOKE", "SUGGEST_PLAN"})
        executed = await self.client.post("/api/proactive/decisions/route-run/executed")
        detail = await self.client.get("/api/proactive/runs/route-run")
        self.assertEqual(executed.json()["status"], "EXECUTED")
        self.assertEqual(detail.json()["trace"][-1]["stage"], "ACTION_EXECUTED")


class ProactiveMigrationTests(unittest.TestCase):
    def test_profile_migration_is_idempotent(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE user_profiles (id VARCHAR PRIMARY KEY, personalization_on BOOLEAN)"
            )
            _migrate_schema(connection)
            _migrate_schema(connection)
        columns = {column["name"] for column in inspect(engine).get_columns("user_profiles")}
        self.assertTrue({
            "proactive_enabled", "proactive_jokes_on", "proactive_planning_on"
        }.issubset(columns))
        engine.dispose()
