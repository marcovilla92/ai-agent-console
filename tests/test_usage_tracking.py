"""Tests for AgentUsage dataclass and UsageRepository."""
import asyncio
import json
from unittest.mock import patch

import pytest

from src.db.schema import AgentUsage, Session
from src.db.repository import UsageRepository, SessionRepository


def test_agent_usage_dataclass():
    """AgentUsage stores all required fields."""
    usage = AgentUsage(
        session_id=1,
        agent_type="plan",
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=10,
        cache_creation_tokens=5,
        cost_usd=0.002,
        created_at="2026-01-01T00:00:00Z",
    )
    assert usage.agent_type == "plan"
    assert usage.input_tokens == 100
    assert usage.output_tokens == 50
    assert usage.cache_read_tokens == 10
    assert usage.cache_creation_tokens == 5
    assert usage.cost_usd == 0.002
    assert usage.id is None


async def _create_session(db_conn, session_id=1):
    """Helper to create a session for FK constraints."""
    repo = SessionRepository(db_conn)
    sid = await repo.create(Session(
        name=f"test-session-{session_id}",
        project_path="/tmp/test",
        created_at="2026-01-01T00:00:00Z",
    ))
    return sid


@pytest.mark.asyncio
async def test_usage_repository_create(db_conn):
    """UsageRepository.create persists a usage record."""
    sid = await _create_session(db_conn)
    repo = UsageRepository(db_conn)
    usage = AgentUsage(
        session_id=sid,
        agent_type="execute",
        input_tokens=200,
        output_tokens=100,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        cost_usd=0.005,
        created_at="2026-01-01T00:00:00Z",
    )
    row_id = await repo.create(usage)
    assert row_id is not None
    assert row_id > 0


@pytest.mark.asyncio
async def test_usage_repository_get_by_session(db_conn):
    """UsageRepository.get_by_session retrieves records for a session."""
    sid = await _create_session(db_conn)
    repo = UsageRepository(db_conn)
    usage1 = AgentUsage(
        session_id=sid,
        agent_type="plan",
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        cost_usd=0.001,
        created_at="2026-01-01T00:00:00Z",
    )
    usage2 = AgentUsage(
        session_id=sid,
        agent_type="execute",
        input_tokens=200,
        output_tokens=100,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        cost_usd=0.003,
        created_at="2026-01-01T00:01:00Z",
    )
    await repo.create(usage1)
    await repo.create(usage2)

    results = await repo.get_by_session(sid)
    assert len(results) == 2
    assert results[0].agent_type == "plan"
    assert results[1].agent_type == "execute"

    # Different session returns empty
    empty = await repo.get_by_session(999)
    assert len(empty) == 0


# --- Task 2: stream_claude result event + StatusBar usage ---


class _MockStdout:
    def __init__(self, lines):
        self._lines = iter(lines)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._lines)
        except StopIteration:
            raise StopAsyncIteration


class _FakeStderr:
    async def read(self):
        return b""


class _MockProc:
    def __init__(self, lines, returncode=0):
        self.stdout = _MockStdout(lines)
        self.stderr = _FakeStderr()
        self.returncode = returncode

    async def wait(self):
        return self.returncode


@pytest.mark.asyncio
async def test_stream_claude_yields_result_dict(monkeypatch):
    """stream_claude yields a dict with type 'result' and cost_usd for result events."""
    import src.runner.runner as runner_mod

    lines = [
        b'{"type":"content_block_delta","delta":{"type":"text_delta","text":"hello"}}\n',
        b'{"type":"result","subtype":"success","result":"hello","cost_usd":0.005,"usage":{"input_tokens":100,"output_tokens":50}}\n',
    ]
    mock_proc = _MockProc(lines)

    async def fake_exec(*args, **kwargs):
        return mock_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(runner_mod, "_CLAUDE_BIN", "claude")

    results = []
    async for chunk in runner_mod.stream_claude("test"):
        results.append(chunk)

    # Should have text chunk + result dict
    assert results[0] == "hello"
    assert isinstance(results[1], dict)
    assert results[1]["type"] == "result"
    assert results[1]["cost_usd"] == 0.005
    assert results[1]["input_tokens"] == 100
    assert results[1]["output_tokens"] == 50


@pytest.mark.asyncio
async def test_stream_claude_text_only_without_result(monkeypatch):
    """stream_claude still yields only text strings for content_block_delta events."""
    import src.runner.runner as runner_mod

    lines = [
        b'{"type":"content_block_delta","delta":{"type":"text_delta","text":"world"}}\n',
    ]
    mock_proc = _MockProc(lines)

    async def fake_exec(*args, **kwargs):
        return mock_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(runner_mod, "_CLAUDE_BIN", "claude")

    results = []
    async for chunk in runner_mod.stream_claude("test"):
        results.append(chunk)

    assert len(results) == 1
    assert results[0] == "world"
    assert isinstance(results[0], str)


def test_status_bar_set_usage():
    """StatusBar.set_usage updates display_text to include token counts and cost."""
    from src.tui.status_bar import StatusBar

    bar = StatusBar()
    bar._refresh_text()  # Initialize
    bar.set_usage(input_tokens=100, output_tokens=50, cost_usd=0.005)
    text = bar.display_text
    assert "100" in text
    assert "50" in text
    assert "0.005" in text or "$0.01" in text or "0.00" in text


def test_status_bar_set_usage_zero_cost():
    """StatusBar.set_usage with cost_usd=0 shows graceful display."""
    from src.tui.status_bar import StatusBar

    bar = StatusBar()
    bar._refresh_text()
    bar.set_usage(input_tokens=0, output_tokens=0, cost_usd=0.0)
    text = bar.display_text
    # Should not crash, should show something graceful
    assert isinstance(text, str)
