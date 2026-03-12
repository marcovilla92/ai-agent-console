"""
Tests for TaskManager concurrency, cancellation, mode, and WebTaskContext Protocol.

Uses real asyncpg pool for DB operations. Mocks orchestrate_pipeline to avoid
real Claude CLI calls.
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.db.pg_repository import TaskRepository
from src.engine.context import WebTaskContext
from src.engine.manager import TaskManager
from src.pipeline.protocol import TaskContext

pytestmark = pytest.mark.asyncio


async def _slow_orchestrate(*args, **kwargs):
    """Mock orchestrate_pipeline that sleeps to simulate work."""
    await asyncio.sleep(0.5)


async def _failing_orchestrate(*args, **kwargs):
    """Mock orchestrate_pipeline that raises an exception."""
    raise RuntimeError("agent exploded")


async def test_submit_creates_db_row_and_asyncio_task(pg_pool):
    """TaskManager.submit creates a DB row and starts an asyncio.Task."""
    with patch("src.engine.manager.orchestrate_pipeline", new=AsyncMock(side_effect=_slow_orchestrate)):
        mgr = TaskManager(pg_pool)
        task_id = await mgr.submit("Build a web app", mode="autonomous", project_path="/tmp")

        assert isinstance(task_id, int)
        assert task_id > 0

        # DB row exists
        repo = TaskRepository(pg_pool)
        task = await repo.get(task_id)
        assert task is not None
        assert task.name == "Build a web app"[:50]
        assert task.prompt == "Build a web app"

        # asyncio.Task is running
        assert task_id in mgr._running

        await mgr.shutdown()


async def test_two_tasks_run_concurrently(pg_pool):
    """Two submitted tasks both reach 'running' status concurrently."""
    running_count = asyncio.Event()
    count = 0

    async def counting_orchestrate(*args, **kwargs):
        nonlocal count
        count += 1
        if count >= 2:
            running_count.set()
        await asyncio.sleep(1.0)

    with patch("src.engine.manager.orchestrate_pipeline", new=AsyncMock(side_effect=counting_orchestrate)):
        mgr = TaskManager(pg_pool)
        id1 = await mgr.submit("task one", project_path="/tmp")
        id2 = await mgr.submit("task two", project_path="/tmp")

        # Wait for both to start running
        await asyncio.wait_for(running_count.wait(), timeout=2.0)

        repo = TaskRepository(pg_pool)
        t1 = await repo.get(id1)
        t2 = await repo.get(id2)
        assert t1.status == "running"
        assert t2.status == "running"

        await mgr.shutdown()


async def test_third_task_queues_until_slot_opens(pg_pool):
    """Third submitted task stays 'queued' until a slot opens."""
    barrier = asyncio.Event()

    async def blocking_orchestrate(*args, **kwargs):
        await barrier.wait()

    with patch("src.engine.manager.orchestrate_pipeline", new=AsyncMock(side_effect=blocking_orchestrate)):
        mgr = TaskManager(pg_pool, max_concurrent=2)
        id1 = await mgr.submit("task one", project_path="/tmp")
        id2 = await mgr.submit("task two", project_path="/tmp")
        id3 = await mgr.submit("task three", project_path="/tmp")

        # Give tasks time to start
        await asyncio.sleep(0.2)

        repo = TaskRepository(pg_pool)
        t1 = await repo.get(id1)
        t2 = await repo.get(id2)
        t3 = await repo.get(id3)
        assert t1.status == "running"
        assert t2.status == "running"
        assert t3.status == "queued"

        # Release barrier -- after one finishes, third should start
        barrier.set()
        await asyncio.sleep(0.3)

        t3 = await repo.get(id3)
        # Should have transitioned (running, completed, or failed -- not queued)
        assert t3.status != "queued"

        await mgr.shutdown()


async def test_cancel_sets_status_cancelled(pg_pool):
    """TaskManager.cancel cancels the asyncio.Task and sets status to 'cancelled'."""
    barrier = asyncio.Event()

    async def blocking_orchestrate(*args, **kwargs):
        await barrier.wait()

    with patch("src.engine.manager.orchestrate_pipeline", new=AsyncMock(side_effect=blocking_orchestrate)):
        mgr = TaskManager(pg_pool)
        task_id = await mgr.submit("cancel me", project_path="/tmp")

        await asyncio.sleep(0.2)
        result = await mgr.cancel(task_id)
        assert result is True

        await asyncio.sleep(0.2)
        repo = TaskRepository(pg_pool)
        task = await repo.get(task_id)
        assert task.status == "cancelled"

        await mgr.shutdown()


async def test_mode_supervised_passes_through(pg_pool):
    """Task with mode='supervised' passes mode through to WebTaskContext."""
    captured_ctx = {}

    async def capture_orchestrate(ctx, prompt, pool=None, session_id=None):
        captured_ctx["mode"] = ctx._mode
        captured_ctx["ctx"] = ctx

    with patch("src.engine.manager.orchestrate_pipeline", new=AsyncMock(side_effect=capture_orchestrate)):
        mgr = TaskManager(pg_pool)
        await mgr.submit("supervised task", mode="supervised", project_path="/tmp")

        await asyncio.sleep(0.3)
        assert captured_ctx.get("mode") == "supervised"

        await mgr.shutdown()


async def test_failed_task_status_and_error(pg_pool):
    """Failed task sets status to 'failed' with error message."""
    with patch("src.engine.manager.orchestrate_pipeline", new=AsyncMock(side_effect=_failing_orchestrate)):
        mgr = TaskManager(pg_pool)
        task_id = await mgr.submit("doomed task", project_path="/tmp")

        await asyncio.sleep(0.3)

        repo = TaskRepository(pg_pool)
        task = await repo.get(task_id)
        assert task.status == "failed"
        assert "agent exploded" in task.error

        await mgr.shutdown()


async def test_web_task_context_satisfies_protocol(pg_pool):
    """WebTaskContext satisfies TaskContext Protocol (isinstance check)."""
    ctx = WebTaskContext(task_id=1, pool=pg_pool, mode="autonomous", project_path="/tmp")
    assert isinstance(ctx, TaskContext)
