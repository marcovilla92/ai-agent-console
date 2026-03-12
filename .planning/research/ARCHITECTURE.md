# Architecture Research

**Domain:** Web platform for AI agent orchestration (TUI-to-web migration)
**Researched:** 2026-03-12
**Confidence:** HIGH

## System Overview

```
                         Browser (Alpine.js + Pico CSS)
                    +-----------------------------------------+
                    |  Dashboard    Task Detail    Logs        |
                    |  [REST]       [WebSocket]   [REST]      |
                    +------+----------+----------+------------+
                           |          |          |
===========================|==========|==========|================
                    FastAPI Server    |          |
                    +------+----------+----------+------------+
                    |          HTTP / WS Router                |
                    |  +----------+  +----------------+       |
                    |  | REST API |  | WS Endpoint    |       |
                    |  | /tasks   |  | /ws/task/{id}  |       |
                    |  +----+-----+  +------+---------+       |
                    |       |               |                  |
                    |  +----+---------------+----------+      |
                    |  |       TaskManager              |      |
                    |  |  (asyncio.Semaphore(2))        |      |
                    |  |  task registry + lifecycle     |      |
                    |  +----+--------------+-----------+      |
                    |       |              |                   |
                    |  +----+----+  +------+----------+       |
                    |  |Approval |  | Connection      |       |
                    |  |Gate     |  | Manager         |       |
                    |  |(Event)  |  | (broadcast)     |       |
                    |  +----+----+  +------+----------+       |
                    |       |              |                   |
                    +-------+--------------+-------------------+
                            |              |
============================|==============|=======================
              Reused Core   |              |
                    +-------+--------------+------------------+
                    |  orchestrator.py  (modified)              |
                    |  stream_claude()  (unchanged)             |
                    |  agents/          (unchanged)             |
                    |  parser/          (unchanged)             |
                    |  context/         (unchanged)             |
                    |  pipeline/        (unchanged)             |
                    +------------------+------------------------+
                                       |
=======================================|==========================
              Data Layer               |
                    +------------------+------------------------+
                    |  asyncpg pool  ->  PostgreSQL 16          |
                    |  (Coolify-managed instance)                |
                    +-------------------------------------------+
```

### Component Responsibilities

