"""Integration tests for projects schema and ProjectRepository CRUD."""
import pytest
from datetime import datetime, timezone

from src.db.pg_schema import Project, Task
from src.db.pg_repository import TaskRepository, ProjectRepository


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
        Task(
            name="test-task",
            project_path="/tmp/test",
            created_at=datetime.now(timezone.utc),
        )
    )
    task = await repo.get(task_id)
    assert task is not None
    assert task.project_id is None


# --- Task 2: ProjectRepository CRUD tests ---


@pytest.mark.asyncio
async def test_project_crud(pg_pool):
    """Insert, get, list_all, delete cycle for ProjectRepository."""
    repo = ProjectRepository(pg_pool)
    project = Project(
        name="My Project",
        slug="my-project",
        path="/home/ubuntu/projects/my-project",
        created_at=datetime.now(timezone.utc),
        description="A test project",
    )
    # Insert
    pid = await repo.insert(project)
    assert isinstance(pid, int)

    # Get
    fetched = await repo.get(pid)
    assert fetched is not None
    assert fetched.id == pid
    assert fetched.name == "My Project"
    assert fetched.slug == "my-project"
    assert fetched.path == "/home/ubuntu/projects/my-project"
    assert fetched.description == "A test project"
    assert fetched.last_used_at is None

    # List all
    all_projects = await repo.list_all()
    assert any(p.id == pid for p in all_projects)

    # Delete
    await repo.delete(pid)
    assert await repo.get(pid) is None


@pytest.mark.asyncio
async def test_update_last_used(pg_pool):
    """update_last_used should set a non-None timestamp."""
    repo = ProjectRepository(pg_pool)
    project = Project(
        name="Updated Project",
        slug="updated-project",
        path="/home/ubuntu/projects/updated",
        created_at=datetime.now(timezone.utc),
    )
    pid = await repo.insert(project)
    fetched = await repo.get(pid)
    assert fetched.last_used_at is None

    await repo.update_last_used(pid)
    fetched = await repo.get(pid)
    assert fetched.last_used_at is not None

    # cleanup
    await repo.delete(pid)


@pytest.mark.asyncio
async def test_get_nonexistent_project(pg_pool):
    """get() should return None for non-existent id."""
    repo = ProjectRepository(pg_pool)
    assert await repo.get(99999) is None
