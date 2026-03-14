"""
Tests for the AI template generation endpoint (POST /templates/generate).

Covers:
- AIGEN-01: Happy path generation with mocked Claude CLI
- AIGEN-02: Validation of reserved names, path traversal, valid agents
- AIGEN-03: Concurrency control (429 when locked, semaphore release on error)

All tests mock call_orchestrator_claude -- no real Claude CLI calls.
"""
import asyncio
import json
import subprocess

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from src.server.routers.templates import template_router, _gen_lock
from src.server.dependencies import verify_credentials

pytestmark = pytest.mark.asyncio

# --- Test fixtures ---

MOCK_CLAUDE_RESPONSE = json.dumps({
    "structured_output": {
        "id": "fastapi-stripe",
        "name": "FastAPI with Stripe",
        "description": "A FastAPI app with Stripe billing",
        "files": {
            "CLAUDE.md.j2": "# {{ name }}\nFastAPI + Stripe project",
            ".claude/settings.local.json": '{"permissions": {}}',
            "src/main.py": "from fastapi import FastAPI\napp = FastAPI()",
            ".claude/agents/billing.md": (
                "---\nname: billing\ndescription: Handles billing logic\n---\n"
                "You are a billing agent."
            ),
        },
    }
})


@pytest.fixture
def app():
    """Create a test FastAPI app with auth overridden."""
    test_app = FastAPI()
    test_app.include_router(template_router)
    test_app.dependency_overrides[verify_credentials] = lambda: "testuser"
    return test_app


@pytest.fixture
async def client(app):
    """AsyncClient for the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- AIGEN-01: Happy path ---


async def test_generate_returns_complete_template(client):
    """Mock call_orchestrator_claude to return valid JSON; assert 200 with all fields."""
    with patch(
        "src.server.routers.templates.call_orchestrator_claude",
        new_callable=AsyncMock,
        return_value=MOCK_CLAUDE_RESPONSE,
    ):
        resp = await client.post(
            "/templates/generate",
            json={"description": "A FastAPI app with Stripe billing"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "fastapi-stripe"
    assert body["name"] == "FastAPI with Stripe"
    assert body["description"] == "A FastAPI app with Stripe billing"
    assert isinstance(body["files"], dict)
    assert len(body["files"]) == 4
    assert body["validation_errors"] == []


async def test_generate_validates_request(client):
    """POST with empty body returns 422 (description is required)."""
    resp = await client.post("/templates/generate", json={})
    assert resp.status_code == 422


# --- AIGEN-02: Validation ---


async def test_validate_catches_reserved_names(client):
    """Agent file named 'plan.md' triggers reserved name warning."""
    reserved_response = json.dumps({
        "structured_output": {
            "id": "reserved-test",
            "name": "Reserved Test",
            "description": "Test reserved name",
            "files": {
                "CLAUDE.md": "# Test",
                ".claude/agents/plan.md": (
                    "---\nname: plan\ndescription: Bad agent\n---\n"
                    "You are plan."
                ),
            },
        }
    })
    with patch(
        "src.server.routers.templates.call_orchestrator_claude",
        new_callable=AsyncMock,
        return_value=reserved_response,
    ):
        resp = await client.post(
            "/templates/generate",
            json={"description": "test reserved"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert any("reserved" in e.lower() or "plan" in e.lower() for e in body["validation_errors"])


async def test_validate_passes_valid_agents(client):
    """Valid agent file (non-reserved name, valid frontmatter) produces no errors."""
    with patch(
        "src.server.routers.templates.call_orchestrator_claude",
        new_callable=AsyncMock,
        return_value=MOCK_CLAUDE_RESPONSE,
    ):
        resp = await client.post(
            "/templates/generate",
            json={"description": "test valid agents"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["validation_errors"] == []


async def test_validate_catches_path_traversal(client):
    """File path containing '..' triggers path warning."""
    traversal_response = json.dumps({
        "structured_output": {
            "id": "traversal-test",
            "name": "Traversal Test",
            "description": "Test path traversal",
            "files": {
                "CLAUDE.md": "# Test",
                "../../etc/passwd": "bad content",
            },
        }
    })
    with patch(
        "src.server.routers.templates.call_orchestrator_claude",
        new_callable=AsyncMock,
        return_value=traversal_response,
    ):
        resp = await client.post(
            "/templates/generate",
            json={"description": "test traversal"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert any("path" in e.lower() or "invalid" in e.lower() for e in body["validation_errors"])


# --- AIGEN-03: Concurrency control ---


async def test_concurrent_generation_returns_429(client):
    """When _gen_lock is held, POST /templates/generate returns 429 with Retry-After."""
    # Manually acquire the lock before the request
    await _gen_lock.acquire()
    try:
        resp = await client.post(
            "/templates/generate",
            json={"description": "should be rejected"},
        )
        assert resp.status_code == 429
        assert "retry-after" in resp.headers
    finally:
        _gen_lock.release()


async def test_semaphore_released_on_error(app):
    """After call_orchestrator_claude raises, lock is released for next request."""
    # Use raise_server_exceptions=False so unhandled errors return 500 instead of propagating
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as error_client:
        # First request: mock raises an exception
        with patch(
            "src.server.routers.templates.call_orchestrator_claude",
            new_callable=AsyncMock,
            side_effect=subprocess.CalledProcessError(1, "claude"),
        ):
            resp1 = await error_client.post(
                "/templates/generate",
                json={"description": "will error"},
            )
        assert resp1.status_code == 500

        # Second request: should NOT get 429 (lock was released)
        with patch(
            "src.server.routers.templates.call_orchestrator_claude",
            new_callable=AsyncMock,
            return_value=MOCK_CLAUDE_RESPONSE,
        ):
            resp2 = await error_client.post(
                "/templates/generate",
                json={"description": "should work now"},
            )
        assert resp2.status_code == 200
        assert resp2.json()["id"] == "fastapi-stripe"
