"""
Integration tests for task REST endpoints with HTTP Basic Auth.

Tests auth dependency, TaskManager lifespan wiring, and task CRUD endpoints.
Requires a running PostgreSQL instance (TEST_DATABASE_URL env var or default).
"""
import asyncio
import base64
import os
from unittest.mock import AsyncMock, MagicMock, patch

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


# --- Task 2 tests: REST endpoints for task CRUD and cancel ---


async def _slow_pipeline(ctx, prompt, pool, task_id):
    """Mock pipeline that sleeps to simulate a long-running task."""
    await asyncio.sleep(60)


@patch("src.engine.manager.orchestrate_pipeline", new_callable=AsyncMock)
async def test_post_tasks_no_auth(mock_pipeline, app_with_pool):
    """POST /tasks without auth returns 401."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/tasks", json={"prompt": "hello"})
    assert resp.status_code == 401


@patch("src.engine.manager.orchestrate_pipeline", new_callable=AsyncMock)
async def test_post_tasks_creates_task(mock_pipeline, app_with_pool):
    """POST /tasks with auth creates task, returns 201 with TaskResponse."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/tasks",
            json={"prompt": "build a website"},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["prompt"] == "build a website"
    assert body["mode"] == "autonomous"
    assert body["id"] is not None
    assert body["status"] in ("queued", "running")


