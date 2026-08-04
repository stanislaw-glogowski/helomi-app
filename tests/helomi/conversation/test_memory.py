import asyncio
from pathlib import Path

from langchain.messages import AIMessage, HumanMessage

from helomi.conversation.memory import MemoryFact, SqliteConversationMemory


def test_sqlite_memory_persists_facts_searches_and_compacts_checkpoints(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        path = tmp_path / "db" / "memory.db"
        memory = SqliteConversationMemory(path)
        await memory.start()
        try:
            await memory.remember("user.city", "Staszek lives in Warszawa")
            await memory.remember("user.food", "Favourite food is pierogi")
            await memory.remember("user.city", "Staszek lives in Kraków")

            assert await memory.list() == (
                # List order is the stable key order, not insertion order.
                MemoryFact("user.city", "Staszek lives in Kraków"),
                MemoryFact("user.food", "Favourite food is pierogi"),
            )
            facts = await memory.search("gdzie mieszka Staszek")
            assert [fact.key for fact in facts] == ["user.city"]
            assert await memory.search('" OR garbage') == ()

            saver = memory.checkpointer
            config = {"configurable": {"thread_id": "helomi", "checkpoint_ns": ""}}
            checkpoint = {
                "id": "001",
                "ts": "2026-08-04T00:00:00Z",
                "channel_values": {"messages": [HumanMessage("one")]},
                "channel_versions": {},
                "versions_seen": {},
                "updated_channels": None,
            }
            await saver.aput(config, checkpoint, {}, {})
            newer = {
                **checkpoint,
                "id": "002",
                "channel_values": {"messages": [AIMessage("two")]},
            }
            await saver.aput(config, newer, {}, {})
            await memory.compact("helomi")
            state = await saver.aget_tuple(config)
            assert state is not None
            assert state.config["configurable"]["checkpoint_id"] == "002"
        finally:
            await memory.stop()

        reopened = SqliteConversationMemory(path)
        await reopened.start()
        try:
            assert [fact.key for fact in await reopened.list()] == [
                "user.city",
                "user.food",
            ]
            assert await reopened.forget("user.city")
            assert not await reopened.forget("user.city")
        finally:
            await reopened.stop()

    asyncio.run(scenario())
