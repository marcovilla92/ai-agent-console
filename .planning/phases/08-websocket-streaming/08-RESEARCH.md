# Phase 8: WebSocket Streaming - Research

**Researched:** 2026-03-12
**Domain:** FastAPI WebSocket, real-time streaming, connection management
**Confidence:** HIGH

## Summary

Phase 8 adds real-time WebSocket streaming so the browser receives Claude CLI output chunks as tasks execute. The existing `WebTaskContext.stream_output()` already iterates over `stream_claude()` text deltas but currently collects them silently (no-op for real-time push). The modification is straightforward: add a `ConnectionManager` that maps task IDs to connected WebSocket clients, wire it into `WebTaskContext` so each yielded chunk is also pushed to subscribers, and add a WebSocket endpoint at `/ws/tasks/{task_id}` with authentication and heartbeat.

FastAPI (via Starlette) has first-class WebSocket support including dependency injection, `WebSocketException` for auth rejection, and `WebSocketDisconnect` for cleanup. Uvicorn handles protocol-level ping/pong automatically (default 20s interval). The main work is: (1) a `ConnectionManager` class, (2) a WebSocket route with auth, (3) modifying `WebTaskContext` to broadcast chunks, and (4) application-level heartbeat to survive Traefik's idle timeout.

**Primary recommendation:** Use FastAPI's built-in WebSocket support with a `ConnectionManager` keyed by task_id. Authenticate via query parameter token (Basic auth credentials base64-encoded). Rely on uvicorn's protocol-level ping/pong plus an application-level heartbeat every 25s to keep Traefik happy.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| STRM-01 | User sees real-time Claude CLI output streamed via WebSocket during task execution | ConnectionManager + WebTaskContext chunk broadcasting + WebSocket endpoint pattern |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | (already installed) | WebSocket endpoint via `@app.websocket()` | Built-in Starlette WebSocket support, no extra deps |
| uvicorn | (already installed) | ASGI server with WebSocket ping/pong | Handles protocol-level keepalive automatically |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| websockets | (uvicorn dep) | WebSocket protocol implementation | Already installed as uvicorn dependency |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| WebSocket | Server-Sent Events (SSE) | SSE is simpler but uni-directional; WebSocket needed for future approval gate (Phase 9) bidirectional communication |
| Query param auth | Cookie auth | Cookies add complexity; query param with token is standard for WebSocket since browsers cannot set custom headers on WS upgrade |

**Installation:**
```bash
# No new packages needed -- FastAPI + uvicorn already provide WebSocket support
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── server/
│   ├── routers/
│   │   ├── tasks.py          # Existing REST endpoints
│   │   └── ws.py             # NEW: WebSocket endpoint
│   ├── connection_manager.py # NEW: ConnectionManager class
│   ├── dependencies.py       # Add WS auth dependency
│   └── app.py                # Wire ConnectionManager into lifespan
├── engine/
│   ├── context.py            # MODIFY: WebTaskContext broadcasts chunks
│   └── manager.py            # MODIFY: Pass ConnectionManager to WebTaskContext
```

### Pattern 1: ConnectionManager keyed by task_id
**What:** A class that tracks WebSocket connections per task_id, enabling targeted streaming to subscribers of a specific task.
**When to use:** When multiple clients may watch different tasks simultaneously.
**Example:**
```python
# Source: FastAPI official docs + project-specific adaptation
import asyncio
from fastapi import WebSocket

class ConnectionManager:
    """Manages WebSocket connections grouped by task_id."""

    def __init__(self):
        # task_id -> set of connected WebSockets
        self._connections: dict[int, set[WebSocket]] = {}

    async def connect(self, task_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(task_id, set()).add(websocket)

    def disconnect(self, task_id: int, websocket: WebSocket) -> None:
        if task_id in self._connections:
            self._connections[task_id].discard(websocket)
            if not self._connections[task_id]:
                del self._connections[task_id]

    async def send_chunk(self, task_id: int, text: str) -> None:
        """Send a text chunk to all clients watching a task."""
        conns = self._connections.get(task_id, set())
        dead = []
        for ws in conns:
            try:
                await ws.send_json({"type": "chunk", "data": text})
            except Exception:
                dead.append(ws)
        for ws in dead:
            conns.discard(ws)

    async def send_status(self, task_id: int, status: str) -> None:
        """Send a status update (e.g., 'completed', 'failed') to all watchers."""
        conns = self._connections.get(task_id, set())
        dead = []
        for ws in conns:
            try:
                await ws.send_json({"type": "status", "data": status})
            except Exception:
                dead.append(ws)
        for ws in dead:
            conns.discard(ws)

    def has_connections(self, task_id: int) -> bool:
        return bool(self._connections.get(task_id))
```

