# Architecture Research

**Domain:** AI Agent Console v2.1 — Project Router integration into existing FastAPI platform
**Researched:** 2026-03-13
**Confidence:** HIGH (direct codebase analysis + full design spec review)

---

## Note on Scope

This document covers **v2.1 integration architecture only** — how the new Project Router
components integrate with the existing v2.0 FastAPI platform. The v2.0 base architecture
(TaskManager, ConnectionManager, ApprovalGate, asyncpg pool) is established and working;
this document focuses on what changes, what is added, and how the pieces connect.

---

## System Overview

### Current State (v2.0)

```
┌──────────────────────────────────────────────────────────────┐
│  BROWSER                                                      │
│  Jinja2 HTML (task_list.html, task_detail.html) + Alpine.js  │
└────────────────┬──────────────────────┬──────────────────────┘
                 │ HTTP (Basic Auth)    │ WebSocket (?token=)
                 ▼                      ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI app.py                                               │
│  lifespan: asyncpg pool → apply_schema → TaskManager         │
├─────────────┬───────────────────┬────────────────────────────┤
│ /tasks      │ /ws/tasks/{id}    │ /  /tasks/{id}/view        │
│ tasks.py    │ ws.py             │ views.py (Jinja2Templates) │
└─────────────┴───────────────────┴────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  Engine / Service Layer                                       │
│  TaskManager (engine/manager.py)                             │
│  ├── asyncio.Semaphore(2)     concurrency cap                │
│  ├── TaskRepository           DB CRUD                        │
│  └── orchestrate_pipeline()   Plan/Execute/Review            │
└──────────────────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  Data Layer                                                   │
│  asyncpg Pool → PostgreSQL 16                                │
│  Tables: tasks, agent_outputs, agent_usage,                  │
│          orchestrator_decisions                              │
└──────────────────────────────────────────────────────────────┘
```

### Target State (v2.1)

```
┌──────────────────────────────────────────────────────────────┐
│  BROWSER — SPA (no page reloads)                             │
│  static/index.html — Alpine.js — 4 states:                   │
│  select → create → prompt → running                          │
└────────────────┬──────────────────────┬──────────────────────┘
                 │ REST (Basic Auth)    │ WebSocket (unchanged)
                 ▼                      ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI app.py (modified lifespan + routers)                │
│  StaticFiles("/static") + GET "/" → FileResponse(index.html) │
├──────────┬──────────┬──────────┬────────┬────────────────────┤
│/projects │/templates│/tasks    │/ws/    │/health             │
│NEW       │NEW       │MODIFIED  │UNCHANGED│UNCHANGED          │
└──────────┴──────────┴──────────┴────────┴────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  Service Layer                                               │
│  TaskManager (unchanged except stores project_id on task)    │
│  ProjectService (NEW — pipeline/project_service.py)          │
│  ├── ProjectRepository      DB CRUD for projects table       │
│  ├── assemble_full_context()  enhanced async assembler       │
│  ├── Jinja2 Environment     .j2 scaffolding renderer         │
│  └── emit_event()           n8n hook placeholder (no-op)     │
└──────────────────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│  Data Layer                                                   │
│  asyncpg Pool → PostgreSQL 16                                │
│  Tables (existing): tasks (+project_id FK), agent_outputs,   │
│          agent_usage, orchestrator_decisions                 │
│  Tables (new): projects                                       │
│  Filesystem: ~/projects/   (source of truth for project list)│
│  Filesystem: src/templates/ (scaffolding .j2 + static files) │
└──────────────────────────────────────────────────────────────┘
```

### Component Map

