"""
Integration tests for HTML view routes.

Tests that the dashboard pages render correctly with Pico CSS, Alpine.js,
and proper auth enforcement.
"""
import base64
import os

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


async def test_task_list_page(client):
    """GET / with auth returns 200 HTML with Alpine.js task list component."""
    async with client:
        resp = await client.get("/", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "x-data" in resp.text
    assert "loadTasks" in resp.text


async def test_task_list_requires_auth(app_with_pool):
    """GET / without auth returns 401."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 401


async def test_task_detail_page(client):
    """GET /tasks/999/view with auth returns 200 HTML."""
    async with client:
        resp = await client.get("/tasks/999/view", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


async def test_base_template_includes(client):
    """GET / response includes Pico CSS and Alpine.js CDN links."""
    async with client:
        resp = await client.get("/", headers=AUTH_HEADERS)
    assert "picocss/pico@2" in resp.text
    assert "alpinejs@3" in resp.text


async def test_create_form_present(client):
    """GET / response contains task creation form elements."""
    async with client:
        resp = await client.get("/", headers=AUTH_HEADERS)
    assert "<textarea" in resp.text
    assert "<select" in resp.text
    assert "supervised" in resp.text
    assert "autonomous" in resp.text


async def test_task_detail_has_log_container(client):
    """GET /tasks/1/view with auth returns HTML containing log-output class."""
    async with client:
        resp = await client.get("/tasks/1/view", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert "log-output" in resp.text


async def test_task_detail_has_approval_ui(client):
    """GET /tasks/1/view with auth returns HTML containing approval UI elements."""
    async with client:
        resp = await client.get("/tasks/1/view", headers=AUTH_HEADERS)
    assert "sendApproval" in resp.text
    assert "approve" in resp.text


async def test_task_detail_has_websocket_connect(client):
    """GET /tasks/1/view with auth returns HTML containing WebSocket connection code."""
    async with client:
        resp = await client.get("/tasks/1/view", headers=AUTH_HEADERS)
    assert "WebSocket" in resp.text


async def test_task_detail_has_cancel_button(client):
    """GET /tasks/1/view with auth returns HTML containing cancel functionality."""
    async with client:
        resp = await client.get("/tasks/1/view", headers=AUTH_HEADERS)
    assert "cancelTask" in resp.text
