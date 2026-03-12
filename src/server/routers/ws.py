"""
WebSocket router for real-time task output streaming.

Endpoint: /ws/tasks/{task_id}?token={base64_creds}

Sends:
  - {"type": "chunk", "data": "..."} for each output chunk
  - {"type": "status", "data": "completed|failed|cancelled"} on task finish
  - {"type": "ping"} every 25 seconds for proxy keepalive
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from src.server.connection_manager import ConnectionManager
from src.server.dependencies import verify_ws_token

log = logging.getLogger(__name__)

ws_router = APIRouter()


async def _heartbeat(websocket: WebSocket, interval: float = 25.0) -> None:
    """Send periodic ping messages to keep proxied connections alive."""
    try:
        while True:
            await asyncio.sleep(interval)
            await websocket.send_json({"type": "ping"})
    except Exception:
        pass  # Connection closed or cancelled -- exit silently


@ws_router.websocket("/ws/tasks/{task_id}")
async def websocket_task_stream(
    websocket: WebSocket,
    task_id: int,
    username: str = Depends(verify_ws_token),
) -> None:
    """Stream task output over WebSocket.

    After connection:
    1. Check if task is already completed/failed/cancelled -- if so, send
       final status and close.
    2. Otherwise, register with ConnectionManager and wait for messages.
    3. Heartbeat pings sent every 25 seconds.
    4. Clean disconnect on client close.
    """
    manager: ConnectionManager = websocket.app.state.connection_manager

    await manager.connect(task_id, websocket)
    log.info("WS connected: task_id=%d user=%s", task_id, username)

    # Check if task is already in a terminal state
    try:
        from src.db.pg_repository import TaskRepository
        pool = websocket.app.state.pool
        repo = TaskRepository(pool)
        task = await repo.get(task_id)
        if task and task.status in ("completed", "failed", "cancelled"):
            await websocket.send_json({"type": "status", "data": task.status})
            manager.disconnect(task_id, websocket)
            await websocket.close()
            return
    except Exception:
        log.exception("Error checking task status for WS task_id=%d", task_id)

    # Spawn heartbeat
    heartbeat_task = asyncio.create_task(_heartbeat(websocket))

    try:
        while True:
            # Keep connection open; incoming messages ignored in Phase 8
            await websocket.receive_text()
    except WebSocketDisconnect:
        log.info("WS disconnected: task_id=%d user=%s", task_id, username)
    except Exception:
        log.debug("WS error: task_id=%d", task_id, exc_info=True)
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        manager.disconnect(task_id, websocket)
