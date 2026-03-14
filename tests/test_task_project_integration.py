"""
Integration tests for task-project integration (Phase 16).

Tests that POST /tasks accepts optional project_id, enriches prompts with
project context, updates last_used_at, and returns project_id in responses.
"""
import asyncio
import base64
import os
from datetime import datetime, timezone
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
async def project_id(app_with_pool):
    """Insert a test project and return its id. Clean up after test."""
    pool = app_with_pool.state.pool
    pid = await pool.fetchval(
        "INSERT INTO projects (name, slug, path, description, created_at) "
        "VALUES ($1, $2, $3, $4, $5) RETURNING id",
        "Test Project", "test-project", "/tmp/test-project",
        "A test project", datetime.now(timezone.utc),
    )
    yield pid
    await pool.execute("DELETE FROM tasks WHERE project_id = $1", pid)
    await pool.execute("DELETE FROM projects WHERE id = $1", pid)


# --- Test: backward compatibility (no project_id) ---

@patch("src.engine.manager.orchestrate_pipeline", new_callable=AsyncMock)
async def test_create_task_without_project_id(mock_pipeline, app_with_pool):
    """POST /tasks without project_id creates task with project_id=null."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/tasks",
            json={"prompt": "no project task"},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["project_id"] is None
    assert body["prompt"] == "no project task"


# --- Test: valid project_id links task ---

@patch("src.engine.manager.orchestrate_pipeline", new_callable=AsyncMock)
async def test_create_task_with_valid_project_id(mock_pipeline, app_with_pool, project_id):
    """POST /tasks with valid project_id creates task linked to project."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/tasks",
            json={"prompt": "linked task", "project_id": project_id},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["project_id"] == project_id
    assert body["prompt"] == "linked task"


# --- Test: invalid project_id returns 404 ---

@patch("src.engine.manager.orchestrate_pipeline", new_callable=AsyncMock)
async def test_create_task_invalid_project_id(mock_pipeline, app_with_pool):
    """POST /tasks with invalid project_id returns 404."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/tasks",
            json={"prompt": "bad project", "project_id": 999999},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 404
    assert "Project not found" in resp.json()["detail"]


# --- Test: context prepended to prompt ---

@patch("src.engine.manager.orchestrate_pipeline", new_callable=AsyncMock)
@patch("src.server.routers.tasks.assemble_full_context", new_callable=AsyncMock)
async def test_create_task_prepends_context(mock_assemble, mock_pipeline, app_with_pool, project_id):
    """POST /tasks with project_id prepends assembled context to pipeline prompt."""
    mock_assemble.return_value = {
        "workspace": "=== WORKSPACE ===\nfiles here\n",
        "claude_md": "# Project Instructions\nDo stuff",
        "planning_docs": {"STATE.md": "Phase 1"},
        "git_log": "abc123 initial commit",
        "recent_tasks": [],
    }

    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/tasks",
            json={"prompt": "do something", "project_id": project_id},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 201

    # The original prompt should be stored in DB (not enriched)
    body = resp.json()
    assert body["prompt"] == "do something"

    # Wait for pipeline to be called
    await asyncio.sleep(0.2)

    # The pipeline should have received the enriched prompt
    mock_pipeline.assert_called_once()
    call_args = mock_pipeline.call_args
    # orchestrate_pipeline(ctx, prompt, pool, task_id)
    pipeline_prompt = call_args[0][1]
    assert "=== WORKSPACE ===" in pipeline_prompt
    assert "# Project Instructions" in pipeline_prompt
    assert "do something" in pipeline_prompt


# --- Test: last_used_at updated ---

@patch("src.engine.manager.orchestrate_pipeline", new_callable=AsyncMock)
async def test_create_task_updates_last_used_at(mock_pipeline, app_with_pool, project_id):
    """POST /tasks with project_id updates project's last_used_at."""
    pool = app_with_pool.state.pool

    # Verify last_used_at is null before
    before = await pool.fetchval(
        "SELECT last_used_at FROM projects WHERE id = $1", project_id
    )
    assert before is None

    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/tasks",
            json={"prompt": "update timestamp", "project_id": project_id},
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 201

    # Verify last_used_at is now set
    after = await pool.fetchval(
        "SELECT last_used_at FROM projects WHERE id = $1", project_id
    )
    assert after is not None


# --- Test: context assembly failure graceful fallback ---

@patch("src.engine.manager.orchestrate_pipeline", new_callable=AsyncMock)
@patch("src.server.routers.tasks.assemble_full_context", new_callable=AsyncMock)
async def test_context_failure_falls_back(mock_assemble, mock_pipeline, app_with_pool, project_id):
    """Context assembly failure does not block task creation."""
    mock_assemble.side_effect = RuntimeError("context assembly exploded")

    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/tasks",
            json={"prompt": "fallback test", "project_id": project_id},
            headers=AUTH_HEADERS,
        )
    # Task should still be created
    assert resp.status_code == 201
    body = resp.json()
    assert body["prompt"] == "fallback test"
    assert body["project_id"] == project_id

    # Wait for pipeline call
    await asyncio.sleep(0.2)

    # Pipeline should have been called with original prompt (no context prefix)
    mock_pipeline.assert_called_once()
    pipeline_prompt = mock_pipeline.call_args[0][1]
    assert pipeline_prompt == "fallback test"