@patch("src.engine.manager.orchestrate_pipeline", new_callable=AsyncMock)
async def test_get_tasks_list(mock_pipeline, app_with_pool):
    """GET /tasks with auth returns list of tasks with count."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a task first
        await client.post(
            "/tasks",
            json={"prompt": "list test task"},
            headers=AUTH_HEADERS,
        )
        resp = await client.get("/tasks", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert "tasks" in body
    assert "count" in body
    assert body["count"] >= 1
    assert isinstance(body["tasks"], list)


@patch("src.engine.manager.orchestrate_pipeline", new_callable=AsyncMock)
async def test_get_task_by_id(mock_pipeline, app_with_pool):
    """GET /tasks/{id} with auth returns single task."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/tasks",
            json={"prompt": "get by id test"},
            headers=AUTH_HEADERS,
        )
        task_id = create_resp.json()["id"]
        resp = await client.get(f"/tasks/{task_id}", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == task_id
    assert body["prompt"] == "get by id test"


@patch("src.engine.manager.orchestrate_pipeline", new_callable=AsyncMock)
async def test_get_task_not_found(mock_pipeline, app_with_pool):
    """GET /tasks/{id} with invalid id returns 404."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/tasks/999999", headers=AUTH_HEADERS)
    assert resp.status_code == 404


@patch("src.engine.manager.orchestrate_pipeline", side_effect=_slow_pipeline)
async def test_cancel_running_task(mock_pipeline, app_with_pool):
    """POST /tasks/{id}/cancel with auth cancels a running task."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/tasks",
            json={"prompt": "cancel test"},
            headers=AUTH_HEADERS,
        )
        task_id = create_resp.json()["id"]
        # Give the task a moment to start running
        await asyncio.sleep(0.1)
        resp = await client.post(f"/tasks/{task_id}/cancel", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == task_id
    assert body["status"] == "cancelled"


@patch("src.engine.manager.orchestrate_pipeline", new_callable=AsyncMock)
async def test_cancel_not_found(mock_pipeline, app_with_pool):
    """POST /tasks/{id}/cancel with invalid id returns 404."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/tasks/999999/cancel", headers=AUTH_HEADERS)
    assert resp.status_code == 404


@patch("src.engine.manager.orchestrate_pipeline", new_callable=AsyncMock)
async def test_post_tasks_supervised_mode(mock_pipeline, app_with_pool):
    """POST /tasks with mode='supervised' stores mode correctly."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/tasks",
            json={"prompt": "supervised task", "mode": "supervised"},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["mode"] == "supervised"


# --- Phase 9: Approval endpoint tests ---


async def _supervised_reroute_pipeline(ctx, prompt, pool, task_id):
    """Mock pipeline that triggers a confirm_reroute in supervised mode."""
    await ctx.confirm_reroute("editor", "needs editing")


@patch("src.engine.manager.orchestrate_pipeline", side_effect=_supervised_reroute_pipeline)
async def test_approve_resumes_task(mock_pipeline, app_with_pool):
    """POST /tasks/{id}/approve with approve decision returns 200 and resumes task."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a supervised task that will pause at reroute
        create_resp = await client.post(
            "/tasks",
            json={"prompt": "approve test", "mode": "supervised"},
            headers=AUTH_HEADERS,
        )
        task_id = create_resp.json()["id"]

        # Wait for the task to reach awaiting_approval
        await asyncio.sleep(0.3)

        resp = await client.post(
            f"/tasks/{task_id}/approve",
            json={"decision": "approve"},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["decision"] == "approve"


async def _supervised_reroute_reject(ctx, prompt, pool, task_id):
    """Mock pipeline that triggers a confirm_reroute; rejection causes it to finish."""
    approved = await ctx.confirm_reroute("editor", "needs editing")
    if not approved:
        return  # Pipeline ends early


@patch("src.engine.manager.orchestrate_pipeline", side_effect=_supervised_reroute_reject)
async def test_reject_stops_task(mock_pipeline, app_with_pool):
    """POST /tasks/{id}/approve with reject decision returns 200 and task completes."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/tasks",
            json={"prompt": "reject test", "mode": "supervised"},
            headers=AUTH_HEADERS,
        )
        task_id = create_resp.json()["id"]

        await asyncio.sleep(0.3)

        resp = await client.post(
            f"/tasks/{task_id}/approve",
            json={"decision": "reject"},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "reject"

    # Give time for task to complete
    await asyncio.sleep(0.3)

    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        task_resp = await client.get(f"/tasks/{task_id}", headers=AUTH_HEADERS)
    assert task_resp.json()["status"] == "completed"


@patch("src.engine.manager.orchestrate_pipeline", new_callable=AsyncMock)
async def test_approve_not_awaiting(mock_pipeline, app_with_pool):
    """POST /tasks/{id}/approve for a task not awaiting approval returns 409."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/tasks",
            json={"prompt": "not awaiting test"},
            headers=AUTH_HEADERS,
        )
        task_id = create_resp.json()["id"]

        await asyncio.sleep(0.2)

        resp = await client.post(
            f"/tasks/{task_id}/approve",
            json={"decision": "approve"},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 409


@patch("src.engine.manager.orchestrate_pipeline", new_callable=AsyncMock)
async def test_approve_nonexistent(mock_pipeline, app_with_pool):
    """POST /tasks/99999/approve returns 404."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/tasks/99999/approve",
            json={"decision": "approve"},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 404


async def test_approve_requires_auth(app_with_pool):
    """POST /tasks/{id}/approve without auth returns 401."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/tasks/1/approve",
            json={"decision": "approve"},
        )
    assert resp.status_code == 401


@patch("src.engine.manager.orchestrate_pipeline", new_callable=AsyncMock)
async def test_approve_invalid_decision(mock_pipeline, app_with_pool):
    """POST /tasks/{id}/approve with invalid decision returns 422."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/tasks/1/approve",
            json={"decision": "invalid_value"},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 422


# --- Task outputs endpoint tests (moved from test_views.py) ---


async def test_get_task_outputs_empty(client):
    """GET /tasks/999/outputs with auth returns 200 with empty outputs list."""
    async with client:
        resp = await client.get("/tasks/999/outputs", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["outputs"] == []
    assert data["count"] == 0


async def test_get_task_outputs_requires_auth(app_with_pool):
    """GET /tasks/1/outputs without auth returns 401."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/tasks/1/outputs")
    assert resp.status_code == 401
