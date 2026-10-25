import json
import unittest
from datetime import datetime, timedelta

from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.database import Base, _migrate_schema
from app.models.models import (
    HabitProfile,
    PlanHorizon,
    PlanItemStatus,
    Priority,
    Session,
    Task,
    UserActionEvent,
    UserActionSource,
    UserActionType,
)
from app.services.habit_service import EventSpec, HabitService, capture_behavior_events
from app.services.personal_memory_schemas import MemoryCandidate
from app.services.personal_memory_service import PersonalMemoryService
from app.services.session_service import SessionService
from app.services.memory_extractor import process_user_memory


class BehavioralHabitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _capture_durations(self, database, minutes, hours, prefix):
        specs = [
            EventSpec(
                UserActionType.SESSION_STARTED,
                UserActionSource.UI,
                "session",
                f"{prefix}-{index}",
                f"{prefix}-{index}",
                {"duration_minutes": minutes, "timezone_offset": 0},
                datetime(2026, 10, 20, hour, 0) + timedelta(days=index),
            )
            for index, hour in enumerate(hours)
        ]
        await capture_behavior_events(database, specs)

    async def test_event_capture_is_idempotent_and_context_is_allowlisted(self):
        async with self.session_factory() as database:
            spec = EventSpec(
                UserActionType.TASK_SELECTED,
                UserActionSource.UI,
                "task",
                "task-1",
                "request-1:task-selected",
                {
                    "view": "today", "rank": 0, "visible_task_count": 3,
                    "sort_mode": "importance", "task_title": "private title",
                },
            )
            await capture_behavior_events(database, [spec, spec])
            await capture_behavior_events(database, [spec])

            events = (await database.execute(select(UserActionEvent))).scalars().all()
            self.assertEqual(len(events), 1)
            context = json.loads(events[0].context_json)
            self.assertEqual(context["view"], "today")
            self.assertNotIn("task_title", context)

    async def test_duration_habits_split_by_time_context_and_prefill_at_high_confidence(self):
        async with self.session_factory() as database:
            await self._capture_durations(database, 50, [8, 8, 8, 8, 8], "morning")
            await self._capture_durations(database, 25, [14, 14, 14, 14, 14], "afternoon")

            morning = await HabitService(database).focus_suggestion(
                view="today", timezone_offset=0
            )
            # Pin query-time context without depending on the execution host clock.
            habits = (await database.execute(select(HabitProfile).where(
                HabitProfile.habit_key == "focus_duration",
            ))).scalars().all()
            by_context = {habit.context_key: habit for habit in habits}
            morning_habit = by_context['{"time_bucket":"morning"}']
            afternoon_habit = by_context['{"time_bucket":"afternoon"}']
            self.assertEqual(json.loads(morning_habit.value_json), 50)
            self.assertEqual(json.loads(afternoon_habit.value_json), 25)
            self.assertTrue(morning_habit.active)
            self.assertGreaterEqual(morning_habit.confidence, 0.78)
            self.assertEqual(morning["task_rank"], None)

    async def test_minimum_sample_and_repeated_override_reduce_confidence(self):
        async with self.session_factory() as database:
            await self._capture_durations(database, 50, [8, 8], "few")
            habit = (await database.execute(select(HabitProfile).where(
                HabitProfile.habit_key == "focus_duration",
                HabitProfile.context_key == '{"time_bucket":"morning"}',
            ))).scalar_one()
            self.assertFalse(habit.active)

            await self._capture_durations(database, 50, [8, 8, 8], "old-choice")
            strong_confidence = habit.confidence
            await self._capture_durations(database, 25, [8, 8, 8, 8, 8], "override")
            await database.refresh(habit)
            self.assertLess(habit.confidence, strong_confidence)
            self.assertFalse(habit.active)

    async def test_task_rank_requires_evidence_and_returns_explanation(self):
        async with self.session_factory() as database:
            await capture_behavior_events(database, [
                EventSpec(
                    UserActionType.TASK_SELECTED, UserActionSource.UI, "task", f"task-{index}",
                    f"rank-{index}",
                    {"view": "today", "rank": 0, "visible_task_count": 4, "sort_mode": "importance"},
                )
                for index in range(5)
            ])
            suggestion = await HabitService(database).focus_suggestion(view="today")
            self.assertEqual(suggestion["task_rank"]["rank"], 0)
            self.assertEqual(suggestion["task_rank"]["evidence_count"], 5)
            self.assertIn("5 recent task choices", suggestion["task_rank"]["explanation"])

    async def test_old_evidence_decays_without_deleting_events(self):
        async with self.session_factory() as database:
            old = datetime.utcnow() - timedelta(days=180)
            await capture_behavior_events(database, [
                EventSpec(
                    UserActionType.SESSION_STARTED, UserActionSource.UI,
                    "session", f"old-{index}", f"old-{index}",
                    {"duration_minutes": 50}, old + timedelta(minutes=index),
                )
                for index in range(5)
            ])
            habit = (await database.execute(select(HabitProfile).where(
                HabitProfile.habit_key == "focus_duration",
                HabitProfile.context_key == "{}",
            ))).scalar_one()
            self.assertFalse(habit.active)
            self.assertLess(habit.confidence, 0.1)
            self.assertEqual(await database.scalar(select(func.count()).select_from(UserActionEvent)), 5)

    async def test_explicit_duration_wins_over_inferred_habit(self):
        async with self.session_factory() as database:
            await self._capture_durations(database, 50, [8, 8, 8, 8, 8], "habit")
            await PersonalMemoryService(database).remember(
                MemoryCandidate(key="explicit_focus_duration", value=25)
            )
            suggestion = await HabitService(database).focus_suggestion(view="today")
            self.assertEqual(suggestion["duration"]["minutes"], 25)
            self.assertEqual(suggestion["duration"]["source"], "explicit_preference")

    async def test_direct_correction_suppresses_duration_habit(self):
        async with self.session_factory() as database:
            await self._capture_durations(database, 50, [8, 8, 8, 8, 8], "habit-correction")
            await process_user_memory(
                database,
                "Đừng mặc định 50 phút nữa",
                "correction-request",
            )
            suggestion = await HabitService(database).focus_suggestion(view="today")
            habits = (await database.execute(select(HabitProfile).where(
                HabitProfile.habit_key == "focus_duration",
            ))).scalars().all()
            self.assertIsNone(suggestion["duration"])
            self.assertTrue(all(habit.dismissed and not habit.active for habit in habits))

    async def test_session_keeps_initial_duration_after_extension_and_captures_events(self):
        async with self.session_factory() as database:
            database.add(Task(
                id="task-1", name="Focus", priority=Priority.MEDIUM,
                completed=False, horizon=PlanHorizon.DAY, status=PlanItemStatus.OPEN,
            ))
            await database.commit()
            service = SessionService(database)
            started = await service.start_session(
                "task-1", 1500, idempotency_key="start-1",
                action_context={"view": "today", "rank": 0, "visible_task_count": 1, "sort_mode": "importance"},
            )
            await service.extend_session(300, idempotency_key="extend-1")

            session = await database.get(Session, started["id"])
            self.assertEqual(session.initial_duration, 1500)
            self.assertEqual(session.duration, 1800)
            self.assertEqual(session.initial_duration_source, "selected")
            event_types = set((await database.execute(select(UserActionEvent.event_type))).scalars().all())
            self.assertEqual(
                event_types,
                {UserActionType.TASK_SELECTED, UserActionType.SESSION_STARTED, UserActionType.SESSION_EXTENDED},
            )

    async def test_delete_all_removes_behavioral_data_but_keeps_productivity(self):
        async with self.session_factory() as database:
            database.add(Task(
                id="task-keep", name="Keep", priority=Priority.MEDIUM,
                completed=False, horizon=PlanHorizon.DAY, status=PlanItemStatus.OPEN,
            ))
            await database.commit()
            await self._capture_durations(database, 25, [8, 8, 8], "delete")
            await PersonalMemoryService(database).delete_all()
            self.assertEqual(await database.scalar(select(func.count()).select_from(UserActionEvent)), 0)
            self.assertEqual(await database.scalar(select(func.count()).select_from(HabitProfile)), 0)
            self.assertIsNotNone(await database.get(Task, "task-keep"))

    async def test_legacy_session_migration_is_repeatable_and_marks_quality(self):
        legacy = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with legacy.begin() as connection:
            await connection.exec_driver_sql("CREATE TABLE tasks (id VARCHAR PRIMARY KEY)")
            await connection.exec_driver_sql(
                "CREATE TABLE sessions (id VARCHAR PRIMARY KEY, duration INTEGER)"
            )
            await connection.exec_driver_sql(
                "INSERT INTO sessions (id, duration) VALUES ('legacy', 1800)"
            )
            await connection.run_sync(_migrate_schema)
            await connection.run_sync(_migrate_schema)
            columns = await connection.run_sync(
                lambda sync_connection: {column["name"] for column in inspect(sync_connection).get_columns("sessions")}
            )
            row = (await connection.exec_driver_sql(
                "SELECT initial_duration, initial_duration_source FROM sessions WHERE id = 'legacy'"
            )).one()
        await legacy.dispose()
        self.assertIn("initial_duration", columns)
        self.assertEqual(tuple(row), (1800, "legacy_total"))


if __name__ == "__main__":
    unittest.main()
