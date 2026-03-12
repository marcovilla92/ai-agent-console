# Phase 7: Task Engine and API - Research

**Researched:** 2026-03-12
**Domain:** asyncio task management, FastAPI REST endpoints, HTTP Basic Auth, subprocess lifecycle
**Confidence:** HIGH

## Summary

Phase 7 builds the core task execution engine on top of the Phase 6 foundation (FastAPI app, asyncpg pool, TaskContext Protocol, orchestrator). The work splits into two clear layers: (1) a TaskManager service that owns task lifecycle, concurrency control via `asyncio.Semaphore(2)`, and subprocess cancellation, and (2) REST endpoints with HTTP Basic Auth that expose CRUD operations on tasks.

The existing codebase provides strong foundations. The `orchestrate_pipeline()` function already accepts a `TaskContext` and `asyncpg.Pool`, making it straightforward to wrap in a managed background task. The `stream_claude()` runner spawns `asyncio.subprocess.Process` objects that expose `.terminate()` and `.kill()` for cancellation. The database schema already has a `tasks` table but needs a `status` and `mode` column added.

**Primary recommendation:** Build a `TaskManager` class that holds an `asyncio.Semaphore(2)`, a dict of running task handles (`asyncio.Task` + subprocess PID), and methods for create/list/cancel. Each task creation inserts a DB row, fires an `asyncio.create_task()` that acquires the semaphore before calling `orchestrate_pipeline()`, and updates status on completion/failure/cancellation.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TASK-01 | User can cancel a running task with subprocess cleanup | Subprocess termination via SIGTERM->SIGKILL pattern; TaskManager tracks asyncio.Task + PID for each running task |
| TASK-02 | User can run up to 2 tasks concurrently | asyncio.Semaphore(2) gates execution; third task queues automatically |
| TASK-03 | User can choose supervised or autonomous mode per task | Mode field added to tasks table and POST request body; passed to orchestrator via TaskContext |
| INFR-02 | All endpoints require HTTP Basic Auth | FastAPI HTTPBasic dependency with secrets.compare_digest; applied globally or per-router |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.115+ | REST framework | Already in project from Phase 6 |
| asyncpg | 0.30+ | PostgreSQL driver | Already in project from Phase 6 |
| pydantic | 2.x | Request/response models | Ships with FastAPI, used for validation |
| pydantic-settings | 2.x | Config management | Already in project from Phase 6 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| httpx | 0.27+ | Async test client | Already used in test_server.py for ASGI transport testing |
| fastapi.security | (builtin) | HTTPBasic auth | For INFR-02 authentication requirement |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| asyncio.Semaphore | asyncio.Queue with workers | Queue is better for complex scheduling, but Semaphore is simpler and explicitly chosen in project decisions |
| HTTP Basic Auth | JWT/OAuth2 | Overkill for single-user; Basic Auth is a locked project decision |

**Installation:**
No new packages needed. FastAPI, asyncpg, pydantic, httpx already available.

## Architecture Patterns

### Recommended Project Structure
```
src/
  server/
    app.py           # (existing) add task_router inclusion
    config.py        # (existing) add AUTH_USERNAME, AUTH_PASSWORD settings
    dependencies.py  # (existing) add get_current_user auth dependency
    routers/
      tasks.py       # NEW: POST/GET/CANCEL endpoints
  engine/
    manager.py       # NEW: TaskManager service (semaphore, lifecycle, cancel)
    context.py       # NEW: WebTaskContext implementing TaskContext Protocol
```

### Pattern 1: TaskManager as App-State Singleton
**What:** A single TaskManager instance stored on `app.state.task_manager`, created during lifespan, holding the semaphore and task registry.
**When to use:** Always -- this is the core pattern for this phase.
**Example:**
```python
# In lifespan:
app.state.task_manager = TaskManager(pool=app.state.pool, max_concurrent=2)

# In endpoint dependency:
async def get_task_manager(request: Request) -> TaskManager:
    return request.app.state.task_manager
```

