# Phase 6: Database and Server Foundation - Research

**Researched:** 2026-03-12
**Domain:** PostgreSQL persistence (asyncpg), FastAPI server bootstrap, orchestrator decoupling via Protocol
**Confidence:** HIGH

## Summary

Phase 6 transitions the application from an aiosqlite-backed TUI to a FastAPI server backed by PostgreSQL via asyncpg. The existing codebase already has a clean repository pattern with four tables (sessions, agent_outputs, agent_usage, orchestrator_decisions) -- these map directly to PostgreSQL with minor SQL dialect changes. The orchestrator currently takes `AgentConsoleApp` (Textual) as its first argument throughout `orchestrate_pipeline`, `show_reroute_confirmation`, and `show_halt_dialog`. A `TaskContext` Protocol will abstract this dependency so any frontend (web, TUI, test harness) can drive orchestration.

The project already runs PostgreSQL 16 on the VPS (container `ihhyb2rjq8jsx0ltbn1btj5a`), so no database provisioning is needed -- only schema creation and connection configuration.

**Primary recommendation:** Replace aiosqlite with asyncpg using the same repository-per-table pattern, managed by a lifespan-scoped connection pool on the FastAPI app. Decouple the orchestrator by defining a `TaskContext` Protocol with the methods the orchestrator actually calls on `AgentConsoleApp`.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFR-01 | Task data persists in PostgreSQL (tasks, outputs, usage, decisions) | asyncpg repository layer replaces aiosqlite repos; same 4 tables with PostgreSQL-native types (SERIAL, TIMESTAMPTZ, DOUBLE PRECISION); connection pool via `asyncpg.create_pool()` with lifespan management |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncpg | 0.30.x | PostgreSQL async driver | 5x faster than psycopg3 async; native binary protocol; pool built-in; no ORM needed |
| FastAPI | 0.115.x | HTTP framework | Async-native; lifespan events; Pydantic integration; WebSocket support for Phase 8 |
| uvicorn | 0.34.x | ASGI server | Standard production server for FastAPI |
| pydantic-settings | 2.x | Configuration | Reads DATABASE_URL from env; validates at startup |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | 2.x | Request/response models | Already a FastAPI dependency; use for API schemas |
| httpx | 0.28.x | Async HTTP test client | FastAPI test client uses it; needed for integration tests |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| asyncpg (raw SQL) | SQLAlchemy async | Adds ORM complexity; project already uses raw SQL repos successfully |
| asyncpg | psycopg3 async | Slower; project explicitly chose asyncpg in v2.0 decisions |
| pydantic-settings | python-dotenv | pydantic-settings validates types at startup; catches bad config early |

**Installation:**
```bash
pip install fastapi uvicorn asyncpg pydantic-settings httpx
```

## Architecture Patterns

### Recommended Project Structure
```
src/
  server/
    __init__.py
    app.py           # create_app() factory with lifespan
    config.py         # Settings class (pydantic-settings)
    dependencies.py   # get_pool() dependency
  db/
    __init__.py
    schema.py         # Updated: PostgreSQL DDL + dataclasses
    repository.py     # Updated: asyncpg instead of aiosqlite
    migrations.py     # apply_schema(pool) -- runs CREATE TABLE IF NOT EXISTS
  pipeline/
    orchestrator.py   # Updated: uses TaskContext Protocol
    protocol.py       # TaskContext Protocol definition
    ...existing files...
```

### Pattern 1: FastAPI App Factory with Lifespan
**What:** A `create_app()` function that configures the FastAPI instance with a lifespan managing the asyncpg pool.
**When to use:** Always -- separates app construction from running, enables testing.
**Example:**
```python
# Source: FastAPI official docs (https://fastapi.tiangolo.com/advanced/events/)
from contextlib import asynccontextmanager
from fastapi import FastAPI
import asyncpg

from src.server.config import get_settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=5,
        command_timeout=60.0,
    )
    # Run schema migration
    async with app.state.pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
    yield
    await app.state.pool.close()

def create_app() -> FastAPI:
    app = FastAPI(title="AI Agent Console", lifespan=lifespan)
    # Register routes
    app.include_router(health_router)
    return app
```

