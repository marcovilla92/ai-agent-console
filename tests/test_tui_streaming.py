"""Tests for streaming worker and real-time panel updates."""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.tui.app import AgentConsoleApp
from src.tui.panels import OutputPanel
from src.tui.streaming import stream_agent_to_panel


async def _mock_stream_chunks(*chunks):
    """Create an async generator that yields chunks."""
    for chunk in chunks:
        yield chunk


async def test_stream_agent_writes_to_panel():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        panel = app.plan_panel

        async def fake_stream(prompt, **kwargs):
            for chunk in ["Hello ", "World"]:
                yield chunk

        with patch("src.tui.streaming.stream_claude", side_effect=fake_stream):
            sections = await stream_agent_to_panel(
                app, "plan", "test prompt", panel,
            )

        # Panel should have received the chunks
        assert len(panel.lines) > 0


async def test_stream_agent_returns_sections():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        panel = app.plan_panel

        async def fake_stream(prompt, **kwargs):
            yield "GOAL:\nBuild an API\n\nTASKS:\n1. Do it\n"

        with patch("src.tui.streaming.stream_claude", side_effect=fake_stream):
            sections = await stream_agent_to_panel(
                app, "plan", "test", panel,
            )

        assert "GOAL" in sections
        assert "TASKS" in sections


async def test_stream_agent_persists_to_db(db_conn):
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        panel = app.plan_panel

        # Create a session first
        await db_conn.execute(
            "INSERT INTO sessions (name, project_path, created_at) VALUES (?, ?, ?)",
            ("test", ".", "2024-01-01"),
        )
        await db_conn.commit()

        async def fake_stream(prompt, **kwargs):
            yield "GOAL:\nTest output\n"

        with patch("src.tui.streaming.stream_claude", side_effect=fake_stream):
            await stream_agent_to_panel(
                app, "plan", "test", panel, db=db_conn, session_id=1,
            )

        from src.db.repository import AgentOutputRepository
        repo = AgentOutputRepository(db_conn)
        outputs = await repo.get_by_session(1)
        assert len(outputs) == 1
        assert outputs[0].agent_type == "plan"


async def test_stream_agent_without_db():
    """Streaming works fine even without a DB connection."""
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        panel = app.execute_panel

        async def fake_stream(prompt, **kwargs):
            yield "TARGET:\nSome target\n"

        with patch("src.tui.streaming.stream_claude", side_effect=fake_stream):
            sections = await stream_agent_to_panel(
                app, "execute", "test", panel, db=None, session_id=None,
            )

        assert "TARGET" in sections


async def test_stream_includes_workspace_context():
    """Prompt sent to Claude includes workspace context."""
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        panel = app.plan_panel
        captured_prompt = None

        async def fake_stream(prompt, **kwargs):
            nonlocal captured_prompt
            captured_prompt = prompt
            yield "GOAL:\ntest\n"

        with patch("src.tui.streaming.stream_claude", side_effect=fake_stream):
            await stream_agent_to_panel(app, "plan", "Build it", panel)

        assert "WORKSPACE CONTEXT" in captured_prompt
        assert "Build it" in captured_prompt
