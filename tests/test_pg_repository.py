"""
Integration tests for PostgreSQL repository classes.

Requires a running PostgreSQL instance (TEST_DATABASE_URL env var or default).
"""
from datetime import datetime, timezone

import pytest

from src.db.pg_schema import Task, AgentOutput, AgentUsage, OrchestratorDecisionRecord
from src.db.pg_repository import (
    TaskRepository,
    AgentOutputRepository,
    UsageRepository,
    OrchestratorDecisionRepository,
)

pytestmark = pytest.mark.asyncio


async def test_schema_creates_tables(pg_pool):
    """apply_schema creates all 4 tables (tasks, agent_outputs, agent_usage, orchestrator_decisions)."""
    async with pg_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
            "ORDER BY table_name"
        )
    table_names = {row["table_name"] for row in rows}
    assert "tasks" in table_names
    assert "agent_outputs" in table_names
    assert "agent_usage" in table_names
    assert "orchestrator_decisions" in table_names


async def test_task_crud(pg_pool):
    """TaskRepository.create returns int id, .get returns Task, .list_all returns list."""
    repo = TaskRepository(pg_pool)
    now = datetime.now(timezone.utc)

    task = Task(name="test-task", project_path="/tmp/project", created_at=now)
    task_id = await repo.create(task)
    assert isinstance(task_id, int)
    assert task_id > 0

    fetched = await repo.get(task_id)
    assert fetched is not None
    assert fetched.id == task_id
    assert fetched.name == "test-task"
    assert fetched.project_path == "/tmp/project"
    assert isinstance(fetched.created_at, datetime)

    all_tasks = await repo.list_all()
    assert len(all_tasks) >= 1
    assert any(t.id == task_id for t in all_tasks)

    # get non-existent returns None
    missing = await repo.get(99999)
    assert missing is None


async def test_agent_output_persistence(pg_pool):
    """AgentOutputRepository.create persists, .get_by_session returns linked outputs."""
    task_repo = TaskRepository(pg_pool)
    output_repo = AgentOutputRepository(pg_pool)
    now = datetime.now(timezone.utc)

    task_id = await task_repo.create(
        Task(name="output-test", project_path="/tmp", created_at=now)
    )

    output = AgentOutput(
        session_id=task_id,
        agent_type="plan",
        raw_output="## Plan\nDo the thing.",
        created_at=now,
    )
    output_id = await output_repo.create(output)
    assert isinstance(output_id, int)

    outputs = await output_repo.get_by_session(task_id)
    assert len(outputs) == 1
    assert outputs[0].id == output_id
    assert outputs[0].session_id == task_id
    assert outputs[0].agent_type == "plan"
    assert outputs[0].raw_output == "## Plan\nDo the thing."

    # No outputs for different session
    empty = await output_repo.get_by_session(99999)
    assert empty == []


async def test_usage_persistence(pg_pool):
    """UsageRepository.create persists, .get_by_session returns linked usage records."""
    task_repo = TaskRepository(pg_pool)
    usage_repo = UsageRepository(pg_pool)
    now = datetime.now(timezone.utc)

    task_id = await task_repo.create(
        Task(name="usage-test", project_path="/tmp", created_at=now)
    )

    usage = AgentUsage(
        session_id=task_id,
        agent_type="execute",
        input_tokens=1000,
        output_tokens=500,
        cache_read_tokens=200,
        cache_creation_tokens=100,
        cost_usd=0.0035,
        created_at=now,
    )
    usage_id = await usage_repo.create(usage)
    assert isinstance(usage_id, int)

    records = await usage_repo.get_by_session(task_id)
    assert len(records) == 1
    assert records[0].id == usage_id
    assert records[0].input_tokens == 1000
    assert records[0].output_tokens == 500
    assert records[0].cost_usd == pytest.approx(0.0035)


async def test_decision_persistence(pg_pool):
    """OrchestratorDecisionRepository.create persists, .get_by_session returns linked decisions."""
    task_repo = TaskRepository(pg_pool)
    decision_repo = OrchestratorDecisionRepository(pg_pool)
    now = datetime.now(timezone.utc)

    task_id = await task_repo.create(
        Task(name="decision-test", project_path="/tmp", created_at=now)
    )

    decision = OrchestratorDecisionRecord(
        session_id=task_id,
        next_agent="review",
        reasoning="Code looks complete, needs review.",
        confidence=0.85,
        full_response='{"next_agent": "review", "reasoning": "..."}',
        iteration_count=2,
        created_at=now,
    )
    decision_id = await decision_repo.create(decision)
    assert isinstance(decision_id, int)

    decisions = await decision_repo.get_by_session(task_id)
    assert len(decisions) == 1
    assert decisions[0].id == decision_id
    assert decisions[0].next_agent == "review"
    assert decisions[0].confidence == pytest.approx(0.85)
    assert decisions[0].iteration_count == 2