| Component | File | Status | What Changes |
|-----------|------|--------|--------------|
| FastAPI lifespan | `server/app.py` | MODIFY | Add ProjectService init; add 2 new routers; remove view_router; add StaticFiles; add root route |
| Settings | `server/config.py` | MODIFY | Add `n8n_webhook_url`, `n8n_events_enabled` |
| Dependencies | `server/dependencies.py` | MODIFY | Add `get_project_service()` injector |
| Projects router | `server/routers/projects.py` | NEW | 5 endpoints: project CRUD + context + suggested-phase |
| Templates router | `server/routers/templates.py` | NEW | 5 endpoints: template CRUD |
| Tasks router | `server/routers/tasks.py` | MODIFY | `TaskCreate` gains `project_id: int`; handler enriches prompt with context |
| Views router | `server/routers/views.py` | REMOVE | Deleted; replaced by StaticFiles + FileResponse |
| DB schema | `db/pg_schema.py` | MODIFY | Add `Project` dataclass; add `CREATE TABLE projects`; add `ALTER TABLE tasks ADD COLUMN project_id` |
| DB repository | `db/pg_repository.py` | MODIFY | Add `ProjectRepository` class |
| DB migrations | `db/migrations.py` | MODIFY | Run new DDL for projects table + tasks ALTER |
| Context assembler | `context/assembler.py` | MODIFY | Add `assemble_full_context()` (async), `suggest_next_phase()`, `get_recent_git_log()`, `get_recent_tasks()` |
| Project scaffold | `pipeline/project.py` | MODIFY | Add `scaffold_from_template()`, `git_init_and_commit()` |
| Project service | `pipeline/project_service.py` | NEW | `ProjectService`: create/list/scan/context/delete |
| Event system | `pipeline/events.py` | NEW | `ProjectEvent` enum + `emit_event()` no-op |
| Template files | `src/templates/` | REPURPOSE | Delete HTML templates; add `registry.yaml` + 4 template dirs with `.j2` + static files |
| SPA frontend | `static/index.html` | NEW | Alpine.js 4-state SPA |
| TaskManager | `engine/manager.py` | MINOR | `submit()` stores `project_id` on task row |

**Unchanged:** `engine/context.py`, `pipeline/orchestrator.py`, `pipeline/runner.py`,
`pipeline/handoff.py`, `pipeline/protocol.py`, `server/connection_manager.py`, `server/routers/ws.py`

---

## Recommended Project Structure (v2.1 target)