### Pattern 2: Background Task with Semaphore Gate
**What:** Each task submission creates an `asyncio.Task` that acquires the semaphore before executing. Tasks that cannot acquire immediately wait (queued state).
**When to use:** For the create-task flow.
**Example:**
```python
class TaskManager:
    def __init__(self, pool: asyncpg.Pool, max_concurrent: int = 2):
        self._pool = pool
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running: dict[int, RunningTask] = {}  # task_id -> RunningTask

    async def submit(self, task_id: int, prompt: str, mode: str) -> None:
        handle = asyncio.create_task(self._execute(task_id, prompt, mode))
        self._running[task_id] = RunningTask(handle=handle, task_id=task_id)

    async def _execute(self, task_id: int, prompt: str, mode: str) -> None:
        await self._update_status(task_id, "queued")
        async with self._semaphore:
            await self._update_status(task_id, "running")
            try:
                ctx = WebTaskContext(task_id=task_id, pool=self._pool, mode=mode)
                state = await orchestrate_pipeline(ctx, prompt, self._pool, task_id)
                status = "completed" if state.approved else "failed"
            except asyncio.CancelledError:
                status = "cancelled"
            except Exception:
                status = "failed"
            finally:
                await self._update_status(task_id, status)
                self._running.pop(task_id, None)
```

### Pattern 3: Subprocess Cancellation via Task.cancel()
**What:** Cancelling an `asyncio.Task` raises `CancelledError` inside the running coroutine, which propagates into `stream_claude()` during `async for raw_line in proc.stdout`. The subprocess must also be explicitly terminated.
**When to use:** For the cancel endpoint.
**Example:**
```python
async def cancel(self, task_id: int) -> bool:
    running = self._running.get(task_id)
    if not running:
        return False
    running.handle.cancel()
    # The CancelledError will propagate; but we also need to kill the subprocess
    # Store proc reference in WebTaskContext so we can terminate it
    if running.proc:
        running.proc.terminate()
        try:
            await asyncio.wait_for(running.proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            running.proc.kill()
    return True
```

### Pattern 4: HTTP Basic Auth as Global Dependency
**What:** Use FastAPI's `HTTPBasic` security scheme with `secrets.compare_digest()` for timing-safe comparison.
**When to use:** For INFR-02 -- all endpoints require auth (except /health which should remain open for monitoring).
**Example:**
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

security = HTTPBasic()

async def verify_credentials(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)]
) -> str:
    settings = get_settings()
    username_ok = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        settings.auth_username.encode("utf-8"),
    )
    password_ok = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        settings.auth_password.encode("utf-8"),
    )
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
```

### Pattern 5: WebTaskContext Implementing TaskContext Protocol
**What:** A class that satisfies the `TaskContext` Protocol for web-based task execution. In Phase 7, it stores output but does not stream to WebSocket (that is Phase 8). In supervised mode, it stores approval requests but auto-approves (approval UI is Phase 9).
**When to use:** For bridging the orchestrator to web execution.
**Example:**
```python
class WebTaskContext:
    def __init__(self, task_id: int, pool: asyncpg.Pool, mode: str, project_path: str = "."):
        self._task_id = task_id
        self._pool = pool
        self._mode = mode
        self._project_path = project_path

    @property
    def project_path(self) -> str:
        return self._project_path

    async def update_status(self, agent: str, state: str, step: str, next_action: str) -> None:
        pass  # Log only in Phase 7; WebSocket in Phase 8

    async def stream_output(self, agent_name: str, prompt: str, sections: dict) -> dict[str, str]:
        # Run agent, collect output, store in DB
        ...

    async def confirm_reroute(self, next_agent: str, reasoning: str) -> bool:
        return self._mode == "autonomous"  # Auto-confirm in autonomous mode

    async def handle_halt(self, iteration_count: int) -> str:
        return "approve"  # Auto-approve halts in web mode for now
