"""Tests for BaseAgent lifecycle."""
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.base import BaseAgent, AgentResult
from src.agents.config import get_agent_config
from src.db.repository import AgentOutputRepository


MOCK_PLAN_OUTPUT = """GOAL:
Build a REST API for task management

ASSUMPTIONS:
User wants Python + FastAPI

CONSTRAINTS:
Must work on Python 3.10+

TASKS:
1. Create project structure
2. Implement endpoints

ARCHITECTURE:
FastAPI with SQLite backend

FILES TO CREATE:
- src/main.py
- src/models.py

HANDOFF:
Ready for EXECUTE agent. Key deliverables: REST API with CRUD endpoints.
"""


@pytest.fixture
async def plan_agent(db_conn, tmp_path):
    # Insert a session row so FK constraints pass (session_id=1)
    await db_conn.execute(
        "INSERT INTO sessions (name, project_path, created_at) VALUES (?, ?, ?)",
        ("test", str(tmp_path), "2024-01-01"),
    )
    await db_conn.commit()
    config = get_agent_config("plan")
    return BaseAgent(config, db_conn, str(tmp_path))


async def test_run_returns_agent_result(plan_agent):
    with patch("src.agents.base.invoke_claude_with_retry", new_callable=AsyncMock) as mock:
        mock.return_value = MOCK_PLAN_OUTPUT
        result = await plan_agent.run("Build a REST API", session_id=1)

    assert isinstance(result, AgentResult)
    assert result.agent_name == "plan"
    assert "GOAL" in result.sections
    assert "REST API" in result.sections["GOAL"]


async def test_run_persists_output(plan_agent, db_conn):
    with patch("src.agents.base.invoke_claude_with_retry", new_callable=AsyncMock) as mock:
        mock.return_value = MOCK_PLAN_OUTPUT
        await plan_agent.run("Build a REST API", session_id=1)

    repo = AgentOutputRepository(db_conn)
    outputs = await repo.get_by_session(1)
    assert len(outputs) == 1
    assert outputs[0].agent_type == "plan"


async def test_handoff_extracted(plan_agent):
    with patch("src.agents.base.invoke_claude_with_retry", new_callable=AsyncMock) as mock:
        mock.return_value = MOCK_PLAN_OUTPUT
        result = await plan_agent.run("Build a REST API", session_id=1)

    assert result.handoff is not None
    assert "EXECUTE" in result.handoff


async def test_run_no_handoff_when_missing(plan_agent):
    output_no_handoff = "GOAL:\nDo something\n"
    with patch("src.agents.base.invoke_claude_with_retry", new_callable=AsyncMock) as mock:
        mock.return_value = output_no_handoff
        result = await plan_agent.run("Do something", session_id=1)

    assert result.handoff is None


async def test_prompt_includes_workspace_context(plan_agent):
    with patch("src.agents.base.invoke_claude_with_retry", new_callable=AsyncMock) as mock:
        mock.return_value = "GOAL:\ntest\n"
        await plan_agent.run("Build something", session_id=1)

    call_args = mock.call_args
    prompt = call_args[0][0]
    assert "WORKSPACE CONTEXT" in prompt
    assert "Build something" in prompt