```
src/
├── server/
│   ├── app.py               # +ProjectService in lifespan; +project_router, template_router
│   │                        # +StaticFiles mount; +root FileResponse; -view_router
│   ├── config.py            # +n8n_webhook_url: str = ""; +n8n_events_enabled: list[str] = []
│   ├── dependencies.py      # +get_project_service() → app.state.project_service
│   ├── connection_manager.py # UNCHANGED
│   └── routers/
│       ├── projects.py      # NEW: GET/POST/DELETE /projects
│       │                    #      GET /projects/{id}/context
│       │                    #      GET /projects/{id}/suggested-phase
│       ├── templates.py     # NEW: GET/POST/PUT/DELETE /templates, GET /templates/{id}
│       ├── tasks.py         # MODIFY: TaskCreate.project_id required; handler enriches prompt
│       ├── ws.py            # UNCHANGED
│       └── views.py         # DELETED
│
├── db/
│   ├── pg_schema.py         # +Project dataclass; +DDL projects table; +ALTER tasks project_id
│   ├── pg_repository.py     # +ProjectRepository (create/get/get_by_path/list_all/update_last_used/delete)
│   ├── migrations.py        # +create_projects_table DDL; +alter_tasks_add_project_id
│   ├── repository.py        # UNCHANGED (v1.0 aiosqlite, keep for existing tests)
│   └── schema.py            # UNCHANGED (v1.0 dataclasses)
│
├── pipeline/
│   ├── project_service.py   # NEW: ProjectService class
│   ├── project.py           # +scaffold_from_template(); +git_init_and_commit(); +slugify()
│   ├── events.py            # NEW: ProjectEvent enum + emit_event() no-op placeholder
│   ├── orchestrator.py      # UNCHANGED
│   ├── runner.py            # UNCHANGED
│   ├── handoff.py           # UNCHANGED
│   └── protocol.py         # UNCHANGED
│
├── engine/
│   ├── manager.py           # MINOR: submit() stores project_id on task row
│   └── context.py           # UNCHANGED
│
├── context/
│   └── assembler.py         # +assemble_full_context() (async)
│                            # +suggest_next_phase()
│                            # +get_recent_git_log() (async subprocess)
│                            # +get_recent_tasks() (DB query)
│
└── templates/               # REPURPOSED — was Jinja2 HTML templates
    ├── registry.yaml         # Template index (builtin + custom entries)
    ├── blank/
    │   ├── CLAUDE.md.j2
    │   └── .planning/README.md
    ├── fastapi-pg/
    │   ├── CLAUDE.md.j2
    │   ├── .claude/settings.local.json
    │   ├── .claude/agents/db-migrator.md
    │   ├── .claude/agents/api-tester.md
    │   ├── .claude/commands/migrate.md
    │   ├── .claude/commands/seed.md
    │   ├── .claude/commands/test-api.md
    │   ├── src/__init__.py
    │   ├── src/main.py
    │   ├── src/config.py
    │   ├── src/db/schema.py
    │   ├── src/routers/__init__.py
    │   ├── tests/conftest.py
    │   ├── Dockerfile
    │   ├── docker-compose.yml.j2
    │   ├── pyproject.toml.j2
    │   └── .gitignore
    ├── telegram-bot/
    │   ├── CLAUDE.md.j2
    │   ├── .claude/agents/handler-builder.md
    │   ├── .claude/commands/test-bot.md
    │   ├── .claude/commands/deploy-bot.md
    │   ├── src/bot.py
    │   ├── src/handlers/__init__.py
    │   ├── src/config.py
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── .gitignore
    └── cli-tool/
        ├── CLAUDE.md.j2
        ├── .claude/agents/command-builder.md
        ├── .claude/commands/release.md
        ├── src/__init__.py
        ├── src/cli.py
        ├── src/commands/__init__.py
        ├── pyproject.toml.j2
        └── .gitignore

static/
└── index.html               # NEW: Alpine.js SPA (4 states, ~400 LOC)
```

### Structure Rationale

- **`src/templates/` repurposed:** The existing directory currently holds `task_list.html`, `task_detail.html`, `base.html`. These are deleted when views.py is removed. The same directory becomes the scaffolding template store. This is explicit in the spec and key decisions table: "Jinja2 HTML templates removed, directory repurposed."
- **`static/` at project root:** FastAPI mounts `StaticFiles(directory="static")`. Placing it at the project root (peer to `src/`) keeps it clearly separate from Python source. The SPA is a single `index.html` — no build step.
- **`pipeline/project_service.py`:** Business logic belongs in pipeline layer, not server layer. Mirrors how `TaskManager` lives in `engine/` — both are services the router handlers depend on via DI.
- **`pipeline/events.py` as a separate file:** Isolates the n8n placeholder. When webhooks are eventually implemented, only this file changes — no impact on ProjectService logic.

---

## Architectural Patterns

### Pattern 1: Repository Pattern — Extend to ProjectRepository

**What:** Add `ProjectRepository` to `pg_repository.py` following the exact same pattern as `TaskRepository`. Constructor takes `asyncpg.Pool`. All SQL is inside the class. No SQL leaks into service or router layers.
**When to use:** All DB access in this codebase.

```python
class ProjectRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, project: Project) -> int:
        return await self._pool.fetchval(
            "INSERT INTO projects (name, slug, path, description, created_at) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING id",
            project.name, project.slug, project.path,
            project.description, project.created_at,
        )

    async def get(self, project_id: int) -> Optional[Project]: ...
    async def get_by_path(self, path: str) -> Optional[Project]: ...
    async def list_all(self) -> list[Project]: ...
    async def update_last_used(self, project_id: int) -> None: ...
    async def delete(self, project_id: int) -> None: ...
```

### Pattern 2: app.state Service Injection — Extend to ProjectService

