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


# --- Custom CRUD tests (Plan 02) ---


@pytest.fixture
def tmp_templates(tmp_path, monkeypatch):
    """Create isolated template directory with registry for testing."""
    import src.server.routers.templates as tmpl_mod

    registry = {
        "templates": [
            {
                "id": "blank",
                "name": "Vuoto",
                "description": "Minimal",
                "builtin": True,
            },
        ]
    }
    (tmp_path / "registry.yaml").write_text(yaml.safe_dump(registry))
    (tmp_path / "blank").mkdir()
    (tmp_path / "blank" / "CLAUDE.md.j2").write_text("# {{ name }}")
    monkeypatch.setattr(tmpl_mod, "TEMPLATES_ROOT", tmp_path)
    monkeypatch.setattr(tmpl_mod, "REGISTRY_PATH", tmp_path / "registry.yaml")
    return tmp_path


@pytest.fixture
def crud_client(app_with_pool, tmp_templates):
    transport = ASGITransport(app=app_with_pool)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_create_custom_template(crud_client):
    """POST /templates creates custom template and returns 201."""
    payload = {
        "id": "my-tpl",
        "name": "My Template",
        "description": "A custom template",
        "files": {"README.md": "# Hello"},
    }
    resp = await crud_client.post(
        "/templates", json=payload, headers=AUTH_HEADERS
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "my-tpl"
    assert data["name"] == "My Template"
    assert data["description"] == "A custom template"
    assert data["builtin"] is False
    assert data["file_count"] == 1


async def test_create_custom_template_files_on_disk(crud_client, tmp_templates):
    """After POST, template files exist on disk."""
    payload = {
        "id": "disk-tpl",
        "name": "Disk Test",
        "files": {"src/main.py": "print('hello')", "README.md": "# Hi"},
    }
    resp = await crud_client.post(
        "/templates", json=payload, headers=AUTH_HEADERS
    )
    assert resp.status_code == 201
    assert (tmp_templates / "disk-tpl" / "src" / "main.py").is_file()
    assert (tmp_templates / "disk-tpl" / "README.md").is_file()
    assert (tmp_templates / "disk-tpl" / "README.md").read_text() == "# Hi"


async def test_create_duplicate_template(crud_client):
    """POST /templates with existing id returns 409."""
    payload = {"id": "blank", "name": "Duplicate", "files": {}}
    resp = await crud_client.post(
        "/templates", json=payload, headers=AUTH_HEADERS
    )
    assert resp.status_code == 409


async def test_create_template_path_traversal(crud_client):
    """POST /templates with '../' in file path returns 400."""
    payload = {
        "id": "evil-tpl",
        "name": "Evil",
        "files": {"../../../etc/passwd": "hacked"},
    }
    resp = await crud_client.post(
        "/templates", json=payload, headers=AUTH_HEADERS
    )
    assert resp.status_code == 400


async def test_update_custom_template(crud_client, tmp_templates):
    """PUT /templates/{id} updates metadata and files."""
    # First create a template
    create_payload = {
        "id": "upd-tpl",
        "name": "Original",
        "description": "Original desc",
        "files": {"a.txt": "aaa", "b.txt": "bbb"},
    }
    resp = await crud_client.post(
        "/templates", json=create_payload, headers=AUTH_HEADERS
    )
    assert resp.status_code == 201

    # Now update it
    update_payload = {
        "name": "Updated",
        "files_upsert": {"a.txt": "AAA", "c.txt": "ccc"},
        "files_delete": ["b.txt"],
    }
    resp = await crud_client.put(
        "/templates/upd-tpl", json=update_payload, headers=AUTH_HEADERS
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Updated"
    assert data["builtin"] is False
    # a.txt updated, c.txt created, b.txt deleted -> 2 files
    assert data["file_count"] == 2
    assert (tmp_templates / "upd-tpl" / "a.txt").read_text() == "AAA"
    assert (tmp_templates / "upd-tpl" / "c.txt").read_text() == "ccc"
    assert not (tmp_templates / "upd-tpl" / "b.txt").exists()


async def test_update_builtin_template_forbidden(crud_client):
    """PUT /templates/blank returns 403."""
    resp = await crud_client.put(
        "/templates/blank", json={"name": "Hacked"}, headers=AUTH_HEADERS
    )
    assert resp.status_code == 403


async def test_update_nonexistent_template(crud_client):
    """PUT /templates/nonexistent returns 404."""
    resp = await crud_client.put(
        "/templates/nonexistent", json={"name": "Nope"}, headers=AUTH_HEADERS
    )
    assert resp.status_code == 404


async def test_delete_custom_template(crud_client, tmp_templates):
    """DELETE /templates/{id} removes dir + registry entry."""
    # Create first
    payload = {"id": "del-tpl", "name": "To Delete", "files": {"x.txt": "x"}}
    resp = await crud_client.post(
        "/templates", json=payload, headers=AUTH_HEADERS
    )
    assert resp.status_code == 201

    # Delete
    resp = await crud_client.delete(
        "/templates/del-tpl", headers=AUTH_HEADERS
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"
    assert data["id"] == "del-tpl"
    assert not (tmp_templates / "del-tpl").exists()


async def test_delete_builtin_template_forbidden(crud_client):
    """DELETE /templates/blank returns 403."""
    resp = await crud_client.delete(
        "/templates/blank", headers=AUTH_HEADERS
    )
    assert resp.status_code == 403


async def test_delete_nonexistent_template(crud_client):
    """DELETE /templates/nonexistent returns 404."""
    resp = await crud_client.delete(
        "/templates/nonexistent", headers=AUTH_HEADERS
    )
    assert resp.status_code == 404


async def test_list_includes_custom_after_create(crud_client):
    """After POST, GET /templates includes the new custom template."""
    payload = {"id": "listed-tpl", "name": "Listed", "files": {}}
    resp = await crud_client.post(
        "/templates", json=payload, headers=AUTH_HEADERS
    )
    assert resp.status_code == 201

    resp = await crud_client.get("/templates", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    ids = {t["id"] for t in resp.json()["templates"]}
    assert "listed-tpl" in ids
    # Check it's marked as non-builtin
    custom = next(t for t in resp.json()["templates"] if t["id"] == "listed-tpl")
    assert custom["builtin"] is False
