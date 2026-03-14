"""Tests for the Alpine.js SPA (static/index.html).

File-content tests validate the SPA HTML directly from disk.
Server integration tests verify routing through FastAPI.
"""

import base64
import os
import pathlib

import pytest
from httpx import ASGITransport, AsyncClient

from src.server.app import create_app

SPA_PATH = pathlib.Path(__file__).resolve().parent.parent / "static" / "index.html"

pytestmark = pytest.mark.asyncio

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://n8n:Amc2017!m@10.0.1.7:5432/agent_console_test",
)

AUTH_HEADERS = {
    "Authorization": "Basic " + base64.b64encode(b"admin:changeme").decode()
}


@pytest.fixture
def spa_html():
    """Read the SPA HTML file from disk."""
    return SPA_PATH.read_text()


def test_html_contains_alpine_store(spa_html):
    """HTML contains Alpine.store (proves it's the SPA, not Jinja2)."""
    assert "Alpine.store" in spa_html


def test_html_contains_project_list(spa_html):
    """HTML contains project list view with loadProjects."""
    assert "x-show=\"$store.app.view === 'select'\"" in spa_html
    assert "loadProjects" in spa_html


def test_html_contains_create_form(spa_html):
    """HTML contains create project view with template picker."""
    assert "x-show=\"$store.app.view === 'create'\"" in spa_html
    assert "template" in spa_html.lower()


def test_html_contains_prompt_view(spa_html):
    """HTML contains prompt view with phase suggestion."""
    assert "x-show=\"$store.app.view === 'prompt'\"" in spa_html
    assert "phaseSuggestion" in spa_html


def test_html_contains_ws_streaming(spa_html):
    """HTML contains WebSocket streaming with connectWS."""
    assert "WebSocket" in spa_html
    assert "connectWS" in spa_html
    assert "logText" in spa_html


def test_uses_xshow_not_xif_for_views(spa_html):
    """Views use x-show (not x-if) to preserve DOM and WS connections."""
    # Must have x-show for all 4 views
    assert "x-show=\"$store.app.view === 'select'\"" in spa_html
    assert "x-show=\"$store.app.view === 'create'\"" in spa_html
    assert "x-show=\"$store.app.view === 'prompt'\"" in spa_html
    assert "x-show=\"$store.app.view === 'running'\"" in spa_html
    # Must NOT use x-if for view switching (would destroy DOM/WS)
    assert "x-if=\"$store.app.view" not in spa_html


def test_html_includes_cdn_libs(spa_html):
    """HTML includes Pico CSS and Alpine.js CDN links."""
    assert "picocss/pico@2" in spa_html or "pico@2" in spa_html
    assert "alpinejs@3" in spa_html


def test_html_has_all_api_endpoints(spa_html):
    """HTML contains fetch calls to all required API endpoints with credentials."""
    # Check API endpoint patterns
    assert "fetch('/projects'" in spa_html or 'fetch("/projects"' in spa_html or "fetch(`/projects`" in spa_html
    assert "fetch('/templates'" in spa_html or 'fetch("/templates"' in spa_html or "fetch(`/templates`" in spa_html
    assert "fetch('/tasks'" in spa_html or 'fetch("/tasks"' in spa_html or "fetch(`/tasks`" in spa_html
    # All fetches must use credentials
    assert "credentials: 'same-origin'" in spa_html


# --- Server integration tests ---


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


async def test_root_returns_spa_html(client):
    """GET / with auth returns 200, text/html, body contains Alpine.store."""
    async with client:
        resp = await client.get("/", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Alpine.store" in resp.text


async def test_old_view_routes_removed(client):
    """GET /tasks/1/view with auth returns 404 (old Jinja2 routes gone)."""
    async with client:
        resp = await client.get("/tasks/1/view", headers=AUTH_HEADERS)
    assert resp.status_code == 404


async def test_root_requires_auth(app_with_pool):
    """GET / without auth returns 401."""
    transport = ASGITransport(app=app_with_pool)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 401