**What:** `ProjectService` is created in lifespan alongside `TaskManager`, stored on `app.state`, extracted via a `get_project_service()` dependency in `dependencies.py`. Identical to the existing `get_task_manager()` pattern.

```python
# app.py lifespan addition:
app.state.project_service = ProjectService(
    pool=app.state.pool,
    templates_dir=Path(__file__).resolve().parent.parent / "templates",
    workspace_root=Path.home() / "projects",
)

# dependencies.py addition:
async def get_project_service(request: Request) -> ProjectService:
    return request.app.state.project_service
```

### Pattern 3: Jinja2 Reused for .j2 Scaffolding (separate Environment)

**What:** The `jinja2` dependency is already installed. A second `jinja2.Environment` (distinct from any HTML template environment) handles `.j2` scaffolding files. Files without `.j2` suffix are copied verbatim.

**Critical detail:** Use `StrictUndefined` — a missing `{{ slug }}` variable must raise an error, not silently render as empty string.

```python
from jinja2 import Environment, FileSystemLoader, StrictUndefined
import shutil

def render_template_files(template_dir: Path, dest_dir: Path, context: dict) -> None:
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    for src in template_dir.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(template_dir)
        if src.suffix == ".j2":
            dest = dest_dir / rel.with_suffix("")   # strip .j2
            content = env.get_template(str(rel)).render(**context)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content)
        else:
            dest = dest_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
```

### Pattern 4: Async subprocess for git operations

**What:** `asyncio.create_subprocess_exec` for all git calls. Never use `subprocess.run` in async handlers — it blocks the event loop and stalls WebSocket pings and concurrent tasks.

```python
async def git_init_and_commit(project_path: str, message: str = "Initial commit") -> None:
    for args in [
        ["git", "init"],
        ["git", "add", "."],
        ["git", "-c", "user.name=ubuntu", "-c", "user.email=ubuntu@localhost",
         "commit", "-m", message],
    ]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=project_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git {args[1]} failed: {stderr.decode()}")

async def get_recent_git_log(project_path: str, count: int = 10) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git", "log", f"--max-count={count}", "--oneline",
        cwd=project_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode().strip() if proc.returncode == 0 else ""
```

### Pattern 5: Alpine.js multi-state SPA with single x-data root

**What:** Single `x-data="app()"` on `<body>`. State transitions via `this.state = 'prompt'`. Each view is a `<div x-show="state === 'select'">` block. No router, no build step.

```html
<body x-data="app()">
  <div x-show="state === 'select'"> ... </div>
  <div x-show="state === 'create'"> ... </div>
  <div x-show="state === 'prompt'"> ... </div>
  <div x-show="state === 'running'"> ... </div>
</body>
<script>
function app() {
  return {
    state: 'select',
    // Data
    projects: [], selectedProject: null,
    templates: [], selectedTemplate: 'blank',
    suggestedPhase: null, allPhases: [],
    projectContext: null, showContext: false,
    currentTask: null, outputLines: [], ws: null,
    // Lifecycle
    async init() { await this.loadProjects() },
    async loadProjects() { ... },
    async selectProject(p) {
      this.selectedProject = p
      await Promise.all([this.loadSuggestedPhase(p.id), this.loadContext(p.id)])
      this.state = 'prompt'
    },
    async submitPrompt(prompt, mode) {
      const res = await fetch('/tasks', { method: 'POST',
        headers: {...}, body: JSON.stringify({ prompt, mode, project_id: this.selectedProject.id }) })
      this.currentTask = await res.json()
      this.state = 'running'
      this.connectWs(this.currentTask.id)
    },
    connectWs(taskId) {
      this.ws = new WebSocket(`/ws/tasks/${taskId}?token=${btoa('user:pass')}`)
      this.ws.onmessage = (e) => {
        const msg = JSON.parse(e.data)
        if (msg.type === 'chunk') this.outputLines.push(msg.data)
        if (msg.type === 'status') { /* terminal state */ }
      }
    }
  }
}
</script>
```

### Pattern 6: SPA served via FastAPI StaticFiles + root FileResponse

