import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.database import Base, _migrate_schema, get_db
from app.main import app
from app.models.models import PlanHorizon, PlanItem, PlanItemStatus
from app.services.ai_service import ProviderError
from app.services.planner_service import (
    GEMINI_BRANCH_RESPONSE_SCHEMA,
    GEMINI_DRAFT_RESPONSE_SCHEMA,
    PlannerService,
)
from app.services.planning_schemas import (
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
from app.services.session_service import SessionService


class PlanningServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _create_hierarchy(self, service: PlanningService):
        goal = await service.create_goal(
            {
                "title": "Reach IELTS 7.0",
                "definition_of_done": "Official score is at least 7.0",
                "deadline": "2026-12-20",
                "importance": "high",
                "weekly_capacity_minutes": 600,
            }
        )
        month = await service.create_plan_item(
            {
                "title": "Build exam foundation",
                "horizon": "month",
                "goal_id": goal["id"],
                "parent_id": None,
                "period_start": "2026-11-01",
                "planned_for": None,
                "estimate_minutes": None,
            }
        )
        week = await service.create_plan_item(
            {
                "title": "Finish diagnostic review",
                "horizon": "week",
                "goal_id": goal["id"],
                "parent_id": month["id"],
                "period_start": "2026-11-02",
                "planned_for": None,
                "estimate_minutes": None,
            }
        )
        day = await service.create_plan_item(
            {
                "title": "Review reading mistakes",
                "horizon": "day",
                "goal_id": goal["id"],
                "parent_id": week["id"],
                "period_start": None,
                "planned_for": "2026-11-02",
                "estimate_minutes": 30,
            }
        )
        return goal, month, week, day

    async def test_ai_draft_schema_rejects_orphan_daily_item(self):
        with self.assertRaises(ValidationError):
            PlannerDraftPayload.model_validate({
                "items": [{
                    "client_id": "orphan-day",
                    "horizon": "day",
                    "title": "Invalid action",
                    "planned_for": "2026-10-23",
                    "estimate_minutes": 25,
                }],
            })

    async def test_goal_linked_task_can_wait_unscheduled_in_inbox(self):
        async with self.session_factory() as database:
            planning = PlanningService(database)
            goal, _, week, _ = await self._create_hierarchy(planning)

            inbox = await planning.create_plan_item({
                "title": "Choose an IELTS practice test",
                "horizon": "day",
                "goal_id": goal["id"],
                "estimate_minutes": 25,
            })

            self.assertEqual(inbox["goal_id"], goal["id"])
            self.assertIsNone(inbox["parent_id"])
            self.assertIsNone(inbox["planned_for"])

            scheduled = await planning.update_plan_item(inbox["id"], {
                "parent_id": week["id"],
                "planned_for": "2026-11-02",
            }, expected_version=inbox["version"])
            self.assertEqual(scheduled["parent_id"], week["id"])

    async def test_parent_period_edits_preserve_existing_children(self):
        async with self.session_factory() as database:
            planning = PlanningService(database)
            _, month, week, _ = await self._create_hierarchy(planning)

            renamed = await planning.update_plan_item(
                week["id"],
                {"title": "Updated weekly outcome", "importance": "medium"},
                expected_version=week["version"],
            )
            self.assertEqual(renamed["title"], "Updated weekly outcome")

            with self.assertRaisesRegex(
                PlanningConflictError, "Move daily tasks"
            ):
                await planning.update_plan_item(
                    week["id"],
                    {"period_start": "2026-11-09"},
                    expected_version=renamed["version"],
                )

            with self.assertRaisesRegex(
                PlanningConflictError, "Move weekly outcomes"
            ):
                await planning.update_plan_item(
                    month["id"],
                    {"period_start": "2026-12-01"},
                    expected_version=month["version"],
                )

    async def test_gemini_planner_uses_native_json_schema(self):
        model = MagicMock()

        PlannerService._structured_output(model, PlannerDraftPayload, "gemini")

        model.with_structured_output.assert_called_once_with(
            GEMINI_DRAFT_RESPONSE_SCHEMA,
            method="json_schema",
        )

        model.reset_mock()
        PlannerService._structured_output(model, PlannerBranchPayload, "gemini")
        model.with_structured_output.assert_called_once_with(
            GEMINI_BRANCH_RESPONSE_SCHEMA,
            method="json_schema",
        )

    async def test_openai_planner_keeps_default_structured_output(self):
        model = MagicMock()

        PlannerService._structured_output(model, PlannerDraftPayload, "openai")

        model.with_structured_output.assert_called_once_with(PlannerDraftPayload)

    async def test_validation_log_names_fields_without_values(self):
        private_value = "private-syllabus-value"
        try:
            PlannerDraftPayload.model_validate({
                "items": [{
                    "client_id": "invalid id",
                    "horizon": "day",
                    "title": private_value,
                    "planned_for": "not-a-date",
                    "estimate_minutes": 25,
                }],
            })
        except ValidationError as error:
            with patch("app.services.planner_service.error_logger.error") as log_error:
                PlannerService(MagicMock(), request_id="request-1")._log_ai_failure(
                    "gemini",
                    "generate",
                    error,
                )

        log_format, *log_values = log_error.call_args.args
        rendered = log_format % tuple(log_values)
        self.assertIn("validation_issues=", rendered)
        self.assertIn("items.0.client_id:string_pattern_mismatch", rendered)
        self.assertNotIn(private_value, rendered)

    async def test_create_hierarchy_and_progress_rollup(self):
        async with self.session_factory() as database:
            planning = PlanningService(database)
            goal, month, week, day = await self._create_hierarchy(planning)

            session_service = SessionService(database)
            started = await session_service.start_session(day["id"], 1800)
            self.assertEqual(started["state"], "running")
            await session_service.add_distraction()
            await session_service.complete_session()

            progress = await planning.get_progress(goal_id=goal["id"])
            self.assertEqual(progress["planned_minutes"], 30)
            self.assertEqual(progress["actual_focus_minutes"], 30)
            self.assertEqual(progress["focus_session_count"], 1)
            self.assertEqual(progress["completed_daily_task_count"], 1)

            day_progress = await planning.get_progress(item_id=day["id"])
            week_progress = await planning.get_progress(item_id=week["id"])
            month_progress = await planning.get_progress(item_id=month["id"])
            self.assertEqual(day_progress["actual_focus_minutes"], 30)
            self.assertEqual(week_progress["actual_focus_minutes"], 30)
            self.assertEqual(month_progress["actual_focus_minutes"], 30)

            completed = await planning.get_plan_item(day["id"])
            self.assertEqual(completed["status"], "completed")
            progress = await planning.get_progress(goal_id=goal["id"])
            self.assertEqual(progress["completed_daily_task_count"], 1)

    async def test_only_open_daily_items_can_start_focus(self):
        async with self.session_factory() as database:
            planning = PlanningService(database)
            _, month, _, day = await self._create_hierarchy(planning)
            sessions = SessionService(database)

            self.assertEqual(
                await sessions.start_session(month["id"], 300),
                {"error": "Only open daily tasks can start focus sessions"},
            )
            await planning.drop_plan_item(day["id"], day["version"])
            self.assertEqual(
                await sessions.start_session(day["id"], 300),
                {"error": "Only open daily tasks can start focus sessions"},
            )

    async def test_parent_chain_and_week_start_are_validated(self):
        async with self.session_factory() as database:
            planning = PlanningService(database)
            goal, month, _, _ = await self._create_hierarchy(planning)

            with self.assertRaisesRegex(PlanningError, "Monday"):
                await planning.create_plan_item(
                    {
                        "title": "Invalid week",
                        "horizon": "week",
                        "goal_id": goal["id"],
                        "parent_id": month["id"],
                        "period_start": "2026-11-03",
                        "planned_for": None,
                        "estimate_minutes": None,
                    }
                )

            with self.assertRaisesRegex(PlanningError, "week parent"):
                await planning.create_plan_item(
                    {
                        "title": "Invalid daily parent",
                        "horizon": "day",
                        "goal_id": goal["id"],
                        "parent_id": month["id"],
                        "period_start": None,
                        "planned_for": "2026-11-03",
                        "estimate_minutes": 25,
                    }
                )

    async def test_inbox_reschedule_drop_and_version_conflict(self):
        async with self.session_factory() as database:
            planning = PlanningService(database)
            inbox_item = await planning.create_plan_item(
                {
                    "title": "Sort study notes",
                    "horizon": "day",
                    "goal_id": None,
                    "parent_id": None,
                    "period_start": None,
                    "planned_for": None,
                    "estimate_minutes": 20,
                }
            )
            self.assertEqual(len(await planning.list_plan_items(inbox=True)), 1)

            scheduled = await planning.reschedule_plan_item(
                inbox_item["id"], "2026-11-04", inbox_item["version"]
            )
            self.assertEqual(scheduled["planned_for"], "2026-11-04")
            with self.assertRaises(PlanningConflictError):
                await planning.drop_plan_item(
                    inbox_item["id"], inbox_item["version"]
                )
            dropped = await planning.drop_plan_item(
                inbox_item["id"], scheduled["version"]
            )
            self.assertEqual(dropped["status"], "dropped")
            restored = await planning.move_to_inbox(
                inbox_item["id"], dropped["version"]
            )
            self.assertEqual(restored["status"], "open")
            self.assertIsNone(restored["planned_for"])

    async def test_goal_cannot_complete_with_open_items_but_can_archive(self):
        async with self.session_factory() as database:
            planning = PlanningService(database)
            goal, _, _, _ = await self._create_hierarchy(planning)
            with self.assertRaises(PlanningConflictError):
                await planning.complete_goal(goal["id"], goal["version"])
            archived = await planning.archive_goal(goal["id"], goal["version"])
            self.assertEqual(archived["status"], "archived")

    async def test_delete_goal_removes_structure_and_keeps_daily_task_in_inbox(self):
        async with self.session_factory() as database:
            planning = PlanningService(database)
            goal, month, week, day = await self._create_hierarchy(planning)

            result = await planning.delete_goal(goal["id"], goal["version"])

            self.assertEqual(result["deleted_structure_items"], 2)
            self.assertEqual(result["moved_to_inbox"], 1)
            with self.assertRaises(PlanningNotFoundError):
                await planning.get_goal(goal["id"])
            with self.assertRaises(PlanningNotFoundError):
                await planning.get_plan_item(month["id"])
            with self.assertRaises(PlanningNotFoundError):
                await planning.get_plan_item(week["id"])
            retained = await planning.get_plan_item(day["id"])
            self.assertIsNone(retained["goal_id"])
            self.assertIsNone(retained["parent_id"])
            self.assertIsNone(retained["planned_for"])
            self.assertEqual(len(await planning.list_plan_items(inbox=True)), 1)

    async def test_planning_api_crud_and_conflict_status(self):
        async with self.session_factory() as database:
            async def override_database():
                yield database

            app.dependency_overrides[get_db] = override_database
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                ) as client:
                    response = await client.post(
                        "/api/planning/goals",
                        json={
                            "title": "Ship planning MVP",
                            "definition_of_done": "All slices accepted",
                            "deadline": "2026-12-31",
                            "weekly_capacity_minutes": 300,
                        },
                    )
                    self.assertEqual(response.status_code, 201)
                    goal = response.json()

                    updated = await client.patch(
                        f"/api/planning/goals/{goal['id']}",
                        json={
                            "title": "Ship safe planning MVP",
                            "expected_version": goal["version"],
                        },
                    )
                    self.assertEqual(updated.status_code, 200)
                    self.assertEqual(updated.json()["version"], 2)

                    stale = await client.patch(
                        f"/api/planning/goals/{goal['id']}",
                        json={
                            "title": "Stale update",
                            "expected_version": goal["version"],
                        },
                    )
                    self.assertEqual(stale.status_code, 409)

                    inbox = await client.post(
                        "/api/planning/plan-items",
                        json={
                            "title": "Legacy-compatible action",
                            "horizon": "day",
                            "estimate_minutes": 25,
                        },
                    )
                    self.assertEqual(inbox.status_code, 201)
                    listing = await client.get(
                        "/api/planning/plan-items", params={"inbox": "true"}
                    )
                    self.assertEqual(listing.status_code, 200)
                    self.assertEqual(listing.json()[0]["id"], inbox.json()["id"])
            finally:
                app.dependency_overrides.pop(get_db, None)

    async def test_planner_provider_error_returns_debug_reference(self):
        async with self.session_factory() as database:
            async def override_database():
                yield database

            app.dependency_overrides[get_db] = override_database
            try:
                with patch.object(
                    PlannerService,
                    "generate",
                    AsyncMock(side_effect=ProviderError("Gemini planner is unavailable")),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app),
                        base_url="http://test",
                    ) as client:
                        response = await client.post(
                            "/api/planning/goals/goal-1/drafts",
                            json={
                                "provider": "gemini",
                                "available_weekdays": [0],
                                "minutes_per_day": 60,
                            },
                        )
                self.assertEqual(response.status_code, 503)
                body = response.json()
                self.assertEqual(body["error_code"], "PROVIDER_UNAVAILABLE")
                self.assertEqual(body["message"], "Gemini planner is unavailable")
                self.assertTrue(body["request_id"])
            finally:
                app.dependency_overrides.pop(get_db, None)

    async def test_ai_draft_capacity_and_idempotent_approval(self):
        async with self.session_factory() as database:
            planning = PlanningService(database)
            goal = await planning.create_goal({
                "title": "Pass exam",
                "definition_of_done": "Score at least 80",
                "deadline": "2026-12-20",
                "importance": "high",
                "weekly_capacity_minutes": 300,
            })
            request = PlannerRequest(
                provider="openai",
                current_state="Starting now",
                available_weekdays=[0],
                minutes_per_day=60,
                default_session_duration=60,
            )
            payload = PlannerDraftPayload.model_validate({
                "schema_version": 1,
                "assumptions": ["No syllabus supplied"],
                "items": [
                    {
                        "client_id": "month-1",
                        "parent_client_id": None,
                        "horizon": "month",
                        "title": "Build foundation",
                        "period_start": "2026-10-01",
                    },
                    {
                        "client_id": "week-1",
                        "parent_client_id": "month-1",
                        "horizon": "week",
                        "title": "Finish baseline",
                        "period_start": "2026-10-19",
                    },
                    {
                        "client_id": "day-1",
                        "parent_client_id": "week-1",
                        "horizon": "day",
                        "title": "Take diagnostic",
                        "planned_for": "2026-10-23",
                        "estimate_minutes": 120,
                    },
                ],
            })
            planner = PlannerService(database, today=date(2026, 10, 23))
            with patch.object(planner, "_invoke", AsyncMock(return_value=payload)):
                draft = await planner.generate(goal["id"], request)

            self.assertTrue(draft["capacity"]["over_capacity"])
            approval = DraftApprovalRequest(
                idempotency_key="approval-key-1",
                override_capacity=False,
            )
            with self.assertRaisesRegex(PlanningConflictError, "capacity"):
                await planner.approve(draft["id"], approval)

            approval.override_capacity = True
            first = await planner.approve(draft["id"], approval)
            second = await planner.approve(draft["id"], approval)
            self.assertEqual(first["approval_result"], second["approval_result"])
            count = await database.scalar(select(func.count()).select_from(PlanItem))
            self.assertEqual(count, 3)

    async def test_cancelled_draft_creates_no_plan_items(self):
        async with self.session_factory() as database:
            planning = PlanningService(database)
            goal = await planning.create_goal({
                "title": "Learn topic",
                "definition_of_done": "Finish curriculum",
                "deadline": "2026-12-20",
                "importance": "medium",
                "weekly_capacity_minutes": 300,
            })
            request = PlannerRequest(
                provider="openai",
                available_weekdays=[0],
                minutes_per_day=30,
            )
            payload = PlannerDraftPayload.model_validate({
                "items": [{
                    "client_id": "month-1",
                    "horizon": "month",
                    "title": "Learn basics",
                    "period_start": "2026-10-01",
                }],
            })
            planner = PlannerService(database, today=date(2026, 10, 23))
            with patch.object(planner, "_invoke", AsyncMock(return_value=payload)):
                draft = await planner.generate(goal["id"], request)
            cancelled = await planner.cancel(draft["id"])
            self.assertEqual(cancelled["status"], "cancelled")
            count = await database.scalar(select(func.count()).select_from(PlanItem))
            self.assertEqual(count, 0)

    async def test_regenerate_replaces_only_selected_branch(self):
        async with self.session_factory() as database:
            planning = PlanningService(database)
            goal = await planning.create_goal({
                "title": "Finish course",
                "definition_of_done": "Pass final project",
                "deadline": "2026-12-20",
                "importance": "medium",
                "weekly_capacity_minutes": 300,
            })
            request = PlannerRequest(
                provider="openai",
                available_weekdays=[0, 2, 4],
                minutes_per_day=60,
            )
            original = PlannerDraftPayload.model_validate({
                "items": [
                    {
                        "client_id": "month-1",
                        "horizon": "month",
                        "title": "Foundation",
                        "period_start": "2026-10-01",
                    },
                    {
                        "client_id": "week-1",
                        "parent_client_id": "month-1",
                        "horizon": "week",
                        "title": "Old outcome",
                        "period_start": "2026-10-19",
                    },
                    {
                        "client_id": "old-day",
                        "parent_client_id": "week-1",
                        "horizon": "day",
                        "title": "Old task",
                        "planned_for": "2026-10-23",
                        "estimate_minutes": 25,
                    },
                    {
                        "client_id": "month-2",
                        "horizon": "month",
                        "title": "Protected milestone",
                        "period_start": "2026-11-01",
                    },
                ],
            })
            replacement = PlannerBranchPayload.model_validate({
                "assumptions": ["Keep the outcome measurable"],
                "items": [
                    {
                        "client_id": "week-1",
                        "parent_client_id": "month-1",
                        "horizon": "week",
                        "title": "New outcome",
                        "period_start": "2026-10-19",
                    },
                    {
                        "client_id": "new-day",
                        "parent_client_id": "week-1",
                        "horizon": "day",
                        "title": "New task",
                        "planned_for": "2026-10-23",
                        "estimate_minutes": 30,
                    },
                ],
            })
            planner = PlannerService(database, today=date(2026, 10, 23))
            with patch.object(planner, "_invoke", AsyncMock(return_value=original)):
                draft = await planner.generate(goal["id"], request)
            with patch.object(
                planner,
                "_invoke_branch",
                AsyncMock(return_value=replacement),
            ):
                regenerated = await planner.regenerate_branch(
                    draft["id"],
                    DraftRegenerateRequest(client_id="week-1"),
                )

            by_id = {item["client_id"]: item for item in regenerated["draft"]["items"]}
            self.assertEqual(by_id["week-1"]["title"], "New outcome")
            self.assertEqual(by_id["month-2"]["title"], "Protected milestone")
            self.assertIn("new-day", by_id)
            self.assertNotIn("old-day", by_id)

    async def test_regenerate_approved_week_replaces_open_days_and_keeps_history(self):
        async with self.session_factory() as database:
            planning = PlanningService(database)
            goal = await planning.create_goal({
                "title": "Finish course",
                "definition_of_done": "Pass final project",
                "deadline": "2026-12-20",
                "importance": "medium",
                "weekly_capacity_minutes": 300,
            })
            month = await planning.create_plan_item({
                "title": "October milestone",
                "horizon": "month",
                "goal_id": goal["id"],
                "period_start": "2026-10-01",
            })
            week = await planning.create_plan_item({
                "title": "Old outcome",
                "horizon": "week",
                "goal_id": goal["id"],
                "parent_id": month["id"],
                "period_start": "2026-10-19",
            })
            old_open = await planning.create_plan_item({
                "title": "Old open task",
                "horizon": "day",
                "goal_id": goal["id"],
                "parent_id": week["id"],
                "planned_for": "2026-10-22",
                "estimate_minutes": 25,
            })
            completed = await planning.create_plan_item({
                "title": "Completed task",
                "horizon": "day",
                "goal_id": goal["id"],
                "parent_id": week["id"],
                "planned_for": "2026-10-20",
                "estimate_minutes": 25,
            })
            await planning.complete_plan_item(completed["id"])
            replacement = PlannerBranchPayload.model_validate({
                "items": [
                    {
                        "client_id": week["id"],
                        "parent_client_id": month["id"],
                        "horizon": "week",
                        "title": "New outcome",
                        "period_start": "2026-10-19",
                    },
                    {
                        "client_id": "new-day",
                        "parent_client_id": week["id"],
                        "horizon": "day",
                        "title": "New task",
                        "planned_for": "2026-10-23",
                        "estimate_minutes": 30,
                    },
                ],
            })
            planner = PlannerService(database, today=date(2026, 10, 23))
            with patch.object(
                planner, "_invoke_branch", AsyncMock(return_value=replacement)
            ):
                result = await planner.regenerate_approved_week(week["id"], "gemini")

            self.assertEqual(result["replaced_open_daily_tasks"], 1)
            self.assertEqual(result["retained_history_tasks"], 1)
            self.assertEqual((await planning.get_plan_item(old_open["id"]))["status"], "dropped")
            self.assertEqual((await planning.get_plan_item(completed["id"]))["status"], "completed")
            self.assertEqual((await planning.get_plan_item(week["id"]))["title"], "New outcome")
            created = await planning.get_plan_item(result["created_daily_tasks"][0]["id"])
            self.assertEqual(created["title"], "New task")


