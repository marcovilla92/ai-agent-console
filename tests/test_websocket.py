"""
Tests for WebSocket streaming: ConnectionManager, WS endpoint with auth and heartbeat.

Requires a running PostgreSQL instance (TEST_DATABASE_URL env var or default).
"""
import asyncio
import base64
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from src.server.app import create_app

pytestmark = pytest.mark.asyncio

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://n8n:Amc2017!m@10.0.1.7:5432/agent_console_test",
)

VALID_TOKEN = base64.b64encode(b"admin:changeme").decode()
BAD_TOKEN = base64.b64encode(b"admin:wrong").decode()


# --- ConnectionManager unit tests ---


async def test_connection_manager_lifecycle():
    """ConnectionManager.connect adds websocket to task set, disconnect removes it."""
    from src.server.connection_manager import ConnectionManager

    mgr = ConnectionManager()
    ws = AsyncMock()

    await mgr.connect(1, ws)
    assert mgr.has_connections(1)

    mgr.disconnect(1, ws)
    assert not mgr.has_connections(1)


async def test_connection_manager_send_chunk():
    """send_chunk delivers JSON with type=chunk to all connected sockets."""
    from src.server.connection_manager import ConnectionManager

    mgr = ConnectionManager()
    ws1 = AsyncMock()
    ws2 = AsyncMock()

    await mgr.connect(1, ws1)
    await mgr.connect(1, ws2)

    await mgr.send_chunk(1, "hello world")

    ws1.send_json.assert_called_once_with({"type": "chunk", "data": "hello world"})
    ws2.send_json.assert_called_once_with({"type": "chunk", "data": "hello world"})


async def test_connection_manager_send_status():
    """send_status delivers JSON with type=status to all connected sockets."""
    from src.server.connection_manager import ConnectionManager

    mgr = ConnectionManager()
    ws = AsyncMock()

    await mgr.connect(1, ws)
    await mgr.send_status(1, "completed")

    ws.send_json.assert_called_once_with({"type": "status", "data": "completed"})


async def test_connection_manager_prunes_dead():
    """send_chunk removes sockets that raise on send."""
    from src.server.connection_manager import ConnectionManager

    mgr = ConnectionManager()
    good_ws = AsyncMock()
    dead_ws = AsyncMock()
    dead_ws.send_json.side_effect = Exception("connection closed")

    await mgr.connect(1, good_ws)
    await mgr.connect(1, dead_ws)

    await mgr.send_chunk(1, "test")

    good_ws.send_json.assert_called_once()
    # Dead socket should have been pruned
    assert dead_ws not in mgr._connections.get(1, set())


# --- WebSocket endpoint integration tests ---


@pytest.fixture
def sync_app():
    """Create a FastAPI app with lifespan for sync TestClient."""
    os.environ["APP_DATABASE_URL"] = TEST_DSN
    os.environ["APP_POOL_MIN_SIZE"] = "1"
    os.environ["APP_POOL_MAX_SIZE"] = "2"
    from src.server.config import get_settings
    get_settings.cache_clear()
    app = create_app()
    return app


def test_ws_connect_with_auth(sync_app):
    """WebSocket at /ws/tasks/{task_id}?token={base64_creds} accepts connection."""
    with TestClient(sync_app) as client:
        with client.websocket_connect(f"/ws/tasks/1?token={VALID_TOKEN}") as ws:
            # Connection accepted -- send a message to keep alive briefly
            # The endpoint should accept without error
            pass  # Connection opened successfully


def test_ws_rejects_invalid_auth(sync_app):
    """WebSocket with invalid token is rejected with close code 1008."""
    with TestClient(sync_app) as client:
        try:
            with client.websocket_connect(f"/ws/tasks/1?token={BAD_TOKEN}"):
                pytest.fail("Should have been rejected")
        except Exception:
            pass  # Expected: connection rejected


def test_ws_rejects_missing_auth(sync_app):
    """WebSocket without token is rejected."""
    with TestClient(sync_app) as client:
        try:
            with client.websocket_connect("/ws/tasks/1"):
                pytest.fail("Should have been rejected")
        except Exception:
            pass  # Expected: connection rejected