| Component | Responsibility | New or Modified |
|-----------|----------------|-----------------|
| **FastAPI app** | HTTP server, lifespan, dependency injection | NEW |
| **REST API routes** | CRUD for tasks, list sessions, usage stats | NEW |
| **WebSocket endpoint** | Per-task streaming + late-join replay | NEW |
| **TaskManager** | Task lifecycle, concurrency control, asyncio.Semaphore(2) | NEW |
| **ApprovalGate** | Pause pipeline at approval points via asyncio.Event | NEW |
| **ConnectionManager** | Track WebSocket connections per task, broadcast chunks | NEW |
| **orchestrator.py** | Route agents through pipeline (decoupled from TUI) | MODIFIED |
| **stream_claude()** | Launch Claude CLI subprocess, yield chunks/results | UNCHANGED |
| **agents/** | Config registry, factory, base agent class | UNCHANGED |
| **parser/** | Section extraction from agent output | UNCHANGED |
| **context/** | Workspace context assembly | UNCHANGED |
| **db/schema.py** | Table definitions (migrated to PostgreSQL DDL) | MODIFIED |
| **db/repository.py** | Data access (rewritten for asyncpg) | MODIFIED |

## Recommended Project Structure

```
src/
+-- agents/                 # UNCHANGED - agent config, factory, base
|   +-- config.py
|   +-- factory.py
|   +-- base.py
|   +-- prompts/
+-- runner/                 # UNCHANGED - Claude CLI subprocess
|   +-- runner.py           # stream_claude(), call_orchestrator_claude()
|   +-- retry.py
+-- parser/                 # UNCHANGED - section extraction
|   +-- extractor.py
+-- context/                # UNCHANGED - workspace context
|   +-- assembler.py
+-- pipeline/               # MODIFIED - decouple from TUI
|   +-- orchestrator.py     # Remove AgentConsoleApp dependency
|   +-- handoff.py
|   +-- runner.py
|   +-- project.py
+-- git/                    # UNCHANGED - auto-commit
|   +-- autocommit.py
+-- db/                     # REWRITTEN - asyncpg instead of aiosqlite
|   +-- schema.py           # PostgreSQL DDL + Pydantic models
|   +-- repository.py       # asyncpg queries (parameterized $1, $2)
|   +-- pool.py             # Connection pool lifecycle
+-- web/                    # NEW - entire web layer
|   +-- app.py              # FastAPI app factory + lifespan
|   +-- routes/
|   |   +-- tasks.py        # POST /tasks, GET /tasks, GET /tasks/{id}
|   |   +-- sessions.py     # GET /sessions, GET /sessions/{id}
|   |   +-- health.py       # GET /health
|   +-- ws/
|   |   +-- streaming.py    # WebSocket /ws/task/{id}
|   +-- services/
|   |   +-- task_manager.py # TaskManager class
|   |   +-- approval.py     # ApprovalGate class
|   |   +-- connection.py   # ConnectionManager class
|   +-- models.py           # Pydantic request/response models
|   +-- auth.py             # HTTP Basic Auth dependency
+-- static/                 # NEW - Alpine.js frontend
|   +-- index.html
|   +-- task.html
|   +-- app.js              # Alpine.js components
|   +-- style.css           # Pico CSS overrides
+-- __main__.py             # NEW - uvicorn entry point
```

### Structure Rationale

- **agents/, runner/, parser/, context/ unchanged:** These modules have zero TUI coupling. `stream_claude()` yields `str | dict` -- the consumer changes from TUI panel to WebSocket broadcast, but the producer stays identical.
- **pipeline/ modified minimally:** The orchestrator currently takes `AgentConsoleApp` as first argument. It needs to accept a callback interface instead, so both TUI and web can drive it. In practice, replace `app: AgentConsoleApp` with a `TaskContext` protocol.
- **db/ rewritten:** aiosqlite uses `?` placeholders and `cursor.lastrowid`. asyncpg uses `$1` placeholders and `RETURNING id`. The repository interface stays the same, but internals change completely.
- **web/ is the new layer:** All new components live here. Clean separation from reusable core.

## Architectural Patterns

### Pattern 1: TaskContext Protocol (Decoupling Orchestrator from UI)

**What:** Define a Protocol that the orchestrator calls for UI actions (stream chunk, request approval, update status). The web layer implements it.
**When to use:** When the same business logic needs to drive different UIs.
**Trade-offs:** Slight indirection, but eliminates the `from src.tui.app import AgentConsoleApp` coupling that currently makes the orchestrator untestable without Textual.

**Example:**
```python
from typing import Protocol

class TaskContext(Protocol):
    """Interface the orchestrator uses to communicate with the UI layer."""

    async def stream_chunk(self, agent: str, chunk: str) -> None:
        """Send a text chunk to the user."""
        ...

    async def request_approval(self, agent: str, reasoning: str) -> bool:
        """Pause and wait for user approval. Returns True if approved."""
        ...

    async def update_status(self, agent: str, state: str, detail: str) -> None:
        """Update task status display."""
        ...


class WebTaskContext:
    """Web implementation -- broadcasts via ConnectionManager."""

    def __init__(self, task_id: int, conn_mgr: "ConnectionManager", gate: "ApprovalGate"):
        self._task_id = task_id
        self._conn_mgr = conn_mgr
        self._gate = gate

    async def stream_chunk(self, agent: str, chunk: str) -> None:
        await self._conn_mgr.broadcast(self._task_id, {
            "type": "chunk", "agent": agent, "text": chunk
        })

    async def request_approval(self, agent: str, reasoning: str) -> bool:
        await self._conn_mgr.broadcast(self._task_id, {
            "type": "approval_required", "agent": agent, "reasoning": reasoning
        })
        return await self._gate.wait_for_approval(self._task_id)

    async def update_status(self, agent: str, state: str, detail: str) -> None:
        await self._conn_mgr.broadcast(self._task_id, {
            "type": "status", "agent": agent, "state": state, "detail": detail
        })
```

### Pattern 2: TaskManager with Semaphore Concurrency

**What:** A singleton that manages task lifecycle (create, run, cancel) with `asyncio.Semaphore(2)` limiting concurrent Claude CLI processes.
**When to use:** When multiple tasks can be queued but only N should run simultaneously.
**Trade-offs:** Simple and correct for single-process. Would need Redis/queue for multi-worker, but PROJECT.md explicitly rules that out.

**Example:**
```python
import asyncio
from enum import Enum

class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskManager:
    def __init__(self, max_concurrent: int = 2):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._tasks: dict[int, asyncio.Task] = {}  # task_id -> asyncio.Task
        self._statuses: dict[int, TaskStatus] = {}

    async def submit(self, task_id: int, coro) -> None:
        """Queue a task. It runs when a semaphore slot opens."""
        self._statuses[task_id] = TaskStatus.QUEUED

        async def _wrapped():
            async with self._semaphore:
                self._statuses[task_id] = TaskStatus.RUNNING
                try:
                    await coro
                    self._statuses[task_id] = TaskStatus.COMPLETED
                except asyncio.CancelledError:
                    self._statuses[task_id] = TaskStatus.CANCELLED
                except Exception:
                    self._statuses[task_id] = TaskStatus.FAILED
                    raise

        self._tasks[task_id] = asyncio.create_task(_wrapped())

    async def cancel(self, task_id: int) -> None:
        task = self._tasks.get(task_id)
        if task and not task.done():
            task.cancel()
```

### Pattern 3: ApprovalGate with asyncio.Event

**What:** Per-task Event objects that pause the orchestrator pipeline until the user sends an HTTP POST to approve/reject.
**When to use:** Supervised mode where each agent transition requires human approval.
**Trade-offs:** Elegant and zero-polling. The Event lives in memory, so if the server restarts mid-approval, the task is lost. Acceptable for single-user single-process.

**Example:**
```python
import asyncio

class ApprovalGate:
    def __init__(self):
        self._gates: dict[int, asyncio.Event] = {}
        self._results: dict[int, bool] = {}

    async def wait_for_approval(self, task_id: int) -> bool:
        """Block the pipeline coroutine until user approves or rejects."""
        event = asyncio.Event()
        self._gates[task_id] = event
        await event.wait()
        result = self._results.pop(task_id, False)
        del self._gates[task_id]
        return result

    def approve(self, task_id: int) -> None:
        """Called by REST endpoint POST /tasks/{id}/approve."""
        self._results[task_id] = True
        if task_id in self._gates:
            self._gates[task_id].set()

    def reject(self, task_id: int) -> None:
        """Called by REST endpoint POST /tasks/{id}/reject."""
        self._results[task_id] = False
        if task_id in self._gates:
            self._gates[task_id].set()
```

### Pattern 4: ConnectionManager with Late-Join Replay

**What:** Track WebSocket connections per task_id. Buffer recent chunks so late-joining clients see context.
**When to use:** When users open task detail page while a task is already streaming.
**Trade-offs:** Memory usage for replay buffer. Cap at 500 chunks per task (roughly last ~50KB of output). Chunks are cheap (small text deltas).

**Example:**
```python
import asyncio
import json
from collections import defaultdict, deque
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self, replay_limit: int = 500):
        self._connections: dict[int, list[WebSocket]] = defaultdict(list)
        self._replay: dict[int, deque] = defaultdict(
            lambda: deque(maxlen=replay_limit)
        )
        self._lock = asyncio.Lock()

    async def connect(self, task_id: int, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[task_id].append(ws)
            # Replay buffered chunks to late-joiner
            for msg in self._replay[task_id]:
                await ws.send_text(msg)

    async def disconnect(self, task_id: int, ws: WebSocket) -> None:
        async with self._lock:
            self._connections[task_id].remove(ws)

    async def broadcast(self, task_id: int, data: dict) -> None:
        msg = json.dumps(data)
        async with self._lock:
            self._replay[task_id].append(msg)
            dead = []
            for ws in self._connections[task_id]:
                try:
                    await ws.send_text(msg)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._connections[task_id].remove(ws)
```

### Pattern 5: Lifespan-Managed asyncpg Pool

**What:** Create asyncpg connection pool in FastAPI lifespan, store on `app.state`, close on shutdown.
**When to use:** Always with asyncpg + FastAPI.
**Trade-offs:** None -- this is the standard pattern. Avoids connection leaks.

**Example:**
```python
from contextlib import asynccontextmanager
import asyncpg
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.db_pool = await asyncpg.create_pool(
        dsn="postgresql://user:pass@host:5432/dbname",
        min_size=2,
        max_size=5,
    )
    app.state.task_manager = TaskManager(max_concurrent=2)
    app.state.conn_manager = ConnectionManager()
    app.state.approval_gate = ApprovalGate()

    yield

    # Shutdown
    await app.state.db_pool.close()

app = FastAPI(lifespan=lifespan)
```

## Data Flow

### Task Creation and Execution Flow

```
Browser                FastAPI             TaskManager      Orchestrator     Claude CLI
  |                      |                     |                |               |
  +--POST /tasks-------->|                     |                |               |
  |  {prompt, mode}      +--create in DB------>|                |               |
  |<--201 {task_id}------|                     |                |               |
  |                      |                     |                |               |
  +--WS /ws/task/{id}--->| (late-join replay)  |                |               |
  |                      |                     |                |               |
  |                      +--submit(id, coro)-->|                |               |
  |                      |                     +--sem.acquire-->|               |
  |                      |                     |                +--stream_claude>|
  |                      |                     |                |<--text chunk---|
  |                      |                     |                |               |
  |<-WS {"type":"chunk"}-|<---broadcast--------|<-stream_chunk()|               |
  |                      |                     |                |               |
  | (repeat for all chunks)                    |                |               |
  |                      |                     |                |               |
  |<-WS {"type":"approval_required"}-----------<-request_approval               |
  |                      |                     |   (Event.wait) |               |
  |                      |                     |                |               |
  +--POST /tasks/{id}/approve-->|              |                |               |
  |                      +--gate.approve(id)-->|                |               |
  |                      |                     +--Event.set()--->|               |
  |                      |                     |                +--next agent--->|
```

### Key Data Flows

1. **Stream chunk path:** `stream_claude() yield` -> `orchestrator` -> `TaskContext.stream_chunk()` -> `ConnectionManager.broadcast()` -> WebSocket -> Browser. This is the hot path. Each yield from the async generator becomes a WebSocket message within milliseconds.

2. **Approval gate path:** Orchestrator calls `TaskContext.request_approval()` -> broadcasts `approval_required` message to browser -> browser shows approve/reject buttons -> user clicks -> `POST /tasks/{id}/approve` -> `ApprovalGate.approve()` sets Event -> orchestrator resumes. Zero polling. The coroutine is suspended at `await event.wait()`.

3. **Late-join replay:** Browser opens `WS /ws/task/{id}` while task is running -> `ConnectionManager.connect()` sends buffered chunks -> browser renders existing output -> future chunks arrive in real-time.

4. **Database persistence:** Same as v1.0 but async. `orchestrator` -> `repository.create()` -> `asyncpg pool.acquire()` -> PostgreSQL. Runs after each agent completes, not on every chunk (chunks are transient, buffered in ConnectionManager).

## Integration Points: Existing Code Changes

### What Changes

| Module | Change | Why |
|--------|--------|-----|
| `pipeline/orchestrator.py` | Replace `app: AgentConsoleApp` param with `ctx: TaskContext` | Decouple from Textual |
| `pipeline/orchestrator.py` | Replace `show_reroute_confirmation()` with `ctx.request_approval()` | Use approval gate instead of TUI modal |
| `pipeline/orchestrator.py` | Replace `stream_agent_to_panel()` with new `stream_agent()` that calls `ctx.stream_chunk()` | Route output to WebSocket instead of TUI panel |
| `pipeline/orchestrator.py` | Replace `app.status_bar.set_status()` with `ctx.update_status()` | Abstract status updates |
| `db/schema.py` | Replace SQLite DDL with PostgreSQL DDL, add `tasks` table, add `status` column | PostgreSQL types (SERIAL, TIMESTAMPTZ, TEXT) |
| `db/repository.py` | Rewrite from aiosqlite to asyncpg | Different API: `$1` params, `fetchrow()`, `RETURNING id` |
| `agents/base.py` | Change `db: aiosqlite.Connection` to `db: asyncpg.Pool` | Pool-based connection management |

### What Does NOT Change

| Module | Why Unchanged |
|--------|---------------|
| `runner/runner.py` | `stream_claude()` is already a clean async generator. No TUI coupling. |
| `runner/retry.py` | Retry logic is transport-agnostic. |
| `parser/extractor.py` | Pure function: string in, dict out. |
| `context/assembler.py` | Pure function: path in, string out. |
| `agents/config.py` | Declarative registry. No I/O coupling. |
| `agents/factory.py` | Factory pattern. DB type changes but factory signature stays. |
| `pipeline/handoff.py` | Pure function: AgentResult in, string out. |
| `git/autocommit.py` | Subprocess call. No TUI coupling. |

## New PostgreSQL Schema

```sql
-- tasks table (new -- replaces in-memory task tracking)
CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    prompt TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'supervised',  -- 'supervised' | 'autonomous'
    status TEXT NOT NULL DEFAULT 'queued',
    project_path TEXT NOT NULL,
    current_agent TEXT,
    iteration_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- v1.0 "sessions" concept merges into "tasks" for v2.0.
-- A task IS a session. One table instead of two.

-- agent_outputs (same structure, PostgreSQL types)
CREATE TABLE agent_outputs (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    agent_type TEXT NOT NULL,
    raw_output TEXT NOT NULL,
    sections JSONB,  -- NEW: parsed sections stored for queryability
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- agent_usage (same structure)
CREATE TABLE agent_usage (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    agent_type TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd NUMERIC(10,6) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- orchestrator_decisions (same structure)
CREATE TABLE orchestrator_decisions (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    next_agent TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    confidence NUMERIC(3,2),
    full_response TEXT NOT NULL,
    iteration_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- indexes
CREATE INDEX idx_agent_outputs_task ON agent_outputs(task_id);
CREATE INDEX idx_agent_usage_task ON agent_usage(task_id);
CREATE INDEX idx_orchestrator_decisions_task ON orchestrator_decisions(task_id);
CREATE INDEX idx_tasks_status ON tasks(status);
```

## Docker Container Architecture

### Dockerfile Strategy

Use `python:3.12-slim` as base, install Node.js 20 for Claude CLI. Do NOT use Alpine -- native npm packages cause compatibility issues.

```dockerfile
FROM python:3.12-slim

# Install Node.js 20 for Claude CLI
RUN apt-get update && apt-get install -y curl git && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g @anthropic-ai/claude-code && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY static/ static/

# Claude CLI needs a home directory for config
ENV HOME=/app
# ANTHROPIC_API_KEY injected at runtime via Coolify env var

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "src.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Key Docker Considerations

| Concern | Approach |
|---------|----------|
| Claude CLI auth | `ANTHROPIC_API_KEY` env var set in Coolify dashboard, passed to container at runtime |
| Workspace volumes | Mount `/workspaces` volume for cloned repos. Claude CLI operates inside these directories. |
| Claude CLI subprocess | `stream_claude()` uses `asyncio.create_subprocess_exec` -- works identically in container |
| Node.js in Python image | ~150MB overhead but necessary. Claude CLI is a Node.js package. |
| `--dangerously-skip-permissions` | Already set in `stream_claude()`. Required for non-interactive container execution. |
| Image size | ~500MB total. Acceptable for VPS deployment. |

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1 user, 1-3 tasks | Current design. Single process, asyncio semaphore, in-memory ConnectionManager. |
| 1 user, 10+ tasks | Add task queue persistence (tasks table with status=queued survives restarts). |
| Multi-user (future) | Add Redis for pub/sub (ConnectionManager), proper auth (JWT), task isolation. OUT OF SCOPE per PROJECT.md. |

### Scaling Priorities

1. **First bottleneck: RAM.** Each Claude CLI subprocess uses ~200-400MB. Semaphore(2) caps at ~800MB for CLI processes + ~200MB for Python + asyncpg. Fits within VPS 5GB margin.
2. **Second bottleneck: Claude CLI cold start.** Each subprocess takes 2-5 seconds to initialize. No mitigation possible -- CLI design limitation. Pipeline has 3-6 agent calls, so 6-30 seconds of overhead per task.

## Anti-Patterns

### Anti-Pattern 1: Blocking the Event Loop with Subprocess

**What people do:** Use `subprocess.run()` or `os.popen()` to call Claude CLI.
**Why it's wrong:** Blocks the entire asyncio event loop. No concurrent tasks, no WebSocket heartbeats, no HTTP responses while CLI runs.
**Do this instead:** Use `asyncio.create_subprocess_exec()` exactly as `stream_claude()` already does. This is already correct in the codebase.

### Anti-Pattern 2: Database Connection Per Request

**What people do:** `asyncpg.connect()` in every route handler.
**Why it's wrong:** Connection overhead (TCP handshake, auth) on every request. Connection leak if not closed properly.
**Do this instead:** Use `asyncpg.create_pool()` in lifespan, `pool.acquire()` in handlers. Pool manages lifecycle.

### Anti-Pattern 3: Storing Stream Chunks in Database

**What people do:** INSERT every text chunk from `stream_claude()` into the database for replay.
**Why it's wrong:** Thousands of INSERT operations per agent run. Destroys performance. Pointless -- chunks are reconstructed from `raw_output`.
**Do this instead:** Buffer chunks in ConnectionManager memory for live replay. Store final `raw_output` once per agent in `agent_outputs` table. Late-join replay uses in-memory buffer; historical replay reconstructs from stored output.

### Anti-Pattern 4: Tight Coupling Between Orchestrator and Web Layer

**What people do:** Import FastAPI Request/WebSocket directly in orchestrator.
**Why it's wrong:** Makes orchestrator untestable, kills reusability.
**Do this instead:** Use the TaskContext Protocol pattern. Orchestrator calls abstract methods. Web layer provides concrete implementation.

### Anti-Pattern 5: Polling for Approval Status

**What people do:** Browser polls `GET /tasks/{id}/status` every second to check if approval is needed.
**Why it's wrong:** Unnecessary load, latency, wasted requests.
**Do this instead:** Push `approval_required` event over WebSocket. Browser shows buttons immediately. User clicks, `POST /tasks/{id}/approve` fires once. Zero polling.

## Suggested Build Order

Build order follows dependency graph -- each phase uses only components from previous phases.

| Phase | Component | Depends On | Rationale |
|-------|-----------|------------|-----------|
| 1 | PostgreSQL schema + asyncpg pool + repository rewrite | Nothing | Foundation. Everything else needs the database. |
| 2 | FastAPI app shell + lifespan + health endpoint | Phase 1 | Verify the server boots, pool connects, Coolify deploys. |
| 3 | TaskContext Protocol + orchestrator refactor | Phase 1 | Decouple orchestrator from TUI. Unit-testable without web server. |
| 4 | TaskManager + REST endpoints (POST/GET /tasks) | Phases 1, 2, 3 | Tasks can be created and queued. Pipeline runs in background. |
| 5 | ConnectionManager + WebSocket endpoint | Phases 2, 4 | Stream chunks to browser in real-time. |
| 6 | ApprovalGate + supervised mode | Phases 3, 4, 5 | Pause/resume pipeline from browser. |
| 7 | Alpine.js frontend | Phases 4, 5, 6 | All backend APIs exist. Build UI against them. |
| 8 | Docker + Coolify deployment | Phases 1-7 | Everything works locally, now containerize. |

**Phase ordering rationale:**
- Database first because repository rewrite touches agents/base.py (db parameter type change).
- Orchestrator refactor before TaskManager because TaskManager calls the orchestrator.
- WebSocket before ApprovalGate because approval events are delivered via WebSocket.
- Frontend last because it consumes all APIs. Building it earlier means constant rework as APIs evolve.
- Docker last because it is packaging, not architecture. Develop locally, containerize once stable.

## Sources

- [FastAPI WebSockets documentation](https://fastapi.tiangolo.com/advanced/websockets/)
- [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- [FastAPI asyncpg lifespan pattern discussion](https://github.com/fastapi/fastapi/discussions/9520)
- [Using asyncpg with FastAPI](https://daniel.feldroy.com/posts/2025-10-using-asyncpg-with-fastapi-and-air)
- [FastAPI without ORM: asyncpg](https://www.sheshbabu.com/posts/fastapi-without-orm-getting-started-with-asyncpg/)
- [Managing Multiple WebSocket Clients in FastAPI](https://hexshift.medium.com/managing-multiple-websocket-clients-in-fastapi-ce5b134568a2)
- [Running Claude Code in Docker Containers](https://medium.com/rigel-computer-com/running-claude-code-in-docker-containers-one-project-one-container-1601042bf49c)
- [Claude Code Development Containers](https://code.claude.com/docs/en/devcontainer)
- [Async Database Patterns for AI Systems](https://dasroot.net/posts/2026/03/async-database-access-patterns-ai-systems/)

---
*Architecture research for: AI Agent Console v2.0 Web Platform*
*Researched: 2026-03-12*