**What:** Replace `views.py` Jinja2 routes with `StaticFiles` mount and a root `GET /` that returns `static/index.html`. The SPA calls REST APIs directly.

```python
# app.py:
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", include_in_schema=False)
async def spa_root(username: str = Depends(verify_credentials)):
    return FileResponse("static/index.html")
```

Note: HTTP Basic Auth must still protect the root route and all API routes. The `verify_credentials` dependency applies to `/` — the browser will prompt for credentials on first load.

---

## Data Flow

### Task Creation with Project Context (new flow)

```
User clicks "Invia" in SPA (state=prompt)
    │
    ▼
POST /tasks { prompt, mode, project_id }
    │
    ▼
tasks.py: create_task()
    ├── 1. ProjectRepository.get(project_id)          → Project row (path, name)
    ├── 2. ProjectService.get_project_context(id)
    │       └── assemble_full_context(project.path, pool)
    │               ├── assemble_workspace_context()  sync, existing
    │               ├── read CLAUDE.md truncated       sync
    │               ├── read .planning/ docs            sync
    │               ├── get_recent_git_log()            async subprocess
    │               └── get_recent_tasks(pool, path)    async DB
    ├── 3. enriched_prompt = context_block + "\n\n" + body.prompt
    ├── 4. TaskManager.submit(enriched_prompt, body.mode, project.path)
    └── 5. ProjectRepository.update_last_used(project_id)
    │
    ▼
HTTP 201 TaskResponse { id, status="queued", ... }
    │
    ▼
SPA: state = 'running'; connectWs(task.id)
    │
    ▼
WebSocket /ws/tasks/{id} (unchanged — streams enriched prompt execution)
```

### Project Creation Flow

```
User fills form (state=create) → POST /projects { name, description, template }
    │
    ▼
projects.py: create_project()
    └── ProjectService.create_new_project(name, description, template)
            ├── slug = slugify(name)             e.g. "My API" → "my-api"
            ├── path = ~/projects/{slug}          mkdir(exist_ok=False)
            ├── render_template_files(            copy + render .j2 files
            │       src/templates/{template}/,
            │       path,
            │       { name, slug, description, date, author="ubuntu" }
            │   )
            ├── git_init_and_commit(path)         async subprocess
            ├── ProjectRepository.create(project) → project_id
            └── emit_event(PROJECT_CREATED, {...}) no-op placeholder
    │
    ▼
HTTP 201 ProjectResponse { id, name, slug, path, ... }
    │
    ▼
SPA: selectedProject = response; load context + suggested-phase; state = 'prompt'
```

### GET /projects (filesystem reconciliation)

```
GET /projects
    │
    ▼
ProjectService.list_projects()
    ├── ProjectRepository.list_all()          → all DB records (as {path: project} dict)
    ├── os.scandir(~/projects/)               → all subdirectories
    ├── for each dir not tracked in DB:
    │       ProjectRepository.create(auto-register with blank description)
    └── return merged list sorted by last_used_at DESC
    │
    ▼
{ projects: [...], count: N }
```

### Phase Suggestion Flow

```
GET /projects/{id}/suggested-phase
    │
    ▼
suggest_next_phase(project_path)
    ├── read .planning/STATE.md       → look for "Current Phase", "Next Phase"
    ├── read .planning/ROADMAP.md     → parse phase list with status markers
    ├── scandir .planning/phases/     → find first dir without SUMMARY.md
    └── return { phase_id, phase_name, status, reason }
    │
    ▼
{ suggestion: {...}, all_phases: [...] }
```

### Alpine.js State Machine

```
state: 'select'
    │ user clicks project card
    ▼ selectProject(p) → GET /projects/{id}/suggested-phase + GET /projects/{id}/context
state: 'prompt'
    │ user submits prompt
    ▼ submitPrompt() → POST /tasks { project_id, prompt, mode }
state: 'running'
    │ task reaches terminal status (completed/failed/cancelled)
    ▼ [back button or new task] → state = 'select'

Parallel path from 'select':
    │ user clicks "+ Nuovo"
    ▼ GET /templates
state: 'create'
    │ user submits form
    ▼ POST /projects
state: 'prompt' (with new project as selectedProject)
```

