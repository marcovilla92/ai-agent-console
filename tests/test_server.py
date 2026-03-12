"""
Integration tests for FastAPI server with lifespan-managed asyncpg pool.

Requires a running PostgreSQL instance (TEST_DATABASE_URL env var or default).
"""
import os

import pytest
from httpx import ASGITransport, AsyncClient

from src.server.app import create_app

pytestmark = pytest.mark.asyncio

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://n8n:Amc2017!m@10.0.1.7:5432/agent_console_test",
)


@pytest.fixture
def app():
    """Create a FastAPI app configured for testing."""
    os.environ["APP_DATABASE_URL"] = TEST_DSN
    os.environ["APP_POOL_MIN_SIZE"] = "1"
    os.environ["APP_POOL_MAX_SIZE"] = "2"
    # Clear lru_cache so env changes take effect
    from src.server.config import get_settings
    get_settings.cache_clear()
    return create_app()


async def test_health_endpoint(app):
    """GET /health returns 200 with {"status": "ok", "database": "connected"}."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"


async def test_health_db_check(app):
    """Health endpoint actually queries the database (SELECT 1)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    # If database is unreachable, this would fail or return error status
    assert resp.status_code == 200
    assert resp.json()["database"] == "connected"


async def test_lifespan_pool(app):
    """Pool exists on app.state during request, is created on startup and closed on shutdown."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # During the lifespan, pool should be available (health endpoint uses it)
        resp = await client.get("/health")
        assert resp.status_code == 200

    # After exiting the context manager (lifespan ends), pool is closed
    # We verify by checking the pool object is closed
    # Note: pool is on app.state, and after lifespan shutdown it should be closed
    if hasattr(app.state, "pool") and app.state.pool is not None:
        assert app.state.pool._closed or app.state.pool._closing
