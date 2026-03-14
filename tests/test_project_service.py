"""Tests for ProjectEvent, detect_stack, upsert_by_path, ProjectService, and project endpoints."""
import pytest
import shutil
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.pipeline.events import ProjectEvent, emit_event
from src.context.assembler import detect_stack
from src.db.pg_schema import Project
from src.db.pg_repository import ProjectRepository
from src.pipeline.project_service import ProjectService


# ---------------------------------------------------------------------------
# TestEvents
# ---------------------------------------------------------------------------


class TestEvents:
    """Tests for ProjectEvent enum and emit_event stub."""

    def test_enum_has_six_values(self):
        assert len(ProjectEvent) == 6

    def test_enum_values(self):
        assert ProjectEvent.PROJECT_CREATED.value == "project.created"
        assert ProjectEvent.PROJECT_DELETED.value == "project.deleted"
        assert ProjectEvent.TASK_STARTED.value == "task.started"
        assert ProjectEvent.TASK_COMPLETED.value == "task.completed"
        assert ProjectEvent.TASK_FAILED.value == "task.failed"
        assert ProjectEvent.PHASE_SUGGESTED.value == "phase.suggested"

    @pytest.mark.asyncio
    async def test_emit_event_returns_none(self):
        result = await emit_event(ProjectEvent.PROJECT_CREATED, {"id": 1})
        assert result is None

    @pytest.mark.asyncio
    async def test_emit_event_does_not_raise(self):
        # Should not raise for any event type
        await emit_event(ProjectEvent.TASK_FAILED, {})


# ---------------------------------------------------------------------------
# TestDetectStack
# ---------------------------------------------------------------------------


class TestDetectStack:
    """Tests for detect_stack() extracted function."""

    def test_python_stack(self, tmp_path):
        (tmp_path / "pyproject.toml").touch()
        result = detect_stack(str(tmp_path))
        assert result == "Python"

    def test_empty_dir_returns_unknown(self, tmp_path):
        result = detect_stack(str(tmp_path))
        assert result == "unknown"

    def test_multiple_stacks(self, tmp_path):
        (tmp_path / "pyproject.toml").touch()
        (tmp_path / "Dockerfile").touch()
        result = detect_stack(str(tmp_path))
        assert "Python" in result
        assert "Docker" in result
        # Comma-separated
        assert ", " in result


# ---------------------------------------------------------------------------
# TestUpsertByPath (integration, requires pg_pool)
# ---------------------------------------------------------------------------


class TestUpsertByPath:
    """Tests for ProjectRepository.upsert_by_path."""

    @pytest.mark.asyncio
    async def test_upsert_inserts_new(self, pg_pool):
        repo = ProjectRepository(pg_pool)
        project = Project(
            name="upsert-test",
            slug="upsert-test",
            path="/tmp/upsert-test-unique-path",
            description="",
            created_at=datetime.now(timezone.utc),
        )
        result = await repo.upsert_by_path(project)
        assert isinstance(result, int)
        # Cleanup
        await repo.delete(result)

    @pytest.mark.asyncio
    async def test_upsert_duplicate_returns_none(self, pg_pool):
        repo = ProjectRepository(pg_pool)
        project = Project(
            name="upsert-dup",
            slug="upsert-dup",
            path="/tmp/upsert-dup-unique-path",
            description="",
            created_at=datetime.now(timezone.utc),
        )
        first_id = await repo.upsert_by_path(project)
        assert first_id is not None

        # Second upsert with same path should return None
        project2 = Project(
            name="upsert-dup-2",
            slug="upsert-dup-2",
            path="/tmp/upsert-dup-unique-path",
            description="",
            created_at=datetime.now(timezone.utc),
        )
        second_id = await repo.upsert_by_path(project2)
        assert second_id is None

        # Cleanup
        await repo.delete(first_id)


# ---------------------------------------------------------------------------
# TestListProjects (integration, requires pg_pool)
# ---------------------------------------------------------------------------