---

## Integration Points

### New vs Modified — Complete File Map

| File | Change | Detail |
|------|--------|--------|
| `src/db/pg_schema.py` | MODIFY | Add `Project` dataclass (id, name, slug, path, description, created_at, last_used_at); add `CREATE TABLE projects` DDL; add `ALTER TABLE tasks ADD COLUMN IF NOT EXISTS project_id INTEGER REFERENCES projects(id)` |
| `src/db/pg_repository.py` | MODIFY | Add `ProjectRepository` class with 6 methods |
| `src/db/migrations.py` | MODIFY | Call `CREATE TABLE projects` DDL + `ALTER TABLE tasks ADD COLUMN project_id` |
| `src/context/assembler.py` | MODIFY | Add `assemble_full_context(project_path, pool)` async; `suggest_next_phase(project_path)` async; `get_recent_git_log(path, count)` async; `get_recent_tasks(pool, path, limit)` async |
| `src/pipeline/project.py` | MODIFY | Add `scaffold_from_template(template_dir, dest_dir, context)`, `git_init_and_commit(path)`, `slugify(name)` |
| `src/pipeline/project_service.py` | NEW | `ProjectService` class: `create_new_project`, `list_projects`, `scan_and_register`, `get_project_context`, `delete_project` |
| `src/pipeline/events.py` | NEW | `ProjectEvent` enum; `async emit_event(event, payload)` no-op stub |
| `src/server/routers/projects.py` | NEW | 5 endpoints on `project_router` with prefix `/projects` |
| `src/server/routers/templates.py` | NEW | 5 endpoints on `template_router` with prefix `/templates` |
| `src/server/routers/tasks.py` | MODIFY | `TaskCreate.project_id: int` (required); handler adds context enrichment + `update_last_used` |
| `src/server/routers/views.py` | REMOVE | Delete file; remove include from app.py |
| `src/server/app.py` | MODIFY | Lifespan adds `ProjectService`; include `project_router`, `template_router`; remove `view_router`; add `StaticFiles` mount + root `FileResponse` |
| `src/server/config.py` | MODIFY | Add `n8n_webhook_url: str = ""` and `n8n_events_enabled: list[str] = []` |
| `src/server/dependencies.py` | MODIFY | Add `get_project_service(request) → ProjectService` |
| `src/templates/task_list.html` | DELETE | Replaced by SPA |
| `src/templates/task_detail.html` | DELETE | Replaced by SPA |
| `src/templates/base.html` | DELETE | Replaced by SPA |
| `src/templates/registry.yaml` | NEW | Template index YAML |
| `src/templates/blank/` | NEW | Blank template files |
| `src/templates/fastapi-pg/` | NEW | FastAPI+PG template files |
| `src/templates/telegram-bot/` | NEW | Telegram bot template files |
| `src/templates/cli-tool/` | NEW | CLI tool template files |
| `static/index.html` | NEW | Alpine.js SPA |

### Boundary: tasks.py ↔ ProjectService

The task creation handler in `tasks.py` gains a dependency on `ProjectService`. This is the key integration point for context enrichment:

```python
@task_router.post("", status_code=201, response_model=TaskResponse)
async def create_task(
    body: TaskCreate,
    manager: TaskManager = Depends(get_task_manager),
    project_svc: ProjectService = Depends(get_project_service),
    pool: asyncpg.Pool = Depends(get_pool),
):
    repo = ProjectRepository(pool)
    project = await repo.get(body.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    ctx = await project_svc.get_project_context(body.project_id)
    context_block = format_context_for_prompt(ctx)
    enriched_prompt = f"{context_block}\n\n{body.prompt}"

    task_id = await manager.submit(
        prompt=enriched_prompt,
        mode=body.mode,
        project_path=project.path,
    )
    await repo.update_last_used(body.project_id)
    ...
```