async def test_disconnect_cleanup():
    """ConnectionManager.disconnect removes socket and cleans up empty sets."""
    from src.server.connection_manager import ConnectionManager

    mgr = ConnectionManager()
    ws1 = AsyncMock()
    ws2 = AsyncMock()

    await mgr.connect(1, ws1)
    await mgr.connect(1, ws2)
    assert mgr.has_connections(1)

    mgr.disconnect(1, ws1)
    assert mgr.has_connections(1)  # ws2 still there

    mgr.disconnect(1, ws2)
    assert not mgr.has_connections(1)
    # Internal dict key should be cleaned up
    assert 1 not in mgr._connections


async def test_heartbeat_sends_ping():
    """Heartbeat coroutine sends ping messages at the configured interval."""
    from src.server.routers.ws import _heartbeat

    ws = AsyncMock()
    # Run heartbeat with very short interval
    task = asyncio.create_task(_heartbeat(ws, interval=0.05))
    await asyncio.sleep(0.15)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Should have sent at least 2 pings in 0.15s with 0.05s interval
    assert ws.send_json.call_count >= 2
    ws.send_json.assert_called_with({"type": "ping"})


# --- Task 2: WebTaskContext broadcasting and TaskManager status events ---


async def test_context_works_without_connection_manager():
    """WebTaskContext.stream_output works normally when connection_manager is None."""
    from src.engine.context import WebTaskContext

    pool = AsyncMock()
    ctx = WebTaskContext(task_id=1, pool=pool, mode="autonomous")

    # Mock stream_claude to yield some text
    async def mock_stream(prompt):
        yield "hello"
        yield "world"

    with patch("src.engine.context.stream_claude", side_effect=mock_stream):
        with patch("src.engine.context.AgentOutputRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo
            result = await ctx.stream_output("test_agent", "test prompt", {})

    # Should work without error -- backward compatible
    assert isinstance(result, dict)


async def test_ws_receives_chunks():
    """When stream_output runs with a ConnectionManager, chunks are sent."""
    from src.engine.context import WebTaskContext
    from src.server.connection_manager import ConnectionManager

    mgr = ConnectionManager()
    mock_ws = AsyncMock()
    await mgr.connect(1, mock_ws)

    pool = AsyncMock()
    ctx = WebTaskContext(
        task_id=1, pool=pool, mode="autonomous",
        connection_manager=mgr,
    )

    async def mock_stream(prompt):
        yield "chunk1"
        yield "chunk2"

    with patch("src.engine.context.stream_claude", side_effect=mock_stream):
        with patch("src.engine.context.AgentOutputRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo
            await ctx.stream_output("test_agent", "test prompt", {})

    # Should have sent chunk messages to the websocket
    calls = mock_ws.send_json.call_args_list
    chunk_calls = [c for c in calls if c[0][0].get("type") == "chunk"]
    assert len(chunk_calls) == 2
    assert chunk_calls[0][0][0] == {"type": "chunk", "data": "chunk1"}
    assert chunk_calls[1][0][0] == {"type": "chunk", "data": "chunk2"}


async def test_task_status_sent_on_completion():
    """When task completes, ConnectionManager.send_status is called with 'completed'."""
    from src.server.connection_manager import ConnectionManager

    mgr = ConnectionManager()
    mgr.send_status = AsyncMock()

    pool = AsyncMock()
    # Mock TaskRepository
    with patch("src.engine.manager.TaskRepository") as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.create.return_value = 1
        mock_repo_cls.return_value = mock_repo

        from src.engine.manager import TaskManager
        tm = TaskManager(pool=pool, max_concurrent=2, connection_manager=mgr)

        with patch("src.engine.manager.orchestrate_pipeline", new_callable=AsyncMock):
            task_id = await tm.submit("test prompt")
            # Wait for async task to complete
            await asyncio.sleep(0.2)

    mgr.send_status.assert_any_call(task_id, "completed")


async def test_task_status_sent_on_failure():
    """When task fails, ConnectionManager.send_status is called with 'failed'."""
    from src.server.connection_manager import ConnectionManager

    mgr = ConnectionManager()
    mgr.send_status = AsyncMock()

    pool = AsyncMock()
    with patch("src.engine.manager.TaskRepository") as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.create.return_value = 1
        mock_repo_cls.return_value = mock_repo

        from src.engine.manager import TaskManager
        tm = TaskManager(pool=pool, max_concurrent=2, connection_manager=mgr)

        with patch(
            "src.engine.manager.orchestrate_pipeline",
            side_effect=RuntimeError("boom"),
        ):
            task_id = await tm.submit("test prompt")
            await asyncio.sleep(0.2)

    mgr.send_status.assert_any_call(task_id, "failed")
