from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


@dataclass(frozen=True, slots=True)
class MemoryFact:
    key: str
    content: str


class ConversationMemory(ABC):
    """Own one profile's durable graph state and explicit long-term facts."""

    @property
    @abstractmethod
    def checkpointer(self) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def remember(self, key: str, content: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list(self) -> tuple[MemoryFact, ...]:
        raise NotImplementedError

    @abstractmethod
    async def forget(self, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def search(self, query: str, *, limit: int = 5) -> tuple[MemoryFact, ...]:
        raise NotImplementedError

    @abstractmethod
    async def compact(self, thread_id: str) -> None:
        raise NotImplementedError


class InMemoryConversationMemory(ConversationMemory):
    """Test-only memory implementation with process-lifetime state."""

    def __init__(self) -> None:
        self._checkpointer = InMemorySaver()
        self._facts: dict[str, str] = {}

    @property
    def checkpointer(self) -> InMemorySaver:
        return self._checkpointer

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def remember(self, key: str, content: str) -> None:
        self._facts[_key(key)] = _content(content)

    async def list(self) -> tuple[MemoryFact, ...]:
        return tuple(MemoryFact(key, self._facts[key]) for key in sorted(self._facts))

    async def forget(self, key: str) -> bool:
        return self._facts.pop(_key(key), None) is not None

    async def search(self, query: str, *, limit: int = 5) -> tuple[MemoryFact, ...]:
        terms = _terms(query)
        if not terms or limit < 1:
            return ()
        return tuple(
            MemoryFact(key, content)
            for key, content in sorted(self._facts.items())
            if any(term in f"{key} {content}".lower() for term in terms)
        )[:limit]

    async def compact(self, thread_id: str) -> None:
        pass


class SqliteConversationMemory(ConversationMemory):
    """SQLite-backed profile memory with LangGraph checkpoints and FTS facts."""

    _FACTS_SCHEMA = """
        CREATE TABLE IF NOT EXISTS memory_facts (
            key TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS memory_facts_fts USING fts5(
            key UNINDEXED,
            content,
            tokenize='unicode61 remove_diacritics 2'
        );
        CREATE TRIGGER IF NOT EXISTS memory_facts_insert AFTER INSERT ON memory_facts
        BEGIN
            INSERT INTO memory_facts_fts(rowid, key, content)
            VALUES (new.rowid, new.key, new.content);
        END;
        CREATE TRIGGER IF NOT EXISTS memory_facts_delete AFTER DELETE ON memory_facts
        BEGIN
            DELETE FROM memory_facts_fts WHERE rowid = old.rowid;
        END;
        CREATE TRIGGER IF NOT EXISTS memory_facts_update AFTER UPDATE ON memory_facts
        BEGIN
            DELETE FROM memory_facts_fts WHERE rowid = old.rowid;
            INSERT INTO memory_facts_fts(rowid, key, content)
            VALUES (new.rowid, new.key, new.content);
        END;
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._connection: aiosqlite.Connection | None = None
        self._checkpointer: AsyncSqliteSaver | None = None

    @property
    def checkpointer(self) -> AsyncSqliteSaver:
        if self._checkpointer is None:
            raise RuntimeError("Conversation memory is not started")
        return self._checkpointer

    async def start(self) -> None:
        if self._connection is not None:
            raise RuntimeError("Conversation memory is already started")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self._path)
        self._checkpointer = AsyncSqliteSaver(self._connection)
        try:
            await self._checkpointer.setup()
            await self._connection.executescript(self._FACTS_SCHEMA)
            await self._connection.commit()
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        connection, self._connection = self._connection, None
        self._checkpointer = None
        if connection is not None:
            await connection.close()

    async def remember(self, key: str, content: str) -> None:
        connection = self._require_connection()
        now = datetime.now(UTC).isoformat()
        await connection.execute(
            """
            INSERT INTO memory_facts(key, content, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                content = excluded.content,
                updated_at = excluded.updated_at
            """,
            (_key(key), _content(content), now, now),
        )
        await connection.commit()

    async def list(self) -> tuple[MemoryFact, ...]:
        connection = self._require_connection()
        async with connection.execute(
            "SELECT key, content FROM memory_facts ORDER BY key LIMIT 100"
        ) as cursor:
            rows = await cursor.fetchall()
        return tuple(MemoryFact(*row) for row in rows)

    async def forget(self, key: str) -> bool:
        connection = self._require_connection()
        cursor = await connection.execute(
            "DELETE FROM memory_facts WHERE key = ?", (_key(key),)
        )
        await connection.commit()
        return cursor.rowcount > 0

    async def search(self, query: str, *, limit: int = 5) -> tuple[MemoryFact, ...]:
        terms = _terms(query)
        if not terms or limit < 1:
            return ()
        match = " OR ".join(f'"{term}"*' for term in terms)
        connection = self._require_connection()
        async with connection.execute(
            """
            SELECT key, content
            FROM memory_facts_fts
            WHERE memory_facts_fts MATCH ?
            ORDER BY bm25(memory_facts_fts), key
            LIMIT ?
            """,
            (match, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return tuple(MemoryFact(*row) for row in rows)

    async def compact(self, thread_id: str) -> None:
        """Retain the latest complete checkpoint for the profile's sole thread."""
        connection = self._require_connection()
        async with connection.execute(
            """
            SELECT checkpoint_id FROM checkpoints
            WHERE thread_id = ? AND checkpoint_ns = ''
            ORDER BY checkpoint_id DESC LIMIT 1
            """,
            (thread_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return
        checkpoint_id = str(row[0])
        await connection.execute(
            """
            DELETE FROM writes
            WHERE thread_id = ? AND checkpoint_ns = '' AND checkpoint_id <> ?
            """,
            (thread_id, checkpoint_id),
        )
        await connection.execute(
            """
            DELETE FROM checkpoints
            WHERE thread_id = ? AND checkpoint_ns = '' AND checkpoint_id <> ?
            """,
            (thread_id, checkpoint_id),
        )
        await connection.commit()

    def _require_connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Conversation memory is not started")
        return self._connection


def _key(value: str) -> str:
    key = value.strip().lower()
    if not key:
        raise ValueError("Memory key must not be empty")
    return key


def _content(value: str) -> str:
    content = value.strip()
    if not content:
        raise ValueError("Memory content must not be empty")
    return content


def _terms(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(re.findall(r"[^\W_]+", value.lower(), re.UNICODE)))
