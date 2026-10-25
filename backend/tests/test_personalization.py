import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.database import Base, _migrate_schema
from app.database.database import get_db
from app.main import app
from app.models.models import MemoryCorrection, PersonalMemory, UserActionSource, UserActionType
from app.services.habit_service import EventSpec, capture_behavior_events
from app.services.agent_runtime import PomoAgent
from app.services.memory_extractor import MemoryExtractor, process_user_memory
from app.services.personal_memory_schemas import MemoryCandidate
from app.services.personal_memory_service import PersonalMemoryService
from app.services.profile_service import ProfileService
from app.services.user_context_builder import UserContextBuilder


class PersonalizationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_default_profile_is_stable_and_independent_from_thread(self):
        async with self.session_factory() as database:
            service = ProfileService(database)
            first = await service.get_or_create_default()
            second = await service.get_or_create_default()
            self.assertEqual(first.id, second.id)

    async def test_memory_correction_supersedes_in_one_active_slot(self):
        async with self.session_factory() as database:
            service = PersonalMemoryService(database)
            old = await service.remember(
                MemoryCandidate(key="preferred_address", value="bro"),
                "request-1",
            )
            new = await service.remember(
                MemoryCandidate(key="preferred_address", value="An"),
                "request-2",
            )

            await database.refresh(old)
            self.assertFalse(old.active)
            self.assertEqual(old.superseded_by, new.id)
            active_count = await database.scalar(
                select(func.count()).select_from(PersonalMemory).where(PersonalMemory.active.is_(True))
            )
            correction = (await database.execute(select(MemoryCorrection))).scalar_one()
            self.assertEqual(active_count, 1)
            self.assertEqual(correction.operation.value, "corrected")

    async def test_repeated_same_memory_is_idempotent(self):
        async with self.session_factory() as database:
            service = PersonalMemoryService(database)
            first = await service.remember(
                MemoryCandidate(key="preferred_name", value="An"),
                "request-1",
            )
            repeated = await service.remember(
                MemoryCandidate(key="preferred_name", value="An"),
                "request-2",
            )

            count = await database.scalar(select(func.count()).select_from(PersonalMemory))
            correction_count = await database.scalar(
                select(func.count()).select_from(MemoryCorrection)
            )
            self.assertEqual(repeated.id, first.id)
            self.assertEqual(count, 1)
            self.assertEqual(correction_count, 0)

    async def test_never_mention_is_audited_and_excluded_from_context(self):
        async with self.session_factory() as database:
            service = PersonalMemoryService(database)
            memory = await service.remember(
                MemoryCandidate(key="preferred_name", value="An"),
                "request-1",
            )
            await service.deactivate(memory.id, "never_mention", "request-2")

            self.assertEqual(await service.list_active(), [])
            self.assertEqual(await UserContextBuilder(database).build(), {"explicit_preferences": []})
            correction = (await database.execute(select(MemoryCorrection))).scalar_one()
            self.assertEqual(correction.operation.value, "never_mention")

    async def test_extractor_accepts_explicit_low_risk_examples(self):
        extractor = MemoryExtractor()
        name = extractor.extract("Tên mình là An.")
        address = extractor.extract("Gọi mình là bro")
        style = extractor.extract("Nhắc ngắn thôi nhé")
        duration = extractor.extract("Mình thích focus 50 phút")

        self.assertEqual((name.candidates[0].key, name.candidates[0].value), ("preferred_name", "An"))
        self.assertEqual((address.candidates[0].key, address.candidates[0].value), ("preferred_address", "bro"))
        self.assertEqual(style.candidates[0].value, "concise")
        self.assertEqual(duration.candidates[0].value, 50)

    async def test_extractor_rejects_temporary_and_sensitive_statements(self):
        extractor = MemoryExtractor()
        self.assertEqual(extractor.extract("Hôm nay mình mệt").candidates, [])
        self.assertEqual(extractor.extract("Mình bị trầm cảm").candidates, [])
        self.assertEqual(extractor.extract("Có lẽ mình ghét task này").candidates, [])

    async def test_correction_statement_removes_old_address_and_saves_new_one(self):
        async with self.session_factory() as database:
            service = PersonalMemoryService(database)
            old = await service.remember(MemoryCandidate(key="preferred_address", value="bro"))
            result = await process_user_memory(
                database,
                "Đừng gọi mình là bro nữa, gọi mình là An.",
                "request-correction",
            )
            active = await service.list_active()

            self.assertEqual(result.removed_keys, ["preferred_address"])
            self.assertEqual(result.remembered_keys, ["preferred_address"])
            self.assertEqual(json.loads(active[0].value_json), "An")
            await database.refresh(old)
            self.assertEqual(old.superseded_by, active[0].id)
            correction = (await database.execute(select(MemoryCorrection))).scalar_one()
            self.assertEqual(correction.operation.value, "corrected")

    async def test_feature_flag_disables_capture_and_retrieval(self):
        async with self.session_factory() as database:
            with patch.dict("os.environ", {"PERSONALIZATION_ENABLED": "false"}):
                result = await process_user_memory(database, "Tên mình là An", "request-disabled")
                self.assertEqual(result.remembered_keys, [])
                self.assertEqual(await UserContextBuilder(database).build(), {})

    async def test_agent_injects_only_compact_active_context_across_threads(self):
        async with self.session_factory() as database:
            await PersonalMemoryService(database).remember(
                MemoryCandidate(key="preferred_name", value="An"),
                "request-private-source",
            )
            model = MagicMock()
            model.ainvoke = AsyncMock(return_value=AIMessage(content="Chào An"))
            model.bind_tools.return_value = model

            response = await PomoAgent("openai", model=model, database=database).chat(
                "Chào Pomo",
                thread_id="brand-new-thread",
            )

            prompt = model.ainvoke.await_args.args[0][0].content
            self.assertEqual(response["message"], "Chào An")
            self.assertIn('"preferred_name"', prompt)
            self.assertIn('"An"', prompt)
            self.assertNotIn("request-private-source", prompt)

    async def test_retrieval_filters_context_specific_preferences(self):
        async with self.session_factory() as database:
            service = PersonalMemoryService(database)
            await service.remember(MemoryCandidate(key="preferred_name", value="An"))
            await service.remember(MemoryCandidate(key="explicit_focus_duration", value=50))

            greeting = await UserContextBuilder(database).build("Xin chào")
            focus = await UserContextBuilder(database).build("Bắt đầu focus nhé")

            self.assertEqual(
                [item["key"] for item in greeting["explicit_preferences"]],
                ["preferred_name"],
            )
            self.assertEqual(
                {item["key"] for item in focus["explicit_preferences"]},
                {"preferred_name", "explicit_focus_duration"},
            )

    async def test_memory_context_failure_does_not_break_chat(self):
        async with self.session_factory() as database:
            model = MagicMock()
            model.ainvoke = AsyncMock(return_value=AIMessage(content="Still works"))
            model.bind_tools.return_value = model
            with patch(
                "app.services.agent_runtime.UserContextBuilder.build",
                AsyncMock(side_effect=RuntimeError("private value")),
            ):
                response = await PomoAgent("openai", model=model, database=database).chat("Hello")
            self.assertEqual(response["message"], "Still works")

    async def test_delete_all_keeps_profile_id_but_removes_memory_and_audit(self):
        async with self.session_factory() as database:
            profile = await ProfileService(database).get_or_create_default()
            service = PersonalMemoryService(database)
            memory = await service.remember(MemoryCandidate(key="preferred_name", value="An"))
            await service.deactivate(memory.id, "deleted")
            await service.delete_all()

            same_profile = await ProfileService(database).get_or_create_default()
            memories = await database.scalar(select(func.count()).select_from(PersonalMemory))
            corrections = await database.scalar(select(func.count()).select_from(MemoryCorrection))
            self.assertEqual(same_profile.id, profile.id)
            self.assertEqual(memories, 0)
            self.assertEqual(corrections, 0)

    async def test_schema_migration_is_repeatable_with_memory_indexes(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(_migrate_schema)
            await connection.run_sync(_migrate_schema)
            indexes = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_indexes("personal_memories")
            )
        self.assertIn("uq_personal_memories_active_key", {index["name"] for index in indexes})

class PersonalizationAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

        async def override_database():
            async with self.session_factory() as database:
                yield database

        app.dependency_overrides[get_db] = override_database

    async def asyncTearDown(self):
        app.dependency_overrides.clear()
        await self.engine.dispose()

    async def test_profile_memory_edit_delete_and_toggle_contract(self):
        async with self.session_factory() as database:
            memory = await PersonalMemoryService(database).remember(
                MemoryCandidate(key="preferred_name", value="An")
            )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            profile_response = await client.get("/api/relationship/profile")
            list_response = await client.get("/api/relationship/memories")
            edit_response = await client.patch(
                f"/api/relationship/memories/{memory.id}",
                json={"value": "Anh An"},
            )
            toggle_response = await client.patch(
                "/api/relationship/profile",
                json={"personalization_on": False},
            )
            delete_response = await client.request(
                "DELETE",
                f"/api/relationship/memories/{edit_response.json()['id']}",
                json={"action": "never_mention"},
            )

        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(list_response.json()[0]["value"], "An")
        self.assertEqual(edit_response.json()["value"], "Anh An")
        self.assertFalse(toggle_response.json()["personalization_on"])
        self.assertEqual(delete_response.json()["active"], False)

    async def test_habit_list_suggestion_and_dismiss_contract(self):
        async with self.session_factory() as database:
            await capture_behavior_events(database, [
                EventSpec(
                    UserActionType.TASK_SELECTED,
                    UserActionSource.UI,
                    "task",
                    f"task-{index}",
                    f"api-rank-{index}",
                    {"view": "today", "rank": 0, "visible_task_count": 3, "sort_mode": "importance"},
                )
                for index in range(5)
            ])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            habits_response = await client.get("/api/relationship/habits")
            suggestion_response = await client.get(
                "/api/relationship/focus-suggestion?view=today&timezone_offset=420"
            )
            habit_id = habits_response.json()[0]["id"]
            dismiss_response = await client.delete(f"/api/relationship/habits/{habit_id}")
            after_response = await client.get("/api/relationship/habits")

        self.assertEqual(habits_response.status_code, 200)
        self.assertEqual(suggestion_response.json()["task_rank"]["rank"], 0)
        self.assertEqual(dismiss_response.json(), {"id": habit_id, "active": False})
        self.assertEqual(after_response.json(), [])


if __name__ == "__main__":
    unittest.main()