class PlanningMigrationTests(unittest.TestCase):
    def test_repeatable_legacy_backfill_preserves_ids_and_sessions(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE tasks (
                    id VARCHAR PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    completed BOOLEAN DEFAULT 0,
                    created_at DATETIME
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE sessions (
                    id VARCHAR PRIMARY KEY,
                    task_id VARCHAR,
                    duration INTEGER
                )
                """
            )
            connection.execute(
                text(
                    "INSERT INTO tasks (id, name, completed, created_at) "
                    "VALUES ('legacy-open', 'Open', 0, CURRENT_TIMESTAMP), "
                    "('legacy-done', 'Done', 1, CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO sessions (id, task_id, duration) "
                    "VALUES ('session-1', 'legacy-open', 1500)"
                )
            )

            _migrate_schema(connection)
            _migrate_schema(connection)

            rows = connection.execute(
                text("SELECT id, goal_id, planned_for, horizon, status FROM tasks ORDER BY id")
            ).mappings().all()
            self.assertEqual(rows[0]["id"], "legacy-done")
            self.assertEqual(rows[0]["horizon"], "day")
            self.assertEqual(rows[0]["status"], "completed")
            self.assertEqual(rows[1]["status"], "open")
            self.assertIsNone(rows[1]["goal_id"])
            self.assertIsNone(rows[1]["planned_for"])
            session_task = connection.execute(
                text("SELECT task_id FROM sessions WHERE id = 'session-1'")
            ).scalar_one()
            self.assertEqual(session_task, "legacy-open")

            task_columns = {
                column["name"] for column in inspect(connection).get_columns("tasks")
            }
            self.assertIn("parent_id", task_columns)
            self.assertIn("version", task_columns)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