```

### Anti-Patterns to Avoid
- **Spawning subprocess without tracking PID:** Every `asyncio.create_subprocess_exec` call must store the process reference so cancellation can terminate it. Without this, cancelled tasks leave orphan Claude CLI processes consuming RAM.
- **Using `asyncio.Task` without exception handling:** Uncaught exceptions in background tasks are silently swallowed. Always wrap `_execute` in try/except and update status to "failed".
- **Blocking the event loop with subprocess.run:** All subprocess calls must use `asyncio.create_subprocess_exec`, never `subprocess.run`.
- **Returning password in API responses:** Never include auth credentials in response bodies or logs.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP Basic Auth | Custom header parsing | `fastapi.security.HTTPBasic` | Handles 401 responses, WWW-Authenticate header, credential extraction |
| Timing-safe comparison | `==` for password check | `secrets.compare_digest()` | Prevents timing attacks |
| Request validation | Manual field checks | Pydantic `BaseModel` | Automatic 422 errors with field-level details |
| Concurrency limiting | Custom counter/lock | `asyncio.Semaphore` | Race-condition-free, well-tested primitive |
| JSON serialization | Manual dict building | Pydantic response models | Consistent, documented API schema |

**Key insight:** FastAPI + Pydantic handle 90% of the boilerplate (validation, serialization, error responses, OpenAPI docs). The custom logic is only in TaskManager lifecycle and subprocess tracking.

## Common Pitfalls

### Pitfall 1: Orphan Subprocesses on Cancellation
**What goes wrong:** `asyncio.Task.cancel()` raises `CancelledError` in the coroutine, but the Claude CLI subprocess keeps running because nobody called `proc.terminate()`.
**Why it happens:** `CancelledError` interrupts the Python coroutine but does not signal the OS-level subprocess.
**How to avoid:** Store the `asyncio.subprocess.Process` reference on the task handle. In the cancel method, call `proc.terminate()` then `proc.wait()` with timeout, escalating to `proc.kill()`.
**Warning signs:** After cancelling a task, `ps aux | grep claude` still shows running processes.

### Pitfall 2: Semaphore Leak on Exception
**What goes wrong:** If an exception occurs after `semaphore.acquire()` but before `semaphore.release()`, the semaphore counter is permanently decremented, reducing available slots.
**Why it happens:** Using manual `acquire()`/`release()` instead of `async with`.
**How to avoid:** Always use `async with self._semaphore:` which guarantees release even on exception or cancellation.
**Warning signs:** After a task failure, fewer than 2 concurrent tasks can run.

### Pitfall 3: Database Status Inconsistency
**What goes wrong:** Task status in DB says "running" but the asyncio.Task has already finished (crashed or cancelled).
**Why it happens:** Status update in the `finally` block fails (DB connection issue) or was never reached.
**How to avoid:** Use try/except/finally with the status update in `finally`. Consider a periodic cleanup that checks `self._running` against DB status.
**Warning signs:** `GET /tasks` shows tasks stuck in "running" status indefinitely.

### Pitfall 4: Auth Bypass on Health Endpoint
**What goes wrong:** Adding auth as a global dependency blocks monitoring tools from checking `/health`.
**Why it happens:** Global `app = FastAPI(dependencies=[Depends(verify_credentials)])` applies to all routes.
**How to avoid:** Apply auth to the task router only, not globally. Keep health_router without auth.
**Warning signs:** Monitoring/health checks start failing with 401.

### Pitfall 5: Missing Status Column in Tasks Table
**What goes wrong:** The current `tasks` table has no `status` or `mode` column.
**Why it happens:** Phase 6 schema was minimal (name, project_path, created_at).
**How to avoid:** Add `status TEXT NOT NULL DEFAULT 'queued'` and `mode TEXT NOT NULL DEFAULT 'autonomous'` columns via ALTER TABLE in migration.
**Warning signs:** Cannot filter tasks by status or store mode selection.

## Code Examples

### Database Schema Migration (add status and mode columns)
```python
# Added to PG_SCHEMA_SQL or as migration step
ALTER_TASKS_SQL = """
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'queued';
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'autonomous';
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS prompt TEXT NOT NULL DEFAULT '';
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS error TEXT;
"""
```

### Pydantic Request/Response Models
```python
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class TaskCreate(BaseModel):
    prompt: str
    mode: str = "autonomous"  # "autonomous" or "supervised"

class TaskResponse(BaseModel):
    id: int
    name: str
    prompt: str
    status: str  # queued/running/awaiting_approval/completed/failed/cancelled
    mode: str
    project_path: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]
    count: int
```

### REST Endpoint Structure
```python
task_router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(verify_credentials)])

@task_router.post("", status_code=201, response_model=TaskResponse)
async def create_task(body: TaskCreate, manager: TaskManager = Depends(get_task_manager)):
    task = await manager.create(prompt=body.prompt, mode=body.mode)
    return task

@task_router.get("", response_model=TaskListResponse)
async def list_tasks(manager: TaskManager = Depends(get_task_manager)):
    tasks = await manager.list_all()
    return TaskListResponse(tasks=tasks, count=len(tasks))

