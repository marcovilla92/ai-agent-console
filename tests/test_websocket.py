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
