import asyncio
import pytest
import aiosqlite


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
def mock_claude_proc():
    """Returns a mock subprocess with pre-baked NDJSON assistant + result lines."""
    lines = [
        b'{"type":"assistant","message":{"content":[{"type":"text","text":"hello"}]}}\n',
        b'{"type":"result","subtype":"success","result":"hello","cost_usd":0.001}\n',
    ]
    return _MockProc(lines)