### Pattern 2: WebSocket Authentication via Query Parameter
**What:** Since browsers cannot set custom HTTP headers on WebSocket upgrade, pass credentials as a query parameter (base64-encoded Basic auth token).
**When to use:** Always -- this is the standard approach for WebSocket auth in browser clients.
**Example:**
```python
# Source: FastAPI official docs (WebSocket dependencies)
import base64
import secrets
from fastapi import WebSocket, WebSocketException, Query, status

async def verify_ws_token(
    websocket: WebSocket,
    token: str = Query(...),
) -> str:
    """Verify WebSocket auth token (base64 Basic auth credentials).

    Token format: base64("username:password") -- same creds as HTTP Basic Auth.
    Raises WebSocketException(1008) on failure.
    """
    try:
        decoded = base64.b64decode(token).decode("utf-8")
        username, password = decoded.split(":", 1)
    except Exception:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    settings = get_settings()
    username_ok = secrets.compare_digest(username.encode(), settings.auth_username.encode())
    password_ok = secrets.compare_digest(password.encode(), settings.auth_password.encode())
    if not (username_ok and password_ok):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    return username
```

### Pattern 3: Application-Level Heartbeat
**What:** Send periodic ping messages from server to client over the WebSocket to prevent Traefik proxy from closing idle connections.
**When to use:** Always in production behind a reverse proxy (Traefik default idle timeout is 60s).
**Example:**
```python
async def _heartbeat(websocket: WebSocket, interval: float = 25.0):
    """Send periodic pings to keep connection alive through proxies."""
    try:
        while True:
            await asyncio.sleep(interval)
            await websocket.send_json({"type": "ping"})
    except Exception:
        pass  # Connection closed, heartbeat stops naturally
```

### Pattern 4: WebSocket Endpoint Structure
**What:** The WebSocket route that ties auth, connection management, heartbeat, and message receive loop together.
**Example:**
```python
@ws_router.websocket("/ws/tasks/{task_id}")
async def task_stream(
    websocket: WebSocket,
    task_id: int,
    username: str = Depends(verify_ws_token),
):
    manager: ConnectionManager = websocket.app.state.connection_manager
    await manager.connect(task_id, websocket)
    heartbeat_task = asyncio.create_task(_heartbeat(websocket))
    try:
        while True:
            # Keep connection open, handle client messages (future: approval)
            msg = await websocket.receive_text()
            # For Phase 8: just acknowledge; Phase 9 will handle approvals
    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        manager.disconnect(task_id, websocket)
```

### Pattern 5: WebTaskContext Broadcasting
**What:** Modify the existing `stream_output()` method to push chunks to WebSocket subscribers alongside collecting them.
**Key insight:** The `ConnectionManager` must be passed into `WebTaskContext` so it can call `send_chunk()` for each text delta.
**Example:**
```python
# In WebTaskContext.stream_output():
async for event in stream_claude(prompt):
    if isinstance(event, str):
        raw_parts.append(event)
        # Push to WebSocket subscribers
        if self._connection_manager:
            await self._connection_manager.send_chunk(self._task_id, event)
    elif isinstance(event, dict):
        if "result" in event:
            raw_parts.append(str(event["result"]))
```

### Anti-Patterns to Avoid
- **Global ConnectionManager singleton:** Use `app.state.connection_manager` instead -- testable and lifecycle-managed
- **Blocking in broadcast loop:** Never await a slow operation inside the broadcast; dead connections should be pruned, not retried
- **Trusting protocol-level ping alone:** Uvicorn's ping/pong operates at the WebSocket protocol level (invisible to proxies); Traefik needs application-level traffic to keep the connection alive
- **HTTP Basic Auth header on WebSocket:** Browsers cannot set custom headers on WebSocket upgrade requests; must use query parameter

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| WebSocket protocol | Raw socket handling | FastAPI `@app.websocket()` | Handles upgrade, framing, close codes |
| Protocol keepalive | Custom ping/pong frames | Uvicorn `ws_ping_interval` (default 20s) | Already handled at server level |
| Connection state tracking | Ad-hoc dict per endpoint | Dedicated `ConnectionManager` class | Centralized cleanup, testable, reusable for Phase 9 |
| Auth token validation | Custom header parsing | FastAPI `Depends()` + `Query()` | Consistent with existing auth pattern |