### Pattern 2: asyncpg Repository (replacing aiosqlite)
**What:** Same repository-per-table pattern but using asyncpg Pool instead of aiosqlite Connection.
**When to use:** All database access.
**Example:**
```python
# Adapted from existing src/db/repository.py
import asyncpg

class SessionRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, session: Session) -> int:
        return await self._pool.fetchval(
            "INSERT INTO sessions (name, project_path, created_at) "
            "VALUES ($1, $2, $3) RETURNING id",
            session.name, session.project_path, session.created_at,
        )

    async def get(self, session_id: int) -> Session | None:
        row = await self._pool.fetchrow(
            "SELECT id, name, project_path, created_at "
            "FROM sessions WHERE id = $1",
            session_id,
        )
        if row is None:
            return None
        return Session(id=row["id"], name=row["name"],
                       project_path=row["project_path"],
                       created_at=row["created_at"])
```

### Pattern 3: TaskContext Protocol for Orchestrator Decoupling
**What:** A `typing.Protocol` that defines what the orchestrator needs from any UI frontend.
**When to use:** Replace the `app: AgentConsoleApp` parameter in `orchestrate_pipeline`.
**Example:**
```python
# Source: PEP 544 (https://peps.python.org/pep-0544/)
from typing import Protocol, runtime_checkable

@runtime_checkable
class TaskContext(Protocol):
    """Interface the orchestrator uses to interact with any UI frontend."""

    async def update_status(self, agent: str, state: str, step: str, next_action: str) -> None:
        """Update status display (status bar in TUI, event in web)."""
        ...

    async def stream_output(self, agent_name: str, prompt: str, sections: dict) -> dict[str, str]:
        """Run an agent and stream its output. Returns parsed sections."""
        ...

    async def confirm_reroute(self, next_agent: str, reasoning: str) -> bool:
        """Ask user to confirm re-routing decision."""
        ...

    async def handle_halt(self, iteration_count: int) -> str:
        """Ask user what to do at iteration limit. Returns 'continue'|'approve'|'stop'."""
        ...

    @property
    def project_path(self) -> str:
        """Path to the working project directory."""
        ...
```

### Pattern 4: Pool as Dependency
**What:** FastAPI dependency that extracts the pool from `request.app.state`.
**When to use:** Every endpoint that needs database access.
**Example:**
```python
from fastapi import Request

async def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool
```

### Anti-Patterns to Avoid
- **Creating connections per request:** Use the pool. Never call `asyncpg.connect()` in endpoints.
- **Storing pool as module-level global:** Use `app.state` -- enables testing with different pools.
- **Using aiosqlite placeholder syntax (?):** asyncpg uses `$1, $2, $3` positional parameters.
- **AUTOINCREMENT in PostgreSQL:** Use `SERIAL` or `BIGSERIAL` instead of `INTEGER PRIMARY KEY AUTOINCREMENT`.
- **TEXT for timestamps:** Use `TIMESTAMPTZ` -- asyncpg returns native `datetime` objects.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Connection pooling | Custom connection manager | `asyncpg.create_pool()` | Handles min/max sizing, health checks, connection recycling |
| Settings management | Manual os.environ parsing | `pydantic-settings` BaseSettings | Validates types, reads .env, fails fast on missing vars |
| Schema migration | Complex migration framework | `CREATE TABLE IF NOT EXISTS` in lifespan | Only 4 simple tables; no Alembic overhead justified yet |
| Health check logic | Custom TCP probes | Simple GET endpoint returning `{"status": "ok"}` | Standard pattern; Coolify/Docker can hit it directly |

**Key insight:** This is a single-user app with 4 tables. Keep the data layer simple -- raw SQL repositories with asyncpg are the right level of abstraction.

## Common Pitfalls

### Pitfall 1: aiosqlite-to-asyncpg SQL Dialect Differences
**What goes wrong:** Copy-pasting SQLite SQL and hitting syntax errors.
**Why it happens:** SQLite uses `?` placeholders, `AUTOINCREMENT`, `TEXT` for everything.
**How to avoid:** Systematic replacement checklist:
- `?` -> `$1, $2, ...` (positional)
- `INTEGER PRIMARY KEY AUTOINCREMENT` -> `SERIAL PRIMARY KEY`
- `TEXT` timestamps -> `TIMESTAMPTZ`
- `REAL` -> `DOUBLE PRECISION`
- `cursor.lastrowid` -> `RETURNING id` clause with `fetchval()`
**Warning signs:** `asyncpg.exceptions.PostgresSyntaxError` at startup.

