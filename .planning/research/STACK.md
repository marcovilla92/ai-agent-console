# Stack Research

**Domain:** Web-based AI agent orchestration platform (TUI-to-web migration)
**Researched:** 2026-03-12
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| FastAPI | >=0.115 | Web framework, REST + WebSocket | Async-native, first-class WebSocket support via Starlette, Pydantic validation built-in. The only serious Python async web framework with this level of maturity. Latest: 0.135.1. |
| uvicorn | >=0.34 | ASGI server | Standard FastAPI server. Use `uvicorn[standard]` for uvloop + httptools performance boost. Latest: 0.41.0. |
| asyncpg | >=0.30 | PostgreSQL driver | 5x faster than psycopg3 for async workloads. Direct binary protocol, built-in connection pooling via `create_pool()`. No ORM needed for this project's simple schema. Latest: 0.31.0. |
| Jinja2 | >=3.1.4 | Server-side HTML templates | FastAPI's built-in `Jinja2Templates` class. Renders initial page shell; Alpine.js handles dynamic updates client-side. |
| Alpine.js | 3.x (CDN) | Client-side reactivity | No build step, ~17KB gzipped. `x-data`, `x-bind`, `x-on` cover all dashboard interactions. Loaded from CDN, zero server-side tooling. Latest: 3.15.1. |
| Pico CSS | 2.x (CDN) | Styling | Semantic HTML styling with zero classes needed for basics. Dark mode built-in. CDN delivery, no build step. Latest: 2.1.1. |
| Docker | (system) | Containerization | Required by Coolify. Multi-stage build for slim production image. |
| Python | 3.12 | Runtime | Already installed on VPS. asyncio mature, `asyncio.TaskGroup` available. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-multipart | >=0.0.18 | Form data parsing | Required by FastAPI for any form/file upload endpoints. Install even if not immediately needed -- FastAPI warns at startup without it. |
| httpx | >=0.27 | Async HTTP client | GitHub API calls (clone, push, PR creation). Also used as FastAPI test client via `AsyncClient(transport=ASGITransport(app=app))`. Latest: 0.28.1. |
| pydantic | >=2.0 | Data validation | Comes with FastAPI. Use for request/response models, settings management via `pydantic-settings`. |
| pydantic-settings | >=2.0 | Configuration from env vars | `.env` file loading, typed config. Replaces manual `os.environ` reads. |
| tenacity | >=8.0 | Retry logic | Already in use (v1.0). Keep for Claude CLI retry patterns. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| pytest | Testing | Already in use. |
| pytest-asyncio | Async test support | Already a dev dependency. Use `mode = "auto"` in pytest.ini. |
| httpx | Test client | `httpx.AsyncClient(transport=ASGITransport(app=app))` for testing FastAPI endpoints without running a server. |
| ruff | Linting + formatting | Fast, single-tool replacement for flake8+black+isort. Recommended but not blocking. |

### Frontend (CDN-delivered, no build step)

| Asset | Source | Notes |
|-------|--------|-------|
| Alpine.js 3.x | `cdn.jsdelivr.net/npm/alpinejs@3/dist/cdn.min.js` | Use `defer` attribute. Add `@alpinejs/morph` plugin only if needed for DOM diffing. |
| Pico CSS 2.x | `cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css` | Standard variant for dashboard (needs class-based layout control). Classless variant only for pure content pages. |

## Installation

```bash
# Core dependencies (add to pyproject.toml)
pip install "fastapi>=0.115" "uvicorn[standard]>=0.34" "asyncpg>=0.30" \
    "jinja2>=3.1.4" "python-multipart>=0.0.18" "httpx>=0.27" \
    "pydantic-settings>=2.0"

# Dev dependencies
pip install -D "pytest>=8.0" "pytest-asyncio>=0.23" "ruff>=0.4"

# Remove v1.0 dependencies no longer needed
pip uninstall textual aiosqlite
```

**pyproject.toml changes:**

```toml
[project]
requires-python = ">=3.12"

dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "asyncpg>=0.30",
    "jinja2>=3.1.4",
    "python-multipart>=0.0.18",
    "httpx>=0.27",
    "pydantic-settings>=2.0",
    "tenacity>=8.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
]
```

## Key Integration Points

### 1. FastAPI Lifespan + asyncpg Pool