**Key insight:** FastAPI/Starlette/uvicorn already handle the hard parts of WebSocket (upgrade negotiation, framing, protocol ping/pong). The application code only needs to manage connection grouping and message routing.

## Common Pitfalls

### Pitfall 1: Resource Leak on Disconnect
**What goes wrong:** WebSocket disconnects (network drop, tab close) leave stale entries in ConnectionManager
**Why it happens:** `WebSocketDisconnect` exception not caught, or finally block missing
**How to avoid:** Always use `try/except WebSocketDisconnect/finally` pattern; `disconnect()` in the finally block
**Warning signs:** Memory growth over time, send errors in logs

### Pitfall 2: Traefik Idle Timeout Kills WebSocket
**What goes wrong:** Long-running task produces output in bursts; during quiet periods Traefik closes the connection (default 60s idle timeout)
**Why it happens:** Protocol-level ping/pong (uvicorn) happens at TCP level -- Traefik may not see it as activity on the HTTP connection
**How to avoid:** Send application-level heartbeat JSON every 25s; optionally configure Traefik idle timeout higher via Coolify labels
**Warning signs:** WebSocket drops after ~60 seconds of no output

### Pitfall 3: Race Condition on Task Completion
**What goes wrong:** Task completes between client connecting to WebSocket and subscribing -- client misses all output
**Why it happens:** WebSocket connect is async; task may already be done
**How to avoid:** After connecting, check task status. If completed/failed, send final status immediately and close. If running, subscribe normally.
**Warning signs:** Client connects but never receives any data

### Pitfall 4: Sending to Closed WebSocket
**What goes wrong:** `send_json()` on a closed WebSocket raises exception, potentially breaking the broadcast loop
**Why it happens:** Client disconnected but `disconnect()` hasn't been called yet
**How to avoid:** Wrap `send_json()` in try/except within broadcast; collect dead connections and prune after iteration
**Warning signs:** Unhandled exceptions in broadcast, other clients stop receiving

### Pitfall 5: Blocking the Event Loop with Large Broadcasts
**What goes wrong:** If many clients connect, sequential `await send_json()` to each blocks other tasks
**Why it happens:** Each send is awaited in sequence
**How to avoid:** For this project (single-user, few connections) sequential is fine. If scaling needed, use `asyncio.gather()` with `return_exceptions=True`
**Warning signs:** Latency increase with more connections (unlikely for single-user)

## Code Examples

### JSON Message Protocol
```python
# Server -> Client message types:
{"type": "chunk", "data": "text content from Claude CLI"}
{"type": "status", "data": "running"}   # or "completed", "failed", "cancelled"
{"type": "ping"}                          # heartbeat keepalive

# Client -> Server (Phase 8: minimal; Phase 9: approvals)
# For now, client just keeps the connection open
```

### Client-Side WebSocket Connection (Alpine.js)
```javascript
// Browser client for Alpine.js dashboard (Phase 10 will use this)
const token = btoa("admin:changeme");  // Base64 Basic auth
const ws = new WebSocket(`wss://${location.host}/ws/tasks/${taskId}?token=${token}`);

ws.onmessage = function(event) {
    const msg = JSON.parse(event.data);
    if (msg.type === "chunk") {
        // Append text to output panel
        outputEl.textContent += msg.data;
    } else if (msg.type === "status") {
        // Update task status indicator
        statusEl.textContent = msg.data;
    } else if (msg.type === "ping") {
        // Heartbeat -- no action needed, keeps connection alive
    }
};

ws.onclose = function(event) {
    console.log("WebSocket closed:", event.code, event.reason);
    // Reconnect logic (Phase 10)
};
```

### Testing WebSocket with httpx
```python
# Source: FastAPI testing docs + project patterns
import asyncio
import base64
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

# httpx does NOT support WebSocket testing -- use Starlette TestClient
def test_ws_auth_rejected(app_with_pool):
    """WebSocket without valid token is rejected with 1008."""
    client = TestClient(app_with_pool)
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/tasks/1?token=invalid"):
            pass

