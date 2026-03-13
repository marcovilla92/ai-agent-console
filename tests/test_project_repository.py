"""Integration tests for projects schema and ProjectRepository CRUD."""
import pytest
from datetime import datetime, timezone

from src.db.pg_schema import Project
from src.db.pg_repository import TaskRepository


# --- Task 1: Schema validation tests ---


@pytest.mark.asyncio
async def test_projects_table_exists(pg_pool):
    """Projects table should have 7 columns after apply_schema()."""
    async with pg_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'projects' ORDER BY ordinal_position"
        )
    columns = [r["column_name"] for r in rows]
    assert len(columns) == 7
    assert set(columns) == {
        "id", "name", "slug", "path", "description", "created_at", "last_used_at"
    }


@pytest.mark.asyncio
async def test_tasks_project_id_nullable(pg_pool):
    """tasks.project_id column should exist and be nullable."""
    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'tasks' AND column_name = 'project_id'"
        )
    assert row is not None, "project_id column does not exist on tasks table"
    assert row["is_nullable"] == "YES"


@pytest.mark.asyncio
async def test_existing_task_crud_with_null_project_id(pg_pool):
    """Existing task CRUD should work with project_id defaulting to None."""
    repo = TaskRepository(pg_pool)
    task_id = await repo.create(
        __import__("src.db.pg_schema", fromlist=["Task"]).Task(
            name="test-task",
            project_path="/tmp/test",
            created_at=datetime.now(timezone.utc),
        )
    )
    task = await repo.get(task_id)
    assert task is not None
    assert task.project_id is None