class TestListProjects:
    """Tests for ProjectService.list_projects()."""

    @pytest.mark.asyncio
    async def test_empty_workspace_returns_empty(self, pg_pool, tmp_path):
        svc = ProjectService(pg_pool, workspace_root=tmp_path)
        result = await svc.list_projects()
        assert result == []

    @pytest.mark.asyncio
    async def test_auto_registers_untracked_folders(self, pg_pool, tmp_path):
        # Create two subdirs, one with pyproject.toml
        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta").mkdir()
        (tmp_path / "beta" / "pyproject.toml").touch()

        svc = ProjectService(pg_pool, workspace_root=tmp_path)
        result = await svc.list_projects()

        assert len(result) == 2
        names = {p["name"] for p in result}
        assert names == {"alpha", "beta"}

        # Check stack detection
        beta = next(p for p in result if p["name"] == "beta")
        assert "Python" in beta["stack"]

        alpha = next(p for p in result if p["name"] == "alpha")
        assert alpha["stack"] == "unknown"

        # Cleanup
        repo = ProjectRepository(pg_pool)
        for p in result:
            await repo.delete(p["id"])

    @pytest.mark.asyncio
    async def test_no_duplicates_on_second_call(self, pg_pool, tmp_path):
        (tmp_path / "gamma").mkdir()

        svc = ProjectService(pg_pool, workspace_root=tmp_path)
        first = await svc.list_projects()
        second = await svc.list_projects()

        assert len(first) == len(second) == 1

        # Cleanup
        repo = ProjectRepository(pg_pool)
        for p in second:
            await repo.delete(p["id"])

    @pytest.mark.asyncio
    async def test_skips_hidden_dirs(self, pg_pool, tmp_path):
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "visible").mkdir()

        svc = ProjectService(pg_pool, workspace_root=tmp_path)
        result = await svc.list_projects()

        assert len(result) == 1
        assert result[0]["name"] == "visible"

        # Cleanup
        repo = ProjectRepository(pg_pool)
        for p in result:
            await repo.delete(p["id"])


# ---------------------------------------------------------------------------
# TestDeleteProject (integration, requires pg_pool)
# ---------------------------------------------------------------------------


class TestDeleteProject:
    """Tests for ProjectService.delete_project()."""

    @pytest.mark.asyncio
    async def test_delete_removes_from_db(self, pg_pool):
        repo = ProjectRepository(pg_pool)
        project = Project(
            name="to-delete",
            slug="to-delete",
            path="/tmp/to-delete-unique",
            description="",
            created_at=datetime.now(timezone.utc),
        )
        pid = await repo.insert(project)

        svc = ProjectService(pg_pool)
        await svc.delete_project(pid)

        assert await repo.get(pid) is None

    @pytest.mark.asyncio
    async def test_delete_emits_event(self, pg_pool):
        repo = ProjectRepository(pg_pool)
        project = Project(
            name="to-delete-evt",
            slug="to-delete-evt",
            path="/tmp/to-delete-evt-unique",
            description="",
            created_at=datetime.now(timezone.utc),
        )
        pid = await repo.insert(project)

        svc = ProjectService(pg_pool)
        with patch("src.pipeline.project_service.emit_event", new_callable=AsyncMock) as mock_emit:
            await svc.delete_project(pid)
            mock_emit.assert_called_once()
            args = mock_emit.call_args[0]
            assert args[0] == ProjectEvent.PROJECT_DELETED
            assert args[1]["id"] == pid

    @pytest.mark.asyncio
    async def test_delete_nonexistent_raises(self, pg_pool):
        svc = ProjectService(pg_pool)
        with pytest.raises(ValueError):
            await svc.delete_project(99999)


# ---------------------------------------------------------------------------
# TestCreateProject (integration, requires pg_pool)
# ---------------------------------------------------------------------------


