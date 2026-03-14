"""Tests for ProjectEvent, detect_stack, upsert_by_path, and ProjectService."""
import pytest
from datetime import datetime, timezone
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