@task_router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, manager: TaskManager = Depends(get_task_manager)):
    task = await manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@task_router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(task_id: int, manager: TaskManager = Depends(get_task_manager)):
    task = await manager.cancel(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Celery/Redis task queue | asyncio.Semaphore for small scale | N/A | Project decision: no message broker needed for 2-task concurrency |
| JWT/OAuth2 | HTTP Basic Auth | N/A | Project decision: single-user simplicity |
| subprocess.run (blocking) | asyncio.create_subprocess_exec | Python 3.5+ | Non-blocking subprocess management |

**Deprecated/outdated:**
- None relevant -- the stack choices are modern and appropriate for the scale.

## Open Questions

1. **Project path for tasks**
   - What we know: Tasks need a `project_path` for the orchestrator. The current schema has it.
   - What's unclear: Should the API accept a project_path per task, or use a server-wide default?
   - Recommendation: Use a server-wide default from Settings (`APP_PROJECT_PATH`), since this is a single-project deployment.

2. **Task naming**
   - What we know: The `name` column exists in tasks table.
   - What's unclear: Should the name be auto-generated from the prompt or user-supplied?
   - Recommendation: Auto-generate from first 50 chars of prompt, truncated. Keep it simple.

3. **WebTaskContext.stream_output implementation**
   - What we know: The orchestrator calls `ctx.stream_output()` which must run an agent and return sections.
   - What's unclear: The existing TUI streaming code in `src/tui/streaming.py` handles section parsing.
   - Recommendation: Reuse the parsing logic from `src/parser/extractor.py` and the runner from `src/runner/runner.py`. WebTaskContext collects output chunks and parses sections.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio 0.23+ |
| Config file | pyproject.toml `[project.optional-dependencies] dev` |
| Quick run command | `python -m pytest tests/test_task_manager.py tests/test_task_endpoints.py -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TASK-01 | Cancel running task, subprocess terminated | unit + integration | `python -m pytest tests/test_task_manager.py::test_cancel_task -x` | No -- Wave 0 |
| TASK-02 | 2 concurrent, 3rd queues | unit | `python -m pytest tests/test_task_manager.py::test_semaphore_concurrency -x` | No -- Wave 0 |
| TASK-03 | Mode selection (supervised/autonomous) | unit | `python -m pytest tests/test_task_manager.py::test_mode_selection -x` | No -- Wave 0 |
| INFR-02 | 401 on unauthenticated requests | integration | `python -m pytest tests/test_task_endpoints.py::test_auth_required -x` | No -- Wave 0 |
| TASK-01 | Cancel via REST endpoint | integration | `python -m pytest tests/test_task_endpoints.py::test_cancel_endpoint -x` | No -- Wave 0 |
| TASK-02 | POST creates task, GET lists tasks | integration | `python -m pytest tests/test_task_endpoints.py::test_create_and_list -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_task_manager.py tests/test_task_endpoints.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_task_manager.py` -- covers TASK-01, TASK-02, TASK-03 (unit tests with mocked orchestrator)
- [ ] `tests/test_task_endpoints.py` -- covers INFR-02, TASK-01 cancel endpoint, TASK-02 create/list (integration tests with ASGI transport)
- [ ] Schema migration test for new columns (status, mode, prompt)

## Sources

### Primary (HIGH confidence)
- Existing codebase: `src/server/app.py`, `src/pipeline/protocol.py`, `src/pipeline/orchestrator.py`, `src/runner/runner.py`, `src/db/pg_schema.py`, `src/db/pg_repository.py`
- [FastAPI HTTP Basic Auth docs](https://fastapi.tiangolo.com/advanced/security/http-basic-auth/)
- [Python asyncio-sync docs (Semaphore)](https://docs.python.org/3/library/asyncio-sync.html)
- [Python asyncio-subprocess docs](https://docs.python.org/3/library/asyncio-subprocess.html)

### Secondary (MEDIUM confidence)
- [Limiting concurrency with semaphore](https://rednafi.com/python/limit-concurrency-with-semaphore/) -- verified patterns match stdlib docs
- [Asyncio subprocess termination patterns](https://runebook.dev/en/docs/python/library/asyncio-subprocess/asyncio.subprocess.Process.terminate)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in project, no new dependencies
- Architecture: HIGH -- patterns directly follow from existing code structure and project decisions
- Pitfalls: HIGH -- well-documented asyncio patterns, verified against stdlib docs

**Research date:** 2026-03-12
**Valid until:** 2026-04-12 (stable stack, no fast-moving dependencies)