### Boundary: templates.py ↔ Filesystem

Templates router does NOT use `ProjectService` — it works directly with the `src/templates/` directory and `registry.yaml`. Operations: read registry YAML, create/modify/delete template directories, enforce builtin protection (403 if `builtin: true`).

### Boundary: app.py lifespan (before/after)

```python
# BEFORE (v2.0):
app.state.connection_manager = ConnectionManager()
app.state.task_manager = TaskManager(pool=app.state.pool, ...)

# AFTER (v2.1):
app.state.connection_manager = ConnectionManager()
app.state.task_manager = TaskManager(pool=app.state.pool, ...)
app.state.project_service = ProjectService(     # NEW
    pool=app.state.pool,
    templates_dir=Path("src/templates"),
    workspace_root=Path.home() / "projects",
)
```

### External Services

| Service | Integration | Notes |
|---------|-------------|-------|
| PostgreSQL 16 | asyncpg pool (unchanged) | New `projects` table; `tasks.project_id` FK nullable for backward compat |
| Filesystem `~/projects/` | `pathlib.Path` operations | Source of truth; never delete on `DELETE /projects/{id}` |
| git | `asyncio.create_subprocess_exec` | project creation (init+commit) + context assembly (log) |
| n8n webhook | `emit_event()` no-op | No HTTP calls in v2.1; placeholder only |

---

## Build Order

The spec's execution order is dependency-correct. Here is the rationale:

| Step | What | Why This Position |
|------|------|-------------------|
| 1 | `pg_schema.py` + `migrations.py` | All layers depend on `projects` table and `tasks.project_id` column existing |
| 2 | `pg_repository.py` + `ProjectRepository` | `ProjectService` and task router handler depend on this |
| 3 | `src/templates/` content (registry.yaml + template dirs) | `ProjectService.create_new_project()` reads from here |
| 4 | `context/assembler.py` enhancements | `ProjectService.get_project_context()` calls `assemble_full_context()` |
| 5 | `pipeline/project.py` scaffold + git functions | `ProjectService` delegates filesystem operations here |
| 6 | `pipeline/events.py` stub | `ProjectService` calls `emit_event()` — must exist before service |
| 7 | `pipeline/project_service.py` | Depends on steps 2–6 |
| 8 | `server/routers/projects.py` + `templates.py` | Depend on ProjectService (step 7) |
| 9 | `server/routers/tasks.py` modification | Depends on ProjectRepository (step 2) + ProjectService (step 7) |
| 10 | `server/app.py` + `config.py` + `dependencies.py` | Wire everything; StaticFiles needs `static/` dir |
| 11 | `static/index.html` SPA | All API endpoints must exist first |
| 12 | Tests + verification | End-to-end check against running server |

**Critical constraint at step 9:** Changing `TaskCreate.project_id` to required breaks any existing tests that create tasks without a project. Either add a migration for existing task rows, make `project_id` optional with a fallback to `settings.project_path`, or update all tests. The spec makes it required — plan for test updates.

**Critical constraint at step 10:** `views.py` removal and `StaticFiles` addition happen together. The existing Jinja2 `Jinja2Templates` instance in `views.py` disappears. The `jinja2` package itself stays (needed by the scaffolding engine in step 5).

---

## Anti-Patterns

### Anti-Pattern 1: Context Assembly in the Router Handler

**What people do:** Build `assemble_full_context()` inline inside `tasks.py:create_task()`, importing assembler functions directly in the router.
**Why it's wrong:** Router becomes responsible for a service-layer concern. Hard to test. Context assembly logic duplicated if called from other places.
**Do this instead:** `ProjectService.get_project_context()` owns assembly. Router calls service, receives result string, prepends it. Router stays thin.

### Anti-Pattern 2: Blocking subprocess for git