### Pitfall 2: Pool Not Closed on Shutdown
**What goes wrong:** Leaked connections prevent PostgreSQL from accepting new ones.
**Why it happens:** Missing `finally` block in lifespan or exception during startup after pool creation.
**How to avoid:** Always use try/finally in lifespan:
```python
@asynccontextmanager
async def lifespan(app):
    app.state.pool = await asyncpg.create_pool(...)
    try:
        yield
    finally:
        await app.state.pool.close()
```
**Warning signs:** "too many connections" errors after server restarts during development.

### Pitfall 3: Forgetting RETURNING Clause
**What goes wrong:** INSERT returns status string, not the new row ID.
**Why it happens:** asyncpg `execute()` returns a command status string like `"INSERT 0 1"`, not lastrowid.
**How to avoid:** Use `fetchval("INSERT ... RETURNING id", ...)` for all INSERTs that need the generated ID.
**Warning signs:** Repository create methods return strings instead of ints.

### Pitfall 4: Circular Imports with Protocol
**What goes wrong:** Putting TaskContext in orchestrator.py and importing from tui creates cycles.
**Why it happens:** Protocol definition and consumer live in the same module.
**How to avoid:** Put `TaskContext` in its own module (`src/pipeline/protocol.py`) imported by both orchestrator and any frontend adapter.
**Warning signs:** `ImportError` at startup.

### Pitfall 5: Over-Sizing the Connection Pool
**What goes wrong:** Too many idle connections consume RAM on a 7.6GB VPS.
**Why it happens:** asyncpg defaults `min_size=10, max_size=10`.
**How to avoid:** Set `min_size=2, max_size=5`. This is a single-user app with max 2 concurrent tasks.
**Warning signs:** PostgreSQL `max_connections` exhaustion (default is 100, shared with n8n and other services).

## Code Examples

### PostgreSQL Schema (replacing SQLite)
```sql
-- Source: Adapted from existing src/db/schema.py SCHEMA_SQL
CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    project_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_outputs (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    agent_type TEXT NOT NULL,
    raw_output TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_usage (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    agent_type TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orchestrator_decisions (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    next_agent TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    confidence DOUBLE PRECISION,
    full_response TEXT NOT NULL,
    iteration_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Settings Configuration
```python
# Source: pydantic-settings docs
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5432/agent_console"
    pool_min_size: int = 2
    pool_max_size: int = 5
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_prefix": "APP_"}

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

### Health Check Endpoint
```python
from fastapi import APIRouter, Request

router = APIRouter()

@router.get("/health")
async def health_check(request: Request):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
    return {"status": "ok", "database": "connected"}
```

### Orchestrator Refactored Signature
```python
# Before (tightly coupled to TUI):
async def orchestrate_pipeline(
    app: AgentConsoleApp,
    prompt: str,
    db: aiosqlite.Connection | None = None,
    session_id: int | None = None,
) -> OrchestratorState:

# After (decoupled via Protocol):
async def orchestrate_pipeline(
    ctx: TaskContext,
    prompt: str,
    pool: asyncpg.Pool,
    session_id: int | None = None,
) -> OrchestratorState:
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` | `lifespan` async context manager | FastAPI 0.109+ (Jan 2024) | Startup/shutdown events deprecated; lifespan is required pattern |
| aiosqlite with `?` params | asyncpg with `$1` params | Project migration v2.0 | Must rewrite all SQL in repository layer |
| `cursor.lastrowid` | `RETURNING id` clause | asyncpg design | Different return semantics for INSERT |
| TYPE_CHECKING guard for AgentConsoleApp | Protocol-based TaskContext | Project migration v2.0 | Eliminates TUI dependency from orchestrator |

**Deprecated/outdated:**
- FastAPI `on_event("startup")`/`on_event("shutdown")`: Use `lifespan` parameter instead
- aiosqlite: Remains in codebase for v1.0 TUI mode but not used by web server

## Open Questions

1. **PostgreSQL credentials for the existing instance**
   - What we know: Container `ihhyb2rjq8jsx0ltbn1btj5a` runs postgres:16 on port 5432
   - What's unclear: Username, password, and whether a database named `agent_console` exists
   - Recommendation: Check Coolify dashboard for connection details; create database via `CREATE DATABASE agent_console` if needed

2. **Should `sessions` be renamed to `tasks` for v2.0?**
   - What we know: v1.0 calls them "sessions" (TUI sessions). v2.0 calls them "tasks" (web tasks). The REQUIREMENTS.md and roadmap use "tasks" consistently.
   - What's unclear: Whether to rename now or later
   - Recommendation: Rename to `tasks` in this phase since we are rewriting the schema anyway. This aligns with INFR-01 requirement language and the web mental model.

