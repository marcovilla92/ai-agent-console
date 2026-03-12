"""Tests for AgentUsage dataclass and UsageRepository."""
import pytest

from src.db.schema import AgentUsage
from src.db.repository import UsageRepository


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


@pytest.mark.asyncio
async def test_usage_repository_create(db_conn):
    """UsageRepository.create persists a usage record."""
    repo = UsageRepository(db_conn)
    usage = AgentUsage(
        session_id=1,
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
    repo = UsageRepository(db_conn)
    usage1 = AgentUsage(
        session_id=42,
        agent_type="plan",
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        cost_usd=0.001,
        created_at="2026-01-01T00:00:00Z",
    )
    usage2 = AgentUsage(
        session_id=42,
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

    results = await repo.get_by_session(42)
    assert len(results) == 2
    assert results[0].agent_type == "plan"
    assert results[1].agent_type == "execute"

    # Different session returns empty
    empty = await repo.get_by_session(999)
    assert len(empty) == 0
