import asyncio
import os

import pytest
import aiosqlite
import asyncpg

from src.db.migrations import apply_schema


@pytest.fixture
async def db_conn():
    """In-memory aiosqlite connection with schema applied."""
    db = await aiosqlite.connect(":memory:")
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            project_path TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS agent_outputs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES sessions(id),
            agent_type TEXT NOT NULL,
            raw_output TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS agent_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES sessions(id),
            agent_type TEXT NOT NULL,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cache_read_tokens INTEGER NOT NULL DEFAULT 0,
            cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd REAL NOT NULL DEFAULT 0.0,
            created_at TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS orchestrator_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES sessions(id),
            next_agent TEXT NOT NULL,
            reasoning TEXT NOT NULL,
            confidence REAL,
            full_response TEXT NOT NULL,
            iteration_count INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    await db.commit()
    yield db
    await db.close()


class _MockStdout:
    def __init__(self, lines: list[bytes]):
        self._lines = iter(lines)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._lines)
        except StopIteration:
            raise StopAsyncIteration


class _MockProc:
    def __init__(self, lines: list[bytes], returncode: int = 0):
        self.stdout = _MockStdout(lines)
        self.returncode = returncode

    async def wait(self):
        return self.returncode


@pytest.fixture
async def pg_pool():
    """asyncpg connection pool with schema applied, cleaned up after test."""
    dsn = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://n8n:Amc2017!m@10.0.1.7:5432/agent_console_test",
    )
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
    await apply_schema(pool)
    yield pool
    # Clean up in reverse FK order
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM orchestrator_decisions")
        await conn.execute("DELETE FROM agent_usage")
        await conn.execute("DELETE FROM agent_outputs")
        await conn.execute("DELETE FROM tasks")
    await pool.close()


@pytest.fixture
def mock_claude_proc():
    """Returns a mock subprocess with pre-baked NDJSON assistant + result lines."""
    lines = [
        b'{"type":"assistant","message":{"content":[{"type":"text","text":"hello"}]}}\n',
        b'{"type":"result","subtype":"success","result":"hello","cost_usd":0.001}\n',
    ]
    return _MockProc(lines)