```python
from contextlib import asynccontextmanager
import asyncpg

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2, max_size=5,  # Small pool -- single user, low concurrency
    )
    yield
    await app.state.db.close()

app = FastAPI(lifespan=lifespan)
```

**Why direct asyncpg, not SQLAlchemy:** The schema is simple (tasks, steps, logs). Raw SQL with asyncpg is faster, simpler to debug, and avoids ORM abstraction for ~10 tables. Pydantic models handle serialization. Migrations handled by plain SQL files, not Alembic.

### 2. WebSocket Streaming Pattern

```python
@app.websocket("/ws/tasks/{task_id}")
async def task_stream(websocket: WebSocket, task_id: str):
    await websocket.accept()
    # Late-join replay: send buffered events from DB/memory
    for event in await get_task_events(task_id):
        await websocket.send_json(event)
    # Live stream: subscribe to task's asyncio.Queue
    queue = subscribe_to_task(task_id)
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        unsubscribe(task_id, queue)
```

**Key pattern:** Each running task has an `asyncio.Queue` for fan-out to connected WebSocket clients. Late-join replay pulls from DB. No Redis/message broker needed for single-user.

### 3. Alpine.js + WebSocket Client

```html
<div x-data="taskStream('{{ task_id }}')">
    <div x-ref="output"></div>
</div>
<script>
function taskStream(taskId) {
    return {
        ws: null,
        init() {
            this.ws = new WebSocket(`ws://${location.host}/ws/tasks/${taskId}`);
            this.ws.onmessage = (e) => {
                const event = JSON.parse(e.data);
                // append to output
            };
        }
    }
}
</script>
```

### 4. Existing Code Reuse Map

| v1.0 Module | Reuse Strategy |
|-------------|----------------|
| `agents/` (plan, execute, review) | Direct reuse. No changes needed. |
| `runner.py` (stream_claude) | Direct reuse. Already yields text chunks + dict events. |
| `parser.py` (NDJSON) | Direct reuse. |
| `context.py` (workspace assembly) | Direct reuse. |
| `pipeline.py` (orchestrator) | Adapt: replace TUI callbacks with WebSocket/queue push. |
| `db.py` (SQLite) | Replace entirely: new asyncpg-based module. |
| `app.py`, `panels/`, `actions/` (TUI) | Drop. Replaced by FastAPI routes + Jinja2 templates + Alpine.js. |

### 5. Docker + Coolify Deployment

```dockerfile
FROM python:3.12-slim AS base
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY src/ src/
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Coolify auto-deploys from GitHub push. Traefik handles TLS termination at `console.amcsystem.uk`. WebSocket upgrade headers pass through Traefik by default.

### 6. Database Connection (VPS PostgreSQL)

Connect to the existing Coolify-managed PostgreSQL 16 instance. Connection string via environment variable:

```
DATABASE_URL=postgresql://user:pass@host:5432/agent_console
```

