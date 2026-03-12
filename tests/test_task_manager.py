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


# --- Phase 9: Approval gate tests ---


from src.server.connection_manager import ConnectionManager


async def test_supervised_pauses_at_reroute(pg_pool):
    """In supervised mode, confirm_reroute pauses via asyncio.Event and resumes on approve."""
    cm = ConnectionManager()
    ctx = WebTaskContext(
        task_id=1, pool=pg_pool, mode="supervised",
        project_path="/tmp", connection_manager=cm,
    )

    result_holder = {}

    async def call_confirm():
        result_holder["result"] = await ctx.confirm_reroute("editor", "needs editing")

    task = asyncio.create_task(call_confirm())
    # Give confirm_reroute time to set up the event and await
    await asyncio.sleep(0.1)

    # Should be awaiting approval
    assert ctx._approval_event is not None
    assert not ctx._approval_event.is_set()

    # Approve
    ctx.set_approval("approve")
    await asyncio.wait_for(task, timeout=2.0)

    assert result_holder["result"] is True


async def test_supervised_pauses_at_halt(pg_pool):
    """In supervised mode, handle_halt pauses via asyncio.Event and returns decision string."""
    cm = ConnectionManager()
    ctx = WebTaskContext(
        task_id=1, pool=pg_pool, mode="supervised",
        project_path="/tmp", connection_manager=cm,
    )

    result_holder = {}

    async def call_halt():
        result_holder["result"] = await ctx.handle_halt(5)

    task = asyncio.create_task(call_halt())
    await asyncio.sleep(0.1)

    assert ctx._approval_event is not None
    assert not ctx._approval_event.is_set()

    ctx.set_approval("reject")
    await asyncio.wait_for(task, timeout=2.0)

    assert result_holder["result"] == "reject"


async def test_autonomous_no_pause(pg_pool):
    """In autonomous mode, confirm_reroute returns True and handle_halt returns 'approve' immediately."""
    ctx = WebTaskContext(
        task_id=1, pool=pg_pool, mode="autonomous", project_path="/tmp",
    )

    result = await ctx.confirm_reroute("editor", "needs editing")
    assert result is True
    assert ctx._approval_event is None

    halt_result = await ctx.handle_halt(3)
    assert halt_result == "approve"
    assert ctx._approval_event is None


async def test_approval_includes_context(pg_pool):
    """send_approval_required is called with correct action and context dict."""
    cm = AsyncMock(spec=ConnectionManager)
    ctx = WebTaskContext(
        task_id=42, pool=pg_pool, mode="supervised",
        project_path="/tmp", connection_manager=cm,
    )

    async def approve_after_delay():
        await asyncio.sleep(0.1)
        ctx.set_approval("approve")

    # Test reroute context
    asyncio.create_task(approve_after_delay())
    await asyncio.wait_for(ctx.confirm_reroute("editor", "needs editing"), timeout=2.0)

    cm.send_approval_required.assert_called_once_with(
        42, "reroute", {"next_agent": "editor", "reasoning": "needs editing"}
    )

    # Reset mock, test halt context
    cm.reset_mock()
    asyncio.create_task(approve_after_delay())
    await asyncio.wait_for(ctx.handle_halt(7), timeout=2.0)

    cm.send_approval_required.assert_called_once_with(
        42, "halt", {"iteration_count": 7}
    )


async def test_cancel_while_awaiting(pg_pool):
    """Cancelling while awaiting _approval_event propagates CancelledError cleanly."""
    cm = AsyncMock(spec=ConnectionManager)
    ctx = WebTaskContext(
        task_id=1, pool=pg_pool, mode="supervised",
        project_path="/tmp", connection_manager=cm,
    )

    async def call_confirm():
        return await ctx.confirm_reroute("editor", "reason")

    task = asyncio.create_task(call_confirm())
    await asyncio.sleep(0.1)

    # Event should be waiting
    assert ctx._approval_event is not None
    assert not ctx._approval_event.is_set()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_manager_approve_relays(pg_pool):
    """TaskManager.approve relays decision to context and returns True."""
    barrier = asyncio.Event()

    async def blocking_orchestrate(ctx, prompt, pool, task_id):
        # Simulate supervised reroute pause
        await ctx.confirm_reroute("editor", "reason")
        barrier.set()

    with patch("src.engine.manager.orchestrate_pipeline", new=AsyncMock(side_effect=blocking_orchestrate)):
        mgr = TaskManager(pg_pool, connection_manager=AsyncMock(spec=ConnectionManager))
        task_id = await mgr.submit("test approve", mode="supervised", project_path="/tmp")

        await asyncio.sleep(0.3)

        # Should be awaiting approval
        result = await mgr.approve(task_id, "approve")
        assert result is True

        # Pipeline should complete
        await asyncio.wait_for(barrier.wait(), timeout=2.0)

        # Approve on non-existent task returns False
        result2 = await mgr.approve(99999, "approve")
        assert result2 is False

        await mgr.shutdown()


async def test_send_approval_required_broadcasts(pg_pool):
    """ConnectionManager.send_approval_required broadcasts correct message."""
    cm = ConnectionManager()

    # Create a mock websocket
    mock_ws = AsyncMock()
    cm._connections[10] = {mock_ws}

    await cm.send_approval_required(10, "reroute", {"next_agent": "editor", "reasoning": "test"})

    mock_ws.send_json.assert_called_once_with({
        "type": "approval_required",
        "data": {"action": "reroute", "context": {"next_agent": "editor", "reasoning": "test"}},
    })