def test_ws_receives_chunks(app_with_pool):
    """WebSocket receives chunk messages from a running task."""
    token = base64.b64encode(b"admin:changeme").decode()
    client = TestClient(app_with_pool)
    with client.websocket_connect(f"/ws/tasks/1?token={token}") as ws:
        # Trigger a chunk send via ConnectionManager
        # ... test implementation
        data = ws.receive_json()
        assert data["type"] == "chunk"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Polling REST endpoints | WebSocket push | Always been the standard for streaming | Real-time UX, no polling overhead |
| SSE (Server-Sent Events) | WebSocket | Both are current; WebSocket chosen for bidirectionality | Needed for Phase 9 approval gates |
| Custom ping frames | Uvicorn auto ping/pong + app heartbeat | Uvicorn added `ws_ping_interval` | Dual-layer keepalive |

**Deprecated/outdated:**
- Nothing deprecated in this domain; WebSocket support in FastAPI/Starlette is stable and mature

## Open Questions

1. **Traefik idle timeout configuration**
   - What we know: Default is 60s, configurable via Coolify labels
   - What's unclear: Whether uvicorn protocol-level pings are sufficient or if app-level heartbeat is strictly required
   - Recommendation: Implement app-level heartbeat (25s) as defense-in-depth; it's cheap and reliable

2. **Late-join replay (STRM-02)**
   - What we know: Deferred to v2.1 per REQUIREMENTS.md
   - What's unclear: N/A -- explicitly out of scope
   - Recommendation: Design ConnectionManager to be extensible (buffer could be added later) but do NOT implement buffering now

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | pyproject.toml (existing) |
| Quick run command | `python -m pytest tests/test_websocket.py -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STRM-01a | WebSocket endpoint accepts connection with valid auth | integration | `python -m pytest tests/test_websocket.py::test_ws_connect_with_auth -x` | No -- Wave 0 |
| STRM-01b | WebSocket rejects connection without valid auth | integration | `python -m pytest tests/test_websocket.py::test_ws_rejects_invalid_auth -x` | No -- Wave 0 |
| STRM-01c | Connected client receives text chunks during task execution | integration | `python -m pytest tests/test_websocket.py::test_ws_receives_chunks -x` | No -- Wave 0 |
| STRM-01d | Heartbeat ping sent periodically | unit | `python -m pytest tests/test_websocket.py::test_heartbeat_sends_ping -x` | No -- Wave 0 |
| STRM-01e | Disconnect does not crash server or leak resources | integration | `python -m pytest tests/test_websocket.py::test_disconnect_cleanup -x` | No -- Wave 0 |
| STRM-01f | ConnectionManager tracks/removes connections correctly | unit | `python -m pytest tests/test_websocket.py::test_connection_manager_lifecycle -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_websocket.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_websocket.py` -- covers STRM-01 (all sub-requirements)
- [ ] Starlette `TestClient` used for WebSocket testing (httpx AsyncClient does NOT support WebSocket)

## Sources

### Primary (HIGH confidence)
- [FastAPI WebSocket docs](https://fastapi.tiangolo.com/advanced/websockets/) - ConnectionManager pattern, auth with dependencies, WebSocketDisconnect handling
- [Uvicorn settings](https://uvicorn.dev/settings/) - ws_ping_interval, ws_ping_timeout defaults (both 20.0s)

### Secondary (MEDIUM confidence)
- [Coolify Gateway Timeout docs](https://coolify.io/docs/troubleshoot/applications/gateway-timeout) - Traefik timeout configuration via labels
- [Coolify Traefik dynamic config](https://coolify.io/docs/knowledge-base/proxy/traefik/dynamic-config) - Custom label-based config

### Tertiary (LOW confidence)
- [Coolify WebSocket issue #4002](https://github.com/coollabsio/coolify/issues/4002) - Reports of WebSocket issues with Traefik in Coolify (needs validation during Phase 11 Docker deployment)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - FastAPI WebSocket is built-in, well-documented, no new dependencies
- Architecture: HIGH - ConnectionManager is the official FastAPI pattern; codebase integration points are clear from existing code
- Pitfalls: HIGH - Traefik timeout and disconnect cleanup are well-documented issues with known solutions

**Research date:** 2026-03-12
**Valid until:** 2026-04-12 (stable domain, no fast-moving changes expected)
