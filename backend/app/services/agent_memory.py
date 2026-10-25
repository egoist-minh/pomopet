from pathlib import Path
from typing import Any

import aiosqlite
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import ChannelVersions, Checkpoint, CheckpointMetadata
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.runtime_config import get_data_dir


def get_agent_memory_path() -> Path:
    return get_data_dir() / "pomo_agent_memory.db"


class BoundedAsyncSqliteSaver(AsyncSqliteSaver):
    """SQLite saver that retains only the latest state for each conversation."""

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        saved_config = await super().aput(
            config,
            checkpoint,
            metadata,
            new_versions,
        )
        configurable = saved_config["configurable"]
        thread_id = str(configurable["thread_id"])
        checkpoint_namespace = configurable.get("checkpoint_ns", "")
        checkpoint_id = str(configurable["checkpoint_id"])

        async with self.lock:
            await self.conn.execute(
                "DELETE FROM checkpoints "
                "WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id < ?",
                (thread_id, checkpoint_namespace, checkpoint_id),
            )
            await self.conn.execute(
                "DELETE FROM writes "
                "WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id < ?",
                (thread_id, checkpoint_namespace, checkpoint_id),
            )
            await self.conn.commit()

        return saved_config


class AgentMemory:
    def __init__(self) -> None:
        self._connection: aiosqlite.Connection | None = None
        self._checkpointer: BoundedAsyncSqliteSaver | None = None

    async def start(self, database_path: Path | None = None) -> None:
        if self._checkpointer is not None:
            return

        database_path = database_path or get_agent_memory_path()
        connection = await aiosqlite.connect(str(database_path))
        checkpointer = BoundedAsyncSqliteSaver(connection)
        try:
            await checkpointer.setup()
            await connection.execute(
                "CREATE TABLE IF NOT EXISTS pending_actions ("
                "action_id TEXT PRIMARY KEY, "
                "thread_id TEXT NOT NULL, "
                "provider TEXT NOT NULL, "
                "status TEXT NOT NULL, "
                "expires_at TEXT NOT NULL"
                ")"
            )
            await connection.commit()
        except Exception:
            await connection.close()
            raise

        self._connection = connection
        self._checkpointer = checkpointer

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
        self._connection = None
        self._checkpointer = None

    @property
    def checkpointer(self) -> BoundedAsyncSqliteSaver:
        if self._checkpointer is None:
            raise RuntimeError("Agent memory has not been initialized")
        return self._checkpointer

    async def get_recent_conversation(
        self,
        thread_id: str,
        *,
        limit: int = 8,
    ) -> list[dict[str, str]]:
        """Return a small, display-safe slice of the latest chat checkpoint."""
        checkpoint_tuple = await self.checkpointer.aget_tuple({
            "configurable": {"thread_id": thread_id},
        })
        if checkpoint_tuple is None:
            return []

        messages = checkpoint_tuple.checkpoint.get("channel_values", {}).get("messages", [])
        conversation: list[dict[str, str]] = []
        for message in messages:
            if not isinstance(message, (HumanMessage, AIMessage)):
                continue
            content = message.content
            if not isinstance(content, str):
                content = " ".join(
                    str(block.get("text", ""))
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            content = content.strip()
            if not content:
                continue
            conversation.append({
                "role": "user" if isinstance(message, HumanMessage) else "pet",
                "text": content[:600],
            })
        return conversation[-limit:]

    async def register_action(self, action: dict[str, Any]) -> None:
        checkpointer = self.checkpointer
        async with checkpointer.lock:
            await checkpointer.conn.execute(
                "DELETE FROM pending_actions WHERE thread_id = ?",
                (action["thread_id"],),
            )
            await checkpointer.conn.execute(
                "INSERT INTO pending_actions "
                "(action_id, thread_id, provider, status, expires_at) "
                "VALUES (?, ?, ?, 'pending', ?)",
                (
                    action["id"],
                    action["thread_id"],
                    action["provider"],
                    action["expires_at"],
                ),
            )
            await checkpointer.conn.commit()

    async def get_action(self, action_id: str) -> dict[str, str] | None:
        checkpointer = self.checkpointer
        async with checkpointer.lock, checkpointer.conn.execute(
            "SELECT action_id, thread_id, provider, status, expires_at "
            "FROM pending_actions WHERE action_id = ?",
            (action_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "thread_id": row[1],
            "provider": row[2],
            "status": row[3],
            "expires_at": row[4],
        }

    async def get_pending_action_for_thread(
        self,
        thread_id: str,
    ) -> dict[str, str] | None:
        checkpointer = self.checkpointer
        async with checkpointer.lock, checkpointer.conn.execute(
            "SELECT action_id, thread_id, provider, status, expires_at "
            "FROM pending_actions WHERE thread_id = ? AND status = 'pending'",
            (thread_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "thread_id": row[1],
            "provider": row[2],
            "status": row[3],
            "expires_at": row[4],
        }

    async def set_action_status(
        self,
        action_id: str,
        status: str,
        expected_status: str = "pending",
    ) -> bool:
        checkpointer = self.checkpointer
        async with checkpointer.lock:
            cursor = await checkpointer.conn.execute(
                "UPDATE pending_actions SET status = ? "
                "WHERE action_id = ? AND status = ?",
                (status, action_id, expected_status),
            )
            await checkpointer.conn.commit()
            return cursor.rowcount == 1


agent_memory = AgentMemory()
