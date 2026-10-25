import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from langchain_core.messages import AIMessage

from app.services.agent_memory import AgentMemory
from app.services.pomo_agent import MAX_MEMORY_MESSAGES, PomoAgent


class AgentMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_survives_connection_restart_and_is_isolated_by_thread(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            memory_path = Path(temporary_directory) / "agent-memory.db"

            first_memory = AgentMemory()
            await first_memory.start(memory_path)
            first_model = AsyncMock()
            first_model.ainvoke.return_value = AIMessage(
                content="Task Alpha is the priority."
            )
            await PomoAgent(
                "openai",
                model=first_model,
                checkpointer=first_memory.checkpointer,
            ).chat(
                "Remember that Task Alpha is the priority.",
                thread_id="thread-memory-test",
                timezone_offset=420,
            )
            await first_memory.close()

            second_memory = AgentMemory()
            await second_memory.start(memory_path)
            try:
                second_model = AsyncMock()
                second_model.ainvoke.return_value = AIMessage(content="Task Alpha.")
                await PomoAgent(
                    "openai",
                    model=second_model,
                    checkpointer=second_memory.checkpointer,
                ).chat(
                    "Which task did I mention?",
                    thread_id="thread-memory-test",
                    timezone_offset=420,
                )

                remembered_messages = second_model.ainvoke.await_args.args[0]
                remembered_content = [message.content for message in remembered_messages]
                self.assertIn(
                    "Remember that Task Alpha is the priority.",
                    remembered_content,
                )
                self.assertIn("Task Alpha is the priority.", remembered_content)

                isolated_model = AsyncMock()
                isolated_model.ainvoke.return_value = AIMessage(content="I do not know yet.")
                await PomoAgent(
                    "openai",
                    model=isolated_model,
                    checkpointer=second_memory.checkpointer,
                ).chat(
                    "Which task did I mention?",
                    thread_id="another-thread",
                    timezone_offset=420,
                )
                isolated_content = [
                    message.content for message in isolated_model.ainvoke.await_args.args[0]
                ]
                self.assertNotIn(
                    "Remember that Task Alpha is the priority.",
                    isolated_content,
                )
            finally:
                await second_memory.close()

    async def test_memory_keeps_only_the_latest_twenty_conversation_messages(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            memory_path = Path(temporary_directory) / "bounded-memory.db"
            memory = AgentMemory()
            await memory.start(memory_path)
            saver = memory.checkpointer
            model = AsyncMock()
            model.ainvoke.side_effect = [
                AIMessage(content=f"Reply {index}") for index in range(12)
            ]
            agent = PomoAgent("openai", model=model, checkpointer=saver)

            try:
                for index in range(12):
                    await agent.chat(
                        f"Message {index}",
                        thread_id="bounded-thread",
                    )

                snapshot = await agent.graph.aget_state(
                    {"configurable": {"thread_id": "bounded-thread"}}
                )
                messages = snapshot.values["messages"]
                self.assertEqual(len(messages), MAX_MEMORY_MESSAGES)
                self.assertEqual(messages[0].content, "Message 2")
                self.assertEqual(messages[-1].content, "Reply 11")

                async with saver.conn.execute(
                    "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?",
                    ("bounded-thread",),
                ) as cursor:
                    checkpoint_count = (await cursor.fetchone())[0]
                self.assertEqual(checkpoint_count, 1)
            finally:
                await memory.close()


if __name__ == "__main__":
    unittest.main()