asyncpg pool `min_size=2, max_size=5` is appropriate. Single user with max 2 concurrent Claude CLI tasks means peak DB concurrency is low.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| asyncpg (raw SQL) | SQLAlchemy async + Alembic | If schema grows beyond ~15 tables or needs complex joins/migrations. Not this project. |
| Alpine.js (CDN) | htmx | If the app were more server-rendered with partial HTML swaps. Alpine.js better for WebSocket-heavy real-time updates. |
| Pico CSS (CDN) | Tailwind CSS | If extensive custom styling needed. Pico's semantic approach matches this project's simplicity. Tailwind requires a build step. |
| asyncpg pool | PgBouncer | If multiple services shared the same PG instance with high connection counts. asyncpg's built-in pool sufficient for single-app. |
| Plain SQL migrations | Alembic | If using SQLAlchemy ORM. Without ORM, numbered SQL files (`001_init.sql`, `002_add_column.sql`) with a simple runner are lighter weight. |
| uvicorn single-process | Gunicorn + uvicorn workers | If running multiple worker processes for high concurrency. Single-user app does not need this. |
| Native WebSocket | Socket.IO / python-socketio | If scaling to multiple server nodes with shared state. Adds unnecessary protocol layer for single-node single-user. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| SQLAlchemy ORM | Unnecessary abstraction for ~10 tables. Adds complexity, slower than raw asyncpg, harder to debug SQL. | asyncpg with raw SQL + Pydantic models for serialization |
| Alembic | Only useful with SQLAlchemy. Overkill for simple schema evolution. | Numbered SQL migration files with a simple apply script |
| Celery / Redis / RabbitMQ | Single-user, max 2 concurrent tasks. asyncio.Semaphore + asyncio.Queue handle all concurrency. Adding a broker adds operational complexity for zero benefit. | `asyncio.Semaphore(2)` for task limiting, `asyncio.Queue` for event fan-out |
| React / Vue / Svelte | Require build tooling (node, npm, webpack/vite). Massive overkill for a single-user dashboard. | Alpine.js from CDN (zero build step) |
| Tailwind CSS | Requires PostCSS build step. Against the no-build-step constraint. | Pico CSS from CDN |
| Socket.IO / python-socketio | Adds unnecessary protocol layer over native WebSocket. Only needed if scaling to multiple server nodes. | Native FastAPI `@app.websocket()` decorator |
| aiosqlite | Being replaced by PostgreSQL. Remove from dependencies. | asyncpg |
| Textual | TUI framework being replaced by web interface. Remove from dependencies. | FastAPI + Alpine.js |
| Flask / Django | Flask lacks native async. Django is heavyweight with ORM baggage. | FastAPI |
| Pydantic v1 | FastAPI >=0.100 requires Pydantic v2. Do not pin to v1. | Pydantic v2 (comes with FastAPI) |
| SSE (Server-Sent Events) | Unidirectional. Project needs bidirectional communication for approval gates in supervised mode (user sends "approve" back to server). | WebSocket (bidirectional) |
| Typer | No longer needed. Was for TUI CLI entry point. Web app starts via uvicorn. | uvicorn CLI or Docker CMD |
| loguru | Not strictly needed in v2.0. Python stdlib `logging` is sufficient. If added, it is optional. | `logging` (stdlib) |

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| FastAPI >=0.115 | Python >=3.10, Pydantic >=2.0 | Starlette 0.40+ bundled. WebSocket support included. |
| asyncpg >=0.30 | Python >=3.9, PostgreSQL 9.5-18 | PostgreSQL 16 on VPS is fully supported. |
| uvicorn[standard] >=0.34 | Python >=3.10 | `[standard]` adds uvloop + httptools for performance. |
| Alpine.js 3.x | Any modern browser | No server-side dependency. |
| Pico CSS 2.x | Any modern browser | No JavaScript dependency. |
| Jinja2 >=3.1.4 | Python >=3.8 | FastAPI uses Starlette's Jinja2Templates wrapper. |
| httpx >=0.27 | Python >=3.8 | Async HTTP client + FastAPI test transport. |
| pydantic-settings >=2.0 | Pydantic >=2.0 | Loads `.env` files, typed config classes. |

## Sources

- [FastAPI PyPI](https://pypi.org/project/fastapi/) -- version 0.135.1, verified 2026-03-12 (HIGH confidence)
- [asyncpg PyPI](https://pypi.org/project/asyncpg/) -- version 0.31.0, supports PG 9.5-18 (HIGH confidence)
- [uvicorn PyPI](https://pypi.org/project/uvicorn/) -- version 0.41.0, Python >=3.10 (HIGH confidence)
- [Alpine.js GitHub releases](https://github.com/alpinejs/alpine/releases) -- version 3.15.1 (HIGH confidence)
- [Pico CSS GitHub](https://github.com/picocss/pico) -- version 2.1.1 (HIGH confidence)
- [FastAPI WebSocket docs](https://fastapi.tiangolo.com/advanced/websockets/) -- native Starlette WebSocket support (HIGH confidence)
- [asyncpg docs](https://magicstack.github.io/asyncpg/current/usage.html) -- connection pool patterns (HIGH confidence)
- [FastAPI templates docs](https://fastapi.tiangolo.com/advanced/templates/) -- Jinja2Templates usage (HIGH confidence)
- [FastAPI + asyncpg without ORM](https://www.sheshbabu.com/posts/fastapi-without-orm-getting-started-with-asyncpg/) -- pattern validation (MEDIUM confidence)
- [httpx PyPI](https://pypi.org/project/httpx/) -- version 0.28.1 (HIGH confidence)

---
*Stack research for: AI Agent Workflow Console v2.0 Web Platform*
*Researched: 2026-03-12*
