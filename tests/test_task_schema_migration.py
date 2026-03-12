"""
Tests for Task schema migration: status, mode, prompt, completed_at, error fields.

TDD RED phase: these tests define the expected behavior for the updated
Task dataclass, TaskRepository CRUD with new fields, and update_status method.
"""
from datetime import datetime, timezone

import pytest

from src.db.pg_schema import Task
from src.db.pg_repository import TaskRepository

pytestmark = pytest.mark.asyncio


async def test_task_dataclass_accepts_new_fields():
    """Task dataclass accepts status, mode, prompt, completed_at, error fields."""
    now = datetime.now(timezone.utc)
    task = Task(
        name="test",
        project_path="/tmp",
        created_at=now,
        status="running",
        mode="supervised",
        prompt="Build something",
        completed_at=now,
        error="something went wrong",
    )
    assert task.status == "running"
    assert task.mode == "supervised"
    assert task.prompt == "Build something"
    assert task.completed_at == now
    assert task.error == "something went wrong"


async def test_task_dataclass_defaults():
    """Task dataclass has sensible defaults for new fields."""
    now = datetime.now(timezone.utc)
    task = Task(name="test", project_path="/tmp", created_at=now)
    assert task.status == "queued"
    assert task.mode == "autonomous"
    assert task.prompt == ""
    assert task.completed_at is None
    assert task.error is None


async def test_create_with_new_fields(pg_pool):
    """TaskRepository.create inserts and returns a task with status/mode/prompt."""
    repo = TaskRepository(pg_pool)
    now = datetime.now(timezone.utc)
    task = Task(
        name="full-task",
        project_path="/tmp/proj",
        created_at=now,
        status="queued",
        mode="supervised",
        prompt="Do the thing",
    )
    task_id = await repo.create(task)
    assert isinstance(task_id, int)

    fetched = await repo.get(task_id)
    assert fetched is not None
    assert fetched.status == "queued"
    assert fetched.mode == "supervised"
    assert fetched.prompt == "Do the thing"
    assert fetched.completed_at is None
    assert fetched.error is None


async def test_update_status(pg_pool):
    """TaskRepository.update_status changes status and optionally sets completed_at/error."""
    repo = TaskRepository(pg_pool)
    now = datetime.now(timezone.utc)
    task = Task(name="status-test", project_path="/tmp", created_at=now)
    task_id = await repo.create(task)

    # Update to running
    await repo.update_status(task_id, "running")
    fetched = await repo.get(task_id)
    assert fetched.status == "running"
    assert fetched.completed_at is None

    # Update to failed with error and completed_at
    completed = datetime.now(timezone.utc)
    await repo.update_status(task_id, "failed", error="boom", completed_at=completed)
    fetched = await repo.get(task_id)
    assert fetched.status == "failed"
    assert fetched.error == "boom"
    assert fetched.completed_at is not None


async def test_list_all_returns_new_fields(pg_pool):
    """TaskRepository.list_all returns tasks with all new fields populated."""
    repo = TaskRepository(pg_pool)
    now = datetime.now(timezone.utc)
    task = Task(
        name="list-test",
        project_path="/tmp",
        created_at=now,
        status="completed",
        mode="autonomous",
        prompt="test prompt",
        completed_at=now,
        error=None,
    )
    task_id = await repo.create(task)

    all_tasks = await repo.list_all()
    found = [t for t in all_tasks if t.id == task_id]
    assert len(found) == 1
    assert found[0].status == "completed"
    assert found[0].mode == "autonomous"
    assert found[0].prompt == "test prompt"
    assert found[0].completed_at is not None