**What people do:** `subprocess.run(["git", "log", ...])` inside an async handler or service method.
**Why it's wrong:** Blocks the asyncio event loop. Stalls WebSocket pings and all other concurrent coroutines while git runs.
**Do this instead:** `asyncio.create_subprocess_exec()` with `await proc.communicate()`. The existing `pipeline/runner.py` already uses this pattern for Claude CLI — same applies to git.

### Anti-Pattern 3: Reusing the HTML Jinja2Templates instance for .j2 scaffolding

**What people do:** Pass the `Jinja2Templates` object from `views.py` (or a shared instance) to the scaffolding code.
**Why it's wrong:** `Jinja2Templates` uses `Undefined` (silent) by default. A missing `{{ slug }}` in a template renders as empty string — silently corrupt scaffolding. Also wrong loader (points to HTML dir, not template dir).
**Do this instead:** Create a separate `jinja2.Environment(undefined=StrictUndefined, loader=FileSystemLoader(...))` scoped to the specific template directory. Fails loudly on missing variables. Never share environments across concerns.

### Anti-Pattern 4: Deleting the project folder on DELETE /projects/{id}

**What people do:** Implement `DELETE /projects/{id}` to `shutil.rmtree(project.path)`.
**Why it's wrong:** Irreversible data loss. A user who just unregisters a project from the console loses their entire codebase.
**Do this instead:** The spec is explicit — `DELETE /projects/{id}` removes only the DB record. Folder stays. Users delete folders manually if desired.

### Anti-Pattern 5: Making project_id optional with settings.project_path fallback

**What people do:** Keep `TaskCreate.project_id: Optional[int] = None` and fall back to `settings.project_path` when not provided.
**Why it's wrong:** Undermines the entire Project Router premise. Tasks would run in an untracked project context with no context enrichment.
**Do this instead:** `project_id` is required. Update existing tests to pass a valid project_id (create a test project fixture). The fallback behavior is eliminated in v2.1.

### Anti-Pattern 6: YAML registry as single source of truth for custom templates

**What people do:** Store all template metadata only in `registry.yaml`, without verifying the template directory exists.
**Why it's wrong:** Registry and filesystem can drift. A template in the registry with a missing directory causes a 500 on `GET /templates/{id}` or `POST /projects`.
**Do this instead:** On `GET /templates`, reconcile registry with filesystem — skip entries whose directory is missing (log a warning). On `POST /templates`, create directory first, then write to registry. On `DELETE /templates/{id}`, remove directory first, then remove from registry. Directory is the source of truth; registry is an index.

---

## Scaling Considerations

This is a single-user system. Scaling is operational, not traffic-driven.

| Scale | Architecture |
|-------|-------------|
| 1 user, current | asyncio.Semaphore(2), asyncpg pool size 5, in-memory ConnectionManager |
| 1 user, many projects | No change needed — project list is a simple `SELECT` + fast `scandir` |
| Context assembly on large repos | Already capped: 200 files, CLAUDE.md 2000 chars, 10 git commits, 5 recent tasks |
| Multi-user (future, out of scope) | Add `user_id` FK on projects+tasks; scope all queries; replace Basic Auth with JWT |

---

## Sources

All findings based on direct codebase analysis (HIGH confidence):

- `src/server/app.py` — lifespan, router wiring
- `src/server/routers/tasks.py` — TaskCreate model, create_task handler
- `src/server/routers/views.py` — Jinja2Templates usage, routes to remove
- `src/server/dependencies.py` — DI pattern for app.state extraction
- `src/server/config.py` — Settings structure, env prefix
- `src/db/pg_repository.py` — TaskRepository pattern to replicate
- `src/db/pg_schema.py` — existing DDL + dataclass pattern
- `src/db/migrations.py` — idempotent ALTER TABLE pattern
- `src/context/assembler.py` — current sync implementation to extend async
- `src/engine/manager.py` — TaskManager.submit() signature
- `docs/project-router-spec.md` — full 808-line design specification

---
*Architecture research for: AI Agent Console v2.1 Project Router integration*
*Researched: 2026-03-13*
