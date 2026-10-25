from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.runtime_config import get_data_dir

DATABASE_PATH = get_data_dir() / "pomopet.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH.as_posix()}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


def _migrate_schema(connection):
    table_names = {
        row[0]
        for row in connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "user_profiles" in table_names:
        profile_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(user_profiles)").fetchall()
        }
        profile_column_definitions = {
            "relationship_context_on": "BOOLEAN NOT NULL DEFAULT 0",
            "proactive_enabled": "BOOLEAN NOT NULL DEFAULT 0",
            "proactive_jokes_on": "BOOLEAN NOT NULL DEFAULT 1",
            "proactive_planning_on": "BOOLEAN NOT NULL DEFAULT 1",
        }
        for column_name, definition in profile_column_definitions.items():
            if column_name not in profile_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE user_profiles ADD COLUMN {column_name} {definition}"
                )

    if "tasks" not in table_names or "sessions" not in table_names:
        return

    task_columns = {
        row[1] for row in connection.exec_driver_sql("PRAGMA table_info(tasks)").fetchall()
    }
    task_column_definitions = {
        "estimated_duration": "INTEGER",
        "goal_id": "VARCHAR",
        "parent_id": "VARCHAR",
        "horizon": "VARCHAR NOT NULL DEFAULT 'day'",
        "planned_for": "VARCHAR",
        "period_start": "VARCHAR",
        "status": "VARCHAR NOT NULL DEFAULT 'open'",
        "version": "INTEGER NOT NULL DEFAULT 1",
        "updated_at": "DATETIME",
    }
    for column_name, definition in task_column_definitions.items():
        if column_name in task_columns:
            continue
        connection.exec_driver_sql(
            f"ALTER TABLE tasks ADD COLUMN {column_name} {definition}"
        )

    # Existing tasks become Inbox daily actions. IDs are deliberately unchanged,
    # so sessions keep pointing at the same records.
    connection.exec_driver_sql(
        "UPDATE tasks SET horizon = 'day' WHERE horizon IS NULL OR horizon = ''"
    )
    if "completed" in task_columns:
        connection.exec_driver_sql(
            """
            UPDATE tasks
            SET status = CASE WHEN completed = 1 THEN 'completed' ELSE 'open' END
            WHERE status IS NULL OR status = '' OR
                  (completed = 1 AND status = 'open')
            """
        )
    else:
        connection.exec_driver_sql(
            "UPDATE tasks SET status = 'open' WHERE status IS NULL OR status = ''"
        )
    connection.exec_driver_sql(
        "UPDATE tasks SET version = 1 WHERE version IS NULL OR version < 1"
    )
    if "created_at" in task_columns:
        connection.exec_driver_sql(
            "UPDATE tasks SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
        )
    else:
        connection.exec_driver_sql(
            "UPDATE tasks SET updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)"
        )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_tasks_goal_id ON tasks (goal_id)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_tasks_parent_id ON tasks (parent_id)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_tasks_planned_for ON tasks (planned_for)"
    )

    session_columns = {
        row[1] for row in connection.exec_driver_sql("PRAGMA table_info(sessions)").fetchall()
    }
    if "penalty_seconds" not in session_columns:
        connection.exec_driver_sql(
            "ALTER TABLE sessions ADD COLUMN penalty_seconds INTEGER NOT NULL DEFAULT 0"
        )
    if "initial_duration" not in session_columns:
        connection.exec_driver_sql(
            "ALTER TABLE sessions ADD COLUMN initial_duration INTEGER"
        )
    if "initial_duration_source" not in session_columns:
        connection.exec_driver_sql(
            "ALTER TABLE sessions ADD COLUMN initial_duration_source "
            "VARCHAR NOT NULL DEFAULT 'legacy_total'"
        )
    if "duration" in session_columns:
        connection.exec_driver_sql(
            "UPDATE sessions SET initial_duration = duration "
            "WHERE initial_duration IS NULL"
        )
        connection.exec_driver_sql(
            "UPDATE sessions SET initial_duration_source = 'legacy_total' "
            "WHERE initial_duration_source IS NULL OR initial_duration_source = ''"
        )
    else:
        connection.exec_driver_sql(
            "UPDATE sessions SET initial_duration_source = 'legacy_unknown' "
            "WHERE initial_duration IS NULL"
        )

    # P1-A profile and memory tables are created by metadata.create_all. These
    # indexes are repeated here so upgrades remain idempotent for older local DBs.
    if "personal_memories" in table_names:
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_personal_memories_profile_active "
            "ON personal_memories (profile_id, active)"
        )
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_personal_memories_active_key "
            "ON personal_memories (profile_id, kind, key, scope) WHERE active = 1"
        )
    if "user_action_events" in table_names:
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_user_action_events_profile_time "
            "ON user_action_events (profile_id, occurred_at)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_user_action_events_profile_type "
            "ON user_action_events (profile_id, event_type)"
        )
    if "habit_profiles" in table_names:
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_habit_profiles_scope "
            "ON habit_profiles (profile_id, habit_key, context_key)"
        )
    if "relationship_episodes" in table_names:
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_relationship_episodes_profile_status "
            "ON relationship_episodes (profile_id, status)"
        )
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_relationship_episodes_source "
            "ON relationship_episodes (profile_id, source_reference) "
            "WHERE source_reference IS NOT NULL"
        )
        # FTS is a disposable search index. Structured rows remain authoritative,
        # and retrieval falls back to SQL token matching if SQLite lacks FTS5.
        try:
            connection.exec_driver_sql(
                "CREATE VIRTUAL TABLE IF NOT EXISTS relationship_episode_fts "
                "USING fts5(episode_id UNINDEXED, profile_id UNINDEXED, summary, "
                "tokenize='unicode61 remove_diacritics 2')"
            )
            connection.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS relationship_episode_fts_insert "
                "AFTER INSERT ON relationship_episodes BEGIN "
                "INSERT INTO relationship_episode_fts(episode_id, profile_id, summary) "
                "VALUES (new.id, new.profile_id, new.summary); END"
            )
            connection.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS relationship_episode_fts_update "
                "AFTER UPDATE OF summary, profile_id ON relationship_episodes BEGIN "
                "DELETE FROM relationship_episode_fts WHERE episode_id = old.id; "
                "INSERT INTO relationship_episode_fts(episode_id, profile_id, summary) "
                "VALUES (new.id, new.profile_id, new.summary); END"
            )
            connection.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS relationship_episode_fts_delete "
                "AFTER DELETE ON relationship_episodes BEGIN "
                "DELETE FROM relationship_episode_fts WHERE episode_id = old.id; END"
            )
            connection.exec_driver_sql("DELETE FROM relationship_episode_fts")
            connection.exec_driver_sql(
                "INSERT INTO relationship_episode_fts(episode_id, profile_id, summary) "
                "SELECT id, profile_id, summary FROM relationship_episodes"
            )
        except Exception:
            # Some SQLite builds omit FTS5. This must not prevent startup; the
            # relationship service uses deterministic structured SQL fallback.
            pass


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_schema)

async def get_db():
    async with async_session() as session:
        yield session
