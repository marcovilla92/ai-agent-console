"""
ConnectionManager: Tracks WebSocket connections per task_id.

Provides broadcasting of chunk and status messages to all connected clients
for a given task. Prunes dead connections automatically.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)


class ConnectionManager:
    """Maps task_id to sets of connected WebSockets.

    Thread-safe within a single asyncio event loop (all methods are
    coroutines or synchronous with no blocking).
    """

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = {}

    async def connect(self, task_id: int, websocket: WebSocket) -> None:
        """Accept and register a WebSocket for a task."""
        await websocket.accept()
        if task_id not in self._connections:
            self._connections[task_id] = set()
        self._connections[task_id].add(websocket)
        log.debug("WS connected: task_id=%d, total=%d", task_id, len(self._connections[task_id]))

    def disconnect(self, task_id: int, websocket: WebSocket) -> None:
        """Remove a WebSocket from a task's connection set.

        Cleans up the set entirely if it becomes empty.
        """
        conns = self._connections.get(task_id)
        if conns is not None:
            conns.discard(websocket)
            if not conns:
                del self._connections[task_id]
        log.debug("WS disconnected: task_id=%d", task_id)

    async def send_chunk(self, task_id: int, text: str) -> None:
        """Broadcast a chunk message to all connected sockets for a task.

        Prunes sockets that raise on send.
        """
        await self._broadcast(task_id, {"type": "chunk", "data": text})

    async def send_status(self, task_id: int, status: str) -> None:
        """Broadcast a status message to all connected sockets for a task.

        Prunes sockets that raise on send.
        """
        await self._broadcast(task_id, {"type": "status", "data": status})

    def has_connections(self, task_id: int) -> bool:
        """Check if any WebSockets are connected for a task."""
        return bool(self._connections.get(task_id))

    async def _broadcast(self, task_id: int, message: dict[str, Any]) -> None:
        """Send a JSON message to all connected sockets, pruning dead ones."""
        conns = self._connections.get(task_id)
        if not conns:
            return

        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)

        for ws in dead:
            conns.discard(ws)
            log.debug("Pruned dead WS for task_id=%d", task_id)

        if not conns:
            del self._connections[task_id]
