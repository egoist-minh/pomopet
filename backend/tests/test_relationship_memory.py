import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage
from sqlalchemy import func, inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.database import Base, _migrate_schema, get_db
from app.main import app
from app.models.models import RelationshipEpisode, RelationshipMemoryAudit, RelationshipMemoryStatus
from app.services.agent_runtime import PomoAgent
from app.services.personal_memory_service import PersonalMemoryService
from app.services.planning_service import PlanningService
from app.services.profile_service import ProfileService
from app.services.relationship_extractor import RelationshipExtractor
from app.services.relationship_memory_service import RelationshipMemoryService
from app.services.relationship_schemas import EpisodeCandidate, RitualCandidate
from app.services.session_service import SessionService
from app.services.user_context_builder import UserContextBuilder


def milestone(reference, summary="Completed milestone: Ship the thesis"):
    return EpisodeCandidate(
        kind="milestone",
        summary=summary,
        source_type="verified_app_event",
        source_reference=reference,
        entity_type="plan_item",
        entity_id="month-1",
        salience=0.9,
        confidence=1.0,
        emotional_tone="positive",
    )


class RelationshipMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.run_sync(_migrate_schema)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_milestone_is_idempotent_and_consolidation_keeps_sources(self):
        async with self.sessions() as database:
            service = RelationshipMemoryService(database)
            first = await service.create_episode(milestone("event-1"))
            retry = await service.create_episode(milestone("event-1"))
            consolidated = await service.create_episode(milestone("event-2"))
            count = await database.scalar(select(func.count()).select_from(RelationshipEpisode))
            self.assertEqual(first.id, retry.id)
            self.assertEqual(first.id, consolidated.id)
            self.assertEqual(count, 1)
            self.assertEqual(
                service.serialize_episode(consolidated)["source_references"],
                ["event-1", "event-2"],
            )

    async def test_only_salient_evidenced_candidates_activate(self):
        async with self.sessions() as database:
            service = RelationshipMemoryService(database)
            low = milestone("low")
            low.salience = 0.2
            suggestion = milestone("suggestion")
            suggestion.source_type = "agent_suggestion"
            unlinked = milestone("unlinked")
            unlinked.entity_id = None
            self.assertIsNone(await service.create_episode(low))
            self.assertIsNone(await service.create_episode(suggestion))
            self.assertIsNone(await service.create_episode(unlinked))
            self.assertEqual(await database.scalar(select(func.count()).select_from(RelationshipEpisode)), 0)

    async def test_suppression_excludes_retrieval_and_is_audited(self):
        async with self.sessions() as database:
            service = RelationshipMemoryService(database)
            archived = await service.create_episode(milestone("archive", "Completed milestone: Publish paper"))
            blocked = await service.create_episode(milestone("never", "Completed milestone: Defend thesis"))
            await service.set_episode_status(archived.id, "archived", "ui-archive")
            await service.set_episode_status(blocked.id, "never_mention", "ui-never")
            self.assertEqual(await service.retrieve("paper thesis"), [])
            self.assertEqual(await database.scalar(select(func.count()).select_from(RelationshipMemoryAudit)), 2)
            state = await service.get_relational_state()
            self.assertEqual(state.evidence_count, 0)
            self.assertEqual(state.pride, 0.0)

    async def test_fts_retrieval_never_fabricates_or_returns_unrelated_data(self):
        async with self.sessions() as database:
            service = RelationshipMemoryService(database)
            target = await service.create_episode(milestone("thesis", "Completed milestone: Publish thesis research"))
            await service.create_episode(milestone("run", "Completed milestone: Finish marathon training"))
            found = await service.retrieve("How did the thesis research go?")
            self.assertEqual([item.id for item in found], [target.id])
            self.assertEqual(await service.retrieve("Tell me about cooking"), [])
            self.assertEqual(found[0].summary, "Completed milestone: Publish thesis research")

    async def test_retrieval_falls_back_to_structured_sql_without_fts(self):
        async with self.sessions() as database:
            service = RelationshipMemoryService(database)
            target = await service.create_episode(milestone("fallback", "Completed milestone: Publish handbook"))
            await database.execute(text("DROP TABLE relationship_episode_fts"))
            await database.commit()
            found = await service.retrieve("publish handbook")
            self.assertEqual([item.id for item in found], [target.id])

    async def test_stale_low_salience_episode_archives_but_milestone_does_not_decay(self):
        async with self.sessions() as database:
            service = RelationshipMemoryService(database)
            low = await service.create_episode(EpisodeCandidate(
                kind="shared_event",
                summary="A modest shared checkpoint",
                source_type="explicit_user",
                source_reference="old-low",
                salience=0.7,
                confidence=1.0,
            ))
            important = await service.create_episode(milestone("old-milestone"))
            old_time = datetime.utcnow() - timedelta(days=365)
            low.updated_at = old_time
            important.updated_at = old_time
            await database.commit()
            active = await service.list_episodes()
            await database.refresh(low)
            await database.refresh(important)
            self.assertEqual([item.id for item in active], [important.id])
            self.assertEqual(low.status, RelationshipMemoryStatus.ARCHIVED)
            self.assertEqual(important.status, RelationshipMemoryStatus.ACTIVE)

    async def test_separate_consent_gates_provider_context(self):
        async with self.sessions() as database:
            await RelationshipMemoryService(database).create_episode(
                milestone("private-source", "Completed milestone: Publish thesis")
            )
            local_only = await UserContextBuilder(database).build("thesis")
            await ProfileService(database).update_default({"relationship_context_on": True})
            opted_in = await UserContextBuilder(database).build("thesis")
            self.assertNotIn("relationship_context", local_only)
            self.assertEqual(
                opted_in["relationship_context"]["shared_episodes"][0]["summary"],
                "Completed milestone: Publish thesis",
            )
            self.assertNotIn("private-source", str(opted_in))
            self.assertNotIn("source_reference", str(opted_in))

    async def test_relational_state_is_bounded_and_versioned(self):
        async with self.sessions() as database:
            service = RelationshipMemoryService(database)
            for index in range(30):
                await service.create_episode(milestone(f"event-{index}"))
            state = await service.get_relational_state()
            values = [state.familiarity, state.warmth, state.playfulness, state.concern, state.pride]
            self.assertTrue(all(0 <= value <= 1 for value in values))
            self.assertEqual(state.rule_version, "relationship-v1")
            self.assertEqual(state.evidence_count, 30)

    async def test_ritual_requires_confirmation_and_never_reactivates_suppressed(self):
        async with self.sessions() as database:
            service = RelationshipMemoryService(database)
            candidate = RitualCandidate(
                label="Celebration",
                description="say pom pom after a milestone",
                source_reference="message-1",
            )
            self.assertIsNone(await service.create_ritual(candidate))
            candidate.explicitly_confirmed = True
            ritual = await service.create_ritual(candidate)
            await service.set_ritual_status(ritual.id, "never_mention")
            repeated = candidate.model_copy(update={"source_reference": "message-2"})
            self.assertEqual((await service.create_ritual(repeated)).status.value, "never_mention")
            self.assertEqual(await service.list_rituals(), [])

    async def test_extractor_is_conservative_and_blocks_sensitive_content(self):
        extractor = RelationshipExtractor()
        self.assertEqual(extractor.extract("I completed a task", "request-1").episodes, [])
        explicit = extractor.extract("Remember this shared moment: we shipped PomoPet", "request-2")
        ritual = extractor.extract("Our ritual is say pom pom after a milestone", "request-3")
        sensitive = extractor.extract("Remember this shared moment: my depression diagnosis", "request-4")
        self.assertEqual(explicit.episodes[0].summary, "we shipped PomoPet")
        self.assertTrue(ritual.rituals[0].explicitly_confirmed)
        self.assertEqual(sensitive.episodes, [])

    async def test_delete_all_removes_relationship_layers_and_resets_consent(self):
        async with self.sessions() as database:
            planning = PlanningService(database)
            task = await planning.create_plan_item({
                "title": "Keep productivity data",
                "horizon": "day",
                "planned_for": "2026-11-01",
            })
            session = await SessionService(database).start_session(task["id"], 1500)
            await RelationshipMemoryService(database).create_episode(milestone("delete"))
            await ProfileService(database).update_default({"relationship_context_on": True})
            await PersonalMemoryService(database).delete_all()
            profile = await ProfileService(database).get_or_create_default()
            self.assertFalse(profile.relationship_context_on)
            self.assertEqual(await database.scalar(select(func.count()).select_from(RelationshipEpisode)), 0)
            self.assertIsNotNone(await planning.get_plan_item(task["id"]))
            self.assertEqual((await SessionService(database).get_current_session())["id"], session["id"])

    async def test_only_completed_monthly_milestone_auto_creates_episode(self):
        async with self.sessions() as database:
            planning = PlanningService(database)
            goal = await planning.create_goal({
                "title": "Ship PomoPet",
                "definition_of_done": "Release is published",
                "deadline": "2026-12-31",
                "importance": "high",
                "weekly_capacity_minutes": 300,
            })
            month = await planning.create_plan_item({
                "title": "Publish v1",
                "horizon": "month",
                "goal_id": goal["id"],
                "period_start": "2026-11-01",
            })
            day = await planning.create_plan_item({
                "title": "Routine cleanup",
                "horizon": "day",
                "planned_for": "2026-11-01",
            })
            await planning.complete_plan_item(month["id"], month["version"])
            await planning.complete_plan_item(day["id"], day["version"])
            episodes = list((await database.execute(select(RelationshipEpisode))).scalars().all())
            self.assertEqual(len(episodes), 1)
            self.assertEqual(episodes[0].entity_id, month["id"])
            self.assertEqual(episodes[0].summary, "Completed milestone: Publish v1")

    async def test_episode_capture_failure_does_not_undo_completed_milestone(self):
        async with self.sessions() as database:
            planning = PlanningService(database)
            goal = await planning.create_goal({
                "title": "Safe fallback", "definition_of_done": "Done",
                "deadline": "2026-12-31", "importance": "high",
                "weekly_capacity_minutes": 60,
            })
            month = await planning.create_plan_item({
                "title": "Durable milestone", "horizon": "month",
                "goal_id": goal["id"], "period_start": "2026-11-01",
            })
            with patch(
                "app.services.relationship_memory_service.RelationshipMemoryService.capture_milestone",
                AsyncMock(side_effect=RuntimeError("private failure")),
            ):
                completed = await planning.complete_plan_item(month["id"], month["version"])
            self.assertEqual(completed["status"], "completed")
            self.assertEqual((await planning.get_plan_item(month["id"]))["status"], "completed")

    async def test_agent_policy_is_safe_and_unconsented_episode_is_absent(self):
        async with self.sessions() as database:
            await RelationshipMemoryService(database).create_episode(
                milestone("private", "Completed milestone: Private thesis")
            )
            model = MagicMock()
            model.ainvoke = AsyncMock(return_value=AIMessage(content="Still safe"))
            model.bind_tools.return_value = model
            await PomoAgent("openai", model=model, database=database).chat("Tell me about thesis")
            prompt = model.ainvoke.await_args.args[0][0].content
            self.assertNotIn("Private thesis", prompt)
            self.assertIn("Do not imply consciousness", prompt)
            self.assertIn("relationship state", prompt)
            self.assertIn("quoted user data", prompt)

    async def test_migration_is_repeatable_and_builds_fts(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(_migrate_schema)
            await connection.run_sync(_migrate_schema)
            tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
            fts_name = (await connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='relationship_episode_fts'"
            )).scalar_one_or_none()
        self.assertIn("relationship_episodes", tables)
        self.assertEqual(fts_name, "relationship_episode_fts")

    async def test_legacy_profile_migration_preserves_rows_and_defaults_consent_off(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.exec_driver_sql("CREATE TABLE tasks (id VARCHAR PRIMARY KEY)")
                await connection.exec_driver_sql("CREATE TABLE sessions (id VARCHAR PRIMARY KEY)")
                await connection.exec_driver_sql(
                    "CREATE TABLE user_profiles (id VARCHAR PRIMARY KEY, display_name VARCHAR, "
                    "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, "
                    "personalization_on BOOLEAN NOT NULL, memory_prompts_on BOOLEAN NOT NULL)"
                )
                await connection.exec_driver_sql(
                    "INSERT INTO user_profiles VALUES "
                    "('legacy-profile', 'An', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, 1)"
                )
                await connection.run_sync(Base.metadata.create_all)
                await connection.run_sync(_migrate_schema)
                row = (await connection.exec_driver_sql(
                    "SELECT id, display_name, relationship_context_on FROM user_profiles"
                )).one()
            self.assertEqual(tuple(row), ("legacy-profile", "An", 0))
        finally:
            await engine.dispose()


class RelationshipMemoryAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.run_sync(_migrate_schema)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

        async def override_database():
            async with self.sessions() as database:
                yield database

        app.dependency_overrides[get_db] = override_database

    async def asyncTearDown(self):
        app.dependency_overrides.clear()
        await self.engine.dispose()

    async def test_episode_ritual_state_consent_and_suppression_contract(self):
        async with self.sessions() as database:
            service = RelationshipMemoryService(database)
            episode = await service.create_episode(milestone("event-api"))
            ritual = await service.create_ritual(RitualCandidate(
                label="Celebration",
                description="say pom pom",
                source_reference="message-api",
                explicitly_confirmed=True,
            ))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            episodes = await client.get("/api/relationship/episodes")
            rituals = await client.get("/api/relationship/rituals")
            state = await client.get("/api/relationship/relational-state")
            consent = await client.patch("/api/relationship/profile", json={"relationship_context_on": True})
            archived = await client.request("DELETE", f"/api/relationship/episodes/{episode.id}", json={"action": "archived"})
            never = await client.request("DELETE", f"/api/relationship/rituals/{ritual.id}", json={"action": "never_mention"})
        self.assertEqual(episodes.json()[0]["source_reference"], "event-api")
        self.assertEqual(rituals.json()[0]["evidence_count"], 1)
        self.assertEqual(state.json()["rule_version"], "relationship-v1")
        self.assertTrue(consent.json()["relationship_context_on"])
        self.assertEqual(archived.json()["status"], "archived")
        self.assertEqual(never.json()["status"], "never_mention")


if __name__ == "__main__":
    unittest.main()