class TestCreateProject:
    """Tests for ProjectService.create_project()."""

    @pytest.mark.asyncio
    async def test_create_project_scaffolds_from_blank(self, pg_pool, tmp_path):
        svc = ProjectService(pg_pool, workspace_root=tmp_path)
        project = await svc.create_project("My API", "A test project", "blank")

        # Verify folder exists
        project_dir = tmp_path / "my-api"
        assert project_dir.is_dir()

        # Verify CLAUDE.md rendered from template (no .j2 extension)
        claude_md = project_dir / "CLAUDE.md"
        assert claude_md.is_file()
        content = claude_md.read_text()
        assert "My API" in content
        assert "A test project" in content

        # Verify .planning dir copied from template
        assert (project_dir / ".planning" / "README.md").is_file()

        # Verify git initialized
        assert (project_dir / ".git").is_dir()

        # Verify DB record
        assert project.id is not None
        assert project.name == "My API"
        assert project.slug == "my-api"

        # Cleanup
        repo = ProjectRepository(pg_pool)
        await repo.delete(project.id)
        shutil.rmtree(project_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_create_project_duplicate_raises(self, pg_pool, tmp_path):
        svc = ProjectService(pg_pool, workspace_root=tmp_path)
        project = await svc.create_project("Duplicate Test", "first", "blank")

        with pytest.raises(FileExistsError):
            await svc.create_project("Duplicate Test", "second", "blank")

        # Cleanup
        repo = ProjectRepository(pg_pool)
        await repo.delete(project.id)
        shutil.rmtree(tmp_path / "duplicate-test", ignore_errors=True)

    @pytest.mark.asyncio
    async def test_create_project_invalid_template_raises(self, pg_pool, tmp_path):
        svc = ProjectService(pg_pool, workspace_root=tmp_path)
        with pytest.raises(ValueError, match="Template .* not found"):
            await svc.create_project("Bad Template", "", "nonexistent-template-xyz")

    @pytest.mark.asyncio
    async def test_create_project_emits_event(self, pg_pool, tmp_path):
        svc = ProjectService(pg_pool, workspace_root=tmp_path)
        with patch("src.pipeline.project_service.emit_event", new_callable=AsyncMock) as mock_emit:
            project = await svc.create_project("Event Test", "", "blank")
            mock_emit.assert_called()
            # Find the PROJECT_CREATED call
            calls = [c for c in mock_emit.call_args_list if c[0][0] == ProjectEvent.PROJECT_CREATED]
            assert len(calls) == 1
            assert calls[0][0][1]["name"] == "Event Test"

        # Cleanup
        repo = ProjectRepository(pg_pool)
        await repo.delete(project.id)
        shutil.rmtree(tmp_path / "event-test", ignore_errors=True)


# ---------------------------------------------------------------------------
# TestProjectEndpoints (integration, requires pg_pool + httpx)
# ---------------------------------------------------------------------------


class TestProjectEndpoints:
    """Tests for GET/POST/DELETE /projects endpoints via httpx."""

    @pytest.fixture
    def auth(self):
        """HTTP Basic auth tuple for test requests."""
        return ("admin", "changeme")

    @pytest.fixture
    async def client(self, pg_pool):
        """Async httpx client with test app (no lifespan)."""
        import httpx
        from contextlib import asynccontextmanager
        from unittest.mock import AsyncMock as AM
        from fastapi import FastAPI
        from src.server.routers.projects import project_router
        from src.server.routers.templates import template_router

        @asynccontextmanager
        async def noop_lifespan(app):
            yield

        app = FastAPI(lifespan=noop_lifespan)
        app.state.pool = pg_pool
        app.state.connection_manager = AM()
        app.state.task_manager = AM()
        app.include_router(project_router)
        app.include_router(template_router)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as c:
            yield c

    @pytest.mark.asyncio
    async def test_get_projects_returns_list(self, client, auth):
        resp = await client.get("/projects", auth=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert "projects" in data
        assert "count" in data
        assert isinstance(data["projects"], list)

    @pytest.mark.asyncio
    async def test_post_project_returns_201(self, client, auth, pg_pool, tmp_path):
        # We need to patch the workspace root so it uses tmp_path
        with patch.object(ProjectService, "WORKSPACE_ROOT", tmp_path):
            resp = await client.post(
                "/projects",
                json={"name": "Endpoint Test", "description": "test desc", "template": "blank"},
                auth=auth,
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Endpoint Test"
        assert data["slug"] == "endpoint-test"
        assert "id" in data

        # Cleanup
        repo = ProjectRepository(pg_pool)
        await repo.delete(data["id"])
        shutil.rmtree(tmp_path / "endpoint-test", ignore_errors=True)

    @pytest.mark.asyncio
    async def test_post_project_duplicate_returns_409(self, client, auth, pg_pool, tmp_path):
        with patch.object(ProjectService, "WORKSPACE_ROOT", tmp_path):
            resp1 = await client.post(
                "/projects",
                json={"name": "Dup Endpoint", "template": "blank"},
                auth=auth,
            )
            assert resp1.status_code == 201

            resp2 = await client.post(
                "/projects",
                json={"name": "Dup Endpoint", "template": "blank"},
                auth=auth,
            )
            assert resp2.status_code == 409

        # Cleanup
        repo = ProjectRepository(pg_pool)
        await repo.delete(resp1.json()["id"])
        shutil.rmtree(tmp_path / "dup-endpoint", ignore_errors=True)

    @pytest.mark.asyncio
    async def test_delete_project_returns_200(self, client, auth, pg_pool):
        # Insert directly via repo
        repo = ProjectRepository(pg_pool)
        project = Project(
            name="del-ep-test",
            slug="del-ep-test",
            path="/tmp/del-ep-test-unique",
            description="",
            created_at=datetime.now(timezone.utc),
        )
        pid = await repo.insert(project)

        resp = await client.delete(f"/projects/{pid}", auth=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"
        assert data["id"] == pid

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, client, auth):
        resp = await client.delete("/projects/99999", auth=auth)
        assert resp.status_code == 404
