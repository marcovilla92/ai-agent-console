"""
Integration tests for task REST endpoints with HTTP Basic Auth.

Tests auth dependency, TaskManager lifespan wiring, and task CRUD endpoints.
Requires a running PostgreSQL instance (TEST_DATABASE_URL env var or default).
"""
import base64
import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.server.app import create_app

pytestmark = pytest.mark.asyncio

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://n8n:Amc2017!m@10.0.1.7:5432/agent_console_test",
)

AUTH_HEADERS = {
    "Authorization": "Basic " + base64.b64encode(b"admin:changeme").decode()
}
BAD_AUTH_HEADERS = {
    "Authorization": "Basic " + base64.b64encode(b"admin:wrong").decode()
}


@pytest.fixture
async def app_with_pool():
    """Create a FastAPI app and manually run its lifespan for testing."""
    os.environ["APP_DATABASE_URL"] = TEST_DSN
    os.environ["APP_POOL_MIN_SIZE"] = "1"
    os.environ["APP_POOL_MAX_SIZE"] = "2"
    from src.server.config import get_settings
    get_settings.cache_clear()

    app = create_app()
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
def client(app_with_pool):
    """Return an HTTPX async client bound to the test app."""
    transport = ASGITransport(app=app_with_pool)
    return AsyncClient(transport=transport, base_url="http://test")


# --- Task 1 tests: Auth dependency and lifespan wiring ---


async def test_settings_has_auth_fields():
    """Settings has auth_username and auth_password fields with defaults."""
    os.environ.pop("APP_AUTH_USERNAME", None)
    os.environ.pop("APP_AUTH_PASSWORD", None)
    from src.server.config import get_settings
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.auth_username == "admin"
    assert settings.auth_password == "changeme"
    get_settings.cache_clear()


async def test_verify_credentials_rejects_invalid(app_with_pool):
    """verify_credentials raises 401 with invalid credentials."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/tasks", headers=BAD_AUTH_HEADERS)
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Basic"


async def test_verify_credentials_returns_username(app_with_pool):
    """verify_credentials returns username with valid credentials."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/tasks", headers=AUTH_HEADERS)
    # Should not be 401 - valid credentials accepted
    assert resp.status_code != 401


async def test_health_no_auth(app_with_pool):
    """GET /health works without auth (no 401)."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_task_manager_in_lifespan(app_with_pool):
    """app.state.task_manager exists after lifespan startup."""
    from src.engine.manager import TaskManager
    assert hasattr(app_with_pool.state, "task_manager")
    assert isinstance(app_with_pool.state.task_manager, TaskManager)
