"""
Integration tests for the template router (GET endpoints) and template filesystem.

Tests: filesystem structure, registry.yaml, GET /templates, GET /templates/{id}, auth.
"""
import base64
import os
from pathlib import Path

import pytest
import yaml
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
    transport = ASGITransport(app=app_with_pool)
    return AsyncClient(transport=transport, base_url="http://test")


# --- Filesystem tests ---


def test_builtin_template_dirs_exist():
    """All 4 template directories exist under templates/."""
    from src.server.routers.templates import TEMPLATES_ROOT

    for name in ("blank", "fastapi-pg", "telegram-bot", "cli-tool"):
        assert (TEMPLATES_ROOT / name).is_dir(), f"Missing template dir: {name}"


def test_builtin_template_has_claude_md():
    """Each builtin template has a CLAUDE.md.j2 file."""
    from src.server.routers.templates import TEMPLATES_ROOT

    for name in ("blank", "fastapi-pg", "telegram-bot", "cli-tool"):
        assert (TEMPLATES_ROOT / name / "CLAUDE.md.j2").is_file(), (
            f"Missing CLAUDE.md.j2 in {name}"
        )


def test_fastapi_pg_has_full_structure():
    """fastapi-pg has agents, commands, src, Dockerfile, etc."""
    from src.server.routers.templates import TEMPLATES_ROOT

    base = TEMPLATES_ROOT / "fastapi-pg"
    expected = [
        ".claude/agents/db-migrator.md",
        ".claude/agents/api-tester.md",
        ".claude/commands/migrate.md",
        ".claude/commands/seed.md",
        ".claude/commands/test-api.md",
        "src/main.py",
        "src/config.py",
        "src/db/schema.py",
        "Dockerfile",
    ]
    for rel in expected:
        assert (base / rel).is_file(), f"Missing fastapi-pg file: {rel}"


def test_registry_has_four_builtins():
    """registry.yaml has 4 entries all with builtin: true."""
    from src.server.routers.templates import REGISTRY_PATH

    data = yaml.safe_load(REGISTRY_PATH.read_text())
    templates = data["templates"]
    assert len(templates) == 4
    for t in templates:
        assert t["builtin"] is True, f"{t['id']} not builtin"


# --- HTTP tests ---


async def test_list_templates(client):
    """GET /templates returns 200 with 4 builtin templates."""
    resp = await client.get("/templates", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["templates"]) == 4
    ids = {t["id"] for t in data["templates"]}
    assert ids == {"blank", "fastapi-pg", "telegram-bot", "cli-tool"}


async def test_get_template_detail(client):
    """GET /templates/fastapi-pg returns 200 with detail + files."""
    resp = await client.get("/templates/fastapi-pg", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "fastapi-pg"
    assert data["builtin"] is True
    assert isinstance(data["files"], list)
    assert len(data["files"]) > 0


async def test_get_template_detail_files_have_type(client):
    """Each file in detail response has path, type, size."""
    resp = await client.get("/templates/fastapi-pg", headers=AUTH_HEADERS)
    data = resp.json()
    for f in data["files"]:
        assert "path" in f
        assert "type" in f
        assert f["type"] in ("jinja2", "static")
        assert "size" in f
        assert isinstance(f["size"], int)


async def test_get_template_not_found(client):
    """GET /templates/nonexistent returns 404."""
    resp = await client.get("/templates/nonexistent", headers=AUTH_HEADERS)
    assert resp.status_code == 404


async def test_templates_requires_auth(client):
    """GET /templates without auth returns 401."""
    resp = await client.get("/templates")
    assert resp.status_code == 401
