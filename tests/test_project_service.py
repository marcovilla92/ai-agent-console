"""Tests for ProjectEvent, detect_stack, upsert_by_path, and ProjectService."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from src.pipeline.events import ProjectEvent, emit_event
from src.context.assembler import detect_stack
from src.db.pg_schema import Project
from src.db.pg_repository import ProjectRepository


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