3. **Existing tests depend on aiosqlite `db_conn` fixture**
   - What we know: `conftest.py` provides an in-memory aiosqlite fixture; 160 tests rely on it
   - What's unclear: Whether to maintain dual fixtures or migrate all tests
   - Recommendation: Add a new `pg_pool` fixture using a test database; keep aiosqlite fixture for existing v1.0 tests that are not being modified in this phase

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.23.x |
| Config file | `pyproject.toml` (existing `[tool.pytest.asyncio]` section expected) |
| Quick run command | `python -m pytest tests/test_pg_repository.py tests/test_server.py -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFR-01a | PostgreSQL schema creates all 4 tables | integration | `python -m pytest tests/test_pg_repository.py::test_schema_creates_tables -x` | No -- Wave 0 |
| INFR-01b | Session/task CRUD persists across connections | integration | `python -m pytest tests/test_pg_repository.py::test_task_crud -x` | No -- Wave 0 |
| INFR-01c | Agent output persists linked to session | integration | `python -m pytest tests/test_pg_repository.py::test_agent_output_persistence -x` | No -- Wave 0 |
| INFR-01d | Usage tracking persists | integration | `python -m pytest tests/test_pg_repository.py::test_usage_persistence -x` | No -- Wave 0 |
| INFR-01e | Orchestrator decisions persist | integration | `python -m pytest tests/test_pg_repository.py::test_decision_persistence -x` | No -- Wave 0 |
| SC-01 | FastAPI starts and health endpoint returns 200 | integration | `python -m pytest tests/test_server.py::test_health_endpoint -x` | No -- Wave 0 |
| SC-02 | Health endpoint checks DB connectivity | integration | `python -m pytest tests/test_server.py::test_health_db_check -x` | No -- Wave 0 |
| SC-03 | Pool created on startup, closed on shutdown | integration | `python -m pytest tests/test_server.py::test_lifespan_pool -x` | No -- Wave 0 |
| SC-04 | TaskContext Protocol accepts non-TUI implementations | unit | `python -m pytest tests/test_protocol.py::test_taskcontext_protocol -x` | No -- Wave 0 |
| SC-05 | Orchestrator uses TaskContext instead of AgentConsoleApp | unit | `python -m pytest tests/test_orchestrator.py::test_orchestrator_uses_protocol -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_pg_repository.py tests/test_server.py tests/test_protocol.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_pg_repository.py` -- covers INFR-01a through INFR-01e
- [ ] `tests/test_server.py` -- covers SC-01, SC-02, SC-03
- [ ] `tests/test_protocol.py` -- covers SC-04, SC-05
- [ ] `tests/conftest.py` update -- add `pg_pool` fixture (test database or mock pool)
- [ ] Framework install: `pip install fastapi uvicorn asyncpg pydantic-settings httpx pytest-asyncio`

## Sources

### Primary (HIGH confidence)
- [asyncpg API Reference](https://magicstack.github.io/asyncpg/current/api/index.html) -- create_pool signature, Pool.acquire, fetch/fetchrow/execute methods
- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/) -- asynccontextmanager lifespan pattern, startup/shutdown deprecation
- [PEP 544](https://peps.python.org/pep-0544/) -- Protocol and structural subtyping specification
- Existing codebase: `src/db/schema.py`, `src/db/repository.py`, `src/pipeline/orchestrator.py` -- current aiosqlite patterns to migrate

### Secondary (MEDIUM confidence)
- [Daniel Feldroy: Using Asyncpg with FastAPI](https://daniel.feldroy.com/posts/2025-10-using-asyncpg-with-fastapi-and-air) -- verified app.state.pool pattern
- [FastAPI Discussion #9520](https://github.com/fastapi/fastapi/discussions/9520) -- community validation of lifespan pool pattern

### Tertiary (LOW confidence)
- Pool sizing recommendation (min=2, max=5) -- derived from project constraints (single user, 2 concurrent tasks, shared VPS) rather than benchmarking

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- asyncpg and FastAPI are locked decisions in STATE.md; versions verified against PyPI
- Architecture: HIGH -- patterns directly adapt existing working codebase patterns (repository, dataclass schemas)
- Pitfalls: HIGH -- SQL dialect differences are well-documented; pool lifecycle is standard asyncpg usage
- Protocol design: MEDIUM -- TaskContext method surface area derived from reading orchestrator.py call sites; may need adjustment during implementation

**Research date:** 2026-03-12
**Valid until:** 2026-04-12 (stable technologies, no fast-moving changes expected)
