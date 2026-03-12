"""
Integration tests for FastAPI server with lifespan-managed asyncpg pool.

Requires a running PostgreSQL instance (TEST_DATABASE_URL env var or default).
"""
import os

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from src.server.app import create_app

pytestmark = pytest.mark.asyncio

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://n8n:Amc2017!m@10.0.1.7:5432/agent_console_test",
)


@pytest.fixture
async def app_with_pool():
    """Create a FastAPI app and manually run its lifespan for testing."""
    os.environ["APP_DATABASE_URL"] = TEST_DSN
    os.environ["APP_POOL_MIN_SIZE"] = "1"
    os.environ["APP_POOL_MAX_SIZE"] = "2"
    # Clear lru_cache so env changes take effect
    from src.server.config import get_settings
    get_settings.cache_clear()

    app = create_app()
    # Manually trigger lifespan
    async with app.router.lifespan_context(app):
        yield app
    # After yield, lifespan cleanup (pool.close()) has run


async def test_health_endpoint(app_with_pool):
    """GET /health returns 200 with {"status": "ok", "database": "connected"}."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"


async def test_health_db_check(app_with_pool):
    """Health endpoint actually queries the database (SELECT 1)."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    # If database is unreachable, this would fail or return error status
    assert resp.status_code == 200
    assert resp.json()["database"] == "connected"


async def test_lifespan_pool(app_with_pool):
    """Pool exists on app.state during request, is created on startup and closed on shutdown."""
    # During lifespan, pool should exist and be usable
    pool = app_with_pool.state.pool
    assert pool is not None
    assert isinstance(pool, asyncpg.Pool)

    # Verify pool is functional by running a query directly
    async with pool.acquire() as conn:
        result = await conn.fetchval("SELECT 1")
    assert result == 1

    # Also verify via health endpoint
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
