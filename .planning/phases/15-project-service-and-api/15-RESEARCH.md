# Phase 15: Project Service and API - Research

**Researched:** 2026-03-13
**Domain:** Project CRUD API, filesystem scaffolding, event system, auto-scan registration
**Confidence:** HIGH

## Summary

Phase 15 builds the core project management API on top of the DB foundation (Phase 12), template system (Phase 13), and context assembly (Phase 14). The existing `projects.py` router currently only exposes context/phase-suggestion endpoints. This phase adds GET (list with auto-scan), POST (create from template with scaffolding + git init), and DELETE (DB-only) endpoints, plus a new `ProjectService` class as the business logic layer, and an `emit_event()` no-op stub for future webhook integration.

All building blocks already exist: `ProjectRepository` has full CRUD, `create_project()` handles folder creation and name sanitization, templates are on disk with a registry, the `assemble_workspace_context()` function detects stack from indicator files. The primary new work is: (1) a `ProjectService` that orchestrates template rendering + folder scaffolding + git init + DB insert, (2) auto-scan of ~/projects/ with ON CONFLICT upsert, (3) the event system stub, and (4) wiring the new endpoints into the existing router.

**Primary recommendation:** Create a single `src/pipeline/project_service.py` with `ProjectService` class, a separate `src/pipeline/events.py` for the event enum + emit_event() stub, extend the existing `projects.py` router with list/create/delete endpoints, and add an `upsert_by_path` method to `ProjectRepository` for ON CONFLICT safety.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PROJ-01 | GET /projects lists all projects with auto-scan of ~/projects/ | ProjectService.list_projects() scans filesystem, reconciles with DB via upsert_by_path, returns enriched list with stack detection |
| PROJ-02 | POST /projects creates project from template with folder scaffolding + git init | ProjectService.create_project() uses existing create_project() + Jinja2 template rendering + asyncio git subprocess + ProjectRepository.insert() |
| PROJ-03 | DELETE /projects/{id} removes DB record without touching filesystem | Simple ProjectRepository.delete() call, already implemented |
| PROJ-04 | Auto-register untracked folders with ON CONFLICT safety | New ProjectRepository.upsert_by_path() using INSERT ... ON CONFLICT (path) DO NOTHING |
| PROJ-05 | Project list shows detected stack and last_used_at | assemble_workspace_context() already detects stack via STACK_INDICATORS; extract detect_stack() as reusable function |
| EVT-01 | emit_event() no-op stub at 6 lifecycle points | New src/pipeline/events.py with ProjectEvent enum and async emit_event() that logs and returns |
</phase_requirements>

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | existing | REST endpoints | Already used for all routers |
| asyncpg | existing | PostgreSQL operations | Already used for all DB access |
| Pydantic | existing | Request/response models | Already used in all routers |
| Jinja2 | existing | Template rendering (.j2 files) | Already a dependency (used by views.py) |

### Supporting (already in project)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pathlib | stdlib | Filesystem operations | Template scaffolding, directory scanning |
| asyncio | stdlib | subprocess for git init | Already used pattern in get_recent_git_log() |
| re | stdlib | Name sanitization | Already used in create_project() |
| logging | stdlib | Event emission logging | Standard Python logging |
| enum | stdlib | ProjectEvent enum | Event type definition |

### No New Dependencies Needed
Everything required is already installed. No `pip install` needed.

## Architecture Patterns

### Recommended Project Structure (new/modified files only)
```
src/
  pipeline/
    project_service.py     # NEW: ProjectService business logic
    events.py              # NEW: ProjectEvent enum + emit_event() stub
    project.py             # MODIFY: extract detect_stack(), add scaffold_from_template()
  server/
    routers/
      projects.py          # MODIFY: add GET /projects, POST /projects, DELETE /projects/{id}
  db/
    pg_repository.py       # MODIFY: add ProjectRepository.upsert_by_path()
```

### Pattern 1: ProjectService as Business Logic Layer
**What:** A service class that coordinates between the router, repository, filesystem, and template system.
**When to use:** When an endpoint needs multi-step orchestration (create folder -> render templates -> git init -> DB insert -> emit event).
**Example:**
```python
class ProjectService:
    WORKSPACE_ROOT = Path.home() / "projects"

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._repo = ProjectRepository(pool)

    async def create_project(self, name: str, description: str = "", template: str = "blank") -> Project:
        slug = sanitize_project_name(name)
        path = str(self.WORKSPACE_ROOT / slug)
        # 1. Create folder from template
        # 2. git init + initial commit
        # 3. Insert DB record
        # 4. emit_event(PROJECT_CREATED, ...)
        return project

    async def list_projects(self) -> list[dict]:
        # 1. Scan ~/projects/ for untracked folders
        # 2. Auto-register with ON CONFLICT
        # 3. Return enriched list with detected stack
        pass

    async def delete_project(self, project_id: int) -> None:
        # 1. Delete from DB only
        # 2. emit_event(PROJECT_DELETED, ...)
        pass
```

### Pattern 2: ON CONFLICT Upsert for Auto-Registration
**What:** INSERT ... ON CONFLICT (path) DO NOTHING to safely register folders that may already exist in DB.
**When to use:** During auto-scan, multiple concurrent requests could try to register the same folder.
**Example:**
```python
async def upsert_by_path(self, project: Project) -> Optional[int]:
    """Insert a project if its path doesn't exist, return id or None if already exists."""
    return await self._pool.fetchval(
        "INSERT INTO projects (name, slug, path, description, created_at) "
        "VALUES ($1, $2, $3, $4, $5) "
        "ON CONFLICT (path) DO NOTHING "
        "RETURNING id",
        project.name, project.slug, project.path,
        project.description, project.created_at,
    )
```

### Pattern 3: Template Scaffolding with Jinja2
**What:** Copy template files to new project directory, rendering .j2 files with project variables.
**When to use:** POST /projects with a template_id.
**Example:**
```python
from jinja2 import Template

def scaffold_from_template(template_dir: Path, target_dir: Path, context: dict) -> None:
    """Copy template files to target, rendering .j2 files."""
    for src_file in template_dir.rglob("*"):
        if not src_file.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in src_file.parts):
            continue
        rel = src_file.relative_to(template_dir)
        if src_file.suffix == ".j2":
            # Render and write without .j2 extension
            dest = target_dir / str(rel)[:-3]  # strip .j2
            dest.parent.mkdir(parents=True, exist_ok=True)
            content = Template(src_file.read_text()).render(**context)
            dest.write_text(content)
        else:
            dest = target_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest)
```

### Pattern 4: Async Git Init with Timeout
**What:** Run `git init` and `git commit` as async subprocess with timeout.
**When to use:** After scaffolding a new project.
**Example:**
```python
async def git_init_project(project_path: str) -> None:
    """Initialize git repo with initial commit. 10s timeout."""
    async def _run(cmd: list[str]) -> None:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10.0)

    await _run(["git", "init"])
    await _run(["git", "add", "."])
    await _run(["git", "-c", "user.name=Console", "-c", "user.email=console@local",
                "commit", "-m", "Initial scaffolding"])
```

### Pattern 5: Event System No-Op Stub
**What:** Enum-based event types with async emit function that only logs.
**When to use:** At 6 lifecycle points as specified in EVT-01.
**Example:**
```python
from enum import Enum

class ProjectEvent(str, Enum):
    PROJECT_CREATED = "project.created"
    PROJECT_DELETED = "project.deleted"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    PHASE_SUGGESTED = "phase.suggested"

async def emit_event(event: ProjectEvent, payload: dict) -> None:
    """No-op placeholder for future webhook integration.
    Logs event at DEBUG level. Will POST to n8n in v2.2."""
    log.debug("Event %s: %s", event.value, payload)
```

### Anti-Patterns to Avoid
- **Scanning filesystem on every request without caching:** The auto-scan on GET /projects is fine for single-user, but avoid scanning inside loops. Scan once per request.
- **Blocking git subprocess:** Always use asyncio.create_subprocess_exec, never subprocess.run. Follow the existing pattern in get_recent_git_log().
- **Deleting filesystem on project delete:** The spec is explicit -- DELETE removes DB record only, filesystem stays.
- **Rendering .j2 files with user-controlled template strings:** Use Jinja2's `Template()` class on file content read from the template directory, never from user input.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Jinja2 template rendering | String format/replace | `jinja2.Template().render()` | Already a dependency, handles escaping, conditionals |
| Project name to slug | Custom regex | Existing `sanitize_project_name()` in src/pipeline/project.py | Already tested, handles edge cases |
| Stack detection | New detection logic | Extract from existing `assemble_workspace_context()` | STACK_INDICATORS dict already maps files to stacks |
| Git subprocess | subprocess.run | asyncio.create_subprocess_exec | Matches existing pattern, non-blocking |
| SQL upsert | SELECT then INSERT | ON CONFLICT clause | Race-condition safe, atomic |

## Common Pitfalls

### Pitfall 1: Race Condition on Auto-Registration
**What goes wrong:** Two concurrent GET /projects requests both scan ~/projects/, both try to INSERT the same untracked folder.
**Why it happens:** No locking between scan and insert.
**How to avoid:** Use `INSERT ... ON CONFLICT (path) DO NOTHING`. The `path` column already has a UNIQUE constraint.
**Warning signs:** IntegrityError / UniqueViolation exceptions in logs.

### Pitfall 2: Git Identity in Docker
**What goes wrong:** `git commit` fails with "Please tell me who you are" inside Docker container.
**Why it happens:** No git config user.name/user.email set in Docker.
**How to avoid:** Pass `-c user.name=Console -c user.email=console@local` flags to git commit command. Already noted in STATE.md blockers.
**Warning signs:** git commit returns non-zero exit code.

### Pitfall 3: Template Path Resolution in Docker
**What goes wrong:** Template directory not found when running in Docker.
**Why it happens:** Working directory differs between dev and Docker.
**How to avoid:** Use `Path(__file__).resolve()` pattern (already used in templates.py). Import TEMPLATES_ROOT from templates module rather than computing independently.
**Warning signs:** FileNotFoundError on template operations.

### Pitfall 4: Existing Router Route Conflicts
**What goes wrong:** New GET /projects endpoint conflicts with existing GET /projects/{project_id}/context.
**Why it happens:** Both routes on same prefix.
**How to avoid:** FastAPI handles this correctly if the parameter-less route (GET /projects) is defined before parameterized routes. Alternatively, ensure routes are unambiguous.
**Warning signs:** Wrong endpoint being called.

### Pitfall 5: Filesystem Permissions in Docker
**What goes wrong:** Cannot create project folders in ~/projects/ inside Docker.
**Why it happens:** Docker container runs as non-root user (per recent commit c63f32a).
**How to avoid:** Ensure WORKSPACE_ROOT exists and is writable. Use `mkdir(parents=True, exist_ok=True)`. Consider making WORKSPACE_ROOT configurable via settings.
**Warning signs:** PermissionError on folder creation.

### Pitfall 6: Git Subprocess Timeout
**What goes wrong:** git init hangs forever, blocking the event loop.
**Why it happens:** No timeout on subprocess.
**How to avoid:** Use `asyncio.wait_for(proc.communicate(), timeout=10.0)` -- same pattern as get_recent_git_log() which uses 5s timeout. Use 10s for init+add+commit sequence.
**Warning signs:** Request never completes.

## Code Examples

### Existing Pattern: Router with Auth + Pool (from projects.py)
```python
project_router = APIRouter(
    prefix="/projects",
    tags=["projects"],
    dependencies=[Depends(verify_credentials)],
)

@project_router.get("/{project_id}/context", response_model=ContextResponse)
async def get_project_context(
    project_id: int,
    pool: asyncpg.Pool = Depends(get_pool),
):
    repo = ProjectRepository(pool)
    project = await repo.get(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, ...)
    ...
```

### Existing Pattern: Stack Detection (from assembler.py)
```python
STACK_INDICATORS: dict[str, list[str]] = {
    "Python": ["requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"],
    "Node.js": ["package.json"],
    "Rust": ["Cargo.toml"],
    "Go": ["go.mod"],
    "Java": ["pom.xml", "build.gradle"],
    "Ruby": ["Gemfile"],
    "Docker": ["Dockerfile", "docker-compose.yml"],
}
# Used in assemble_workspace_context() -- extract as detect_stack(path) -> str
```

### Existing Pattern: Project Creation (from project.py)
```python
def create_project(name: str, workspace_root: str) -> str:
    dir_name = sanitize_project_name(name)
    project_path = Path(workspace_root) / dir_name
    if project_path.exists():
        raise FileExistsError(f"Project folder already exists: {project_path}")
    project_path.mkdir(parents=True)
    (project_path / "src").mkdir()
    return str(project_path)
```

### Existing Pattern: Async Git (from assembler.py)
```python
proc = await asyncio.create_subprocess_exec(
    "git", "log", "--oneline", "--no-pager", f"-{count}",
    cwd=project_path,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
```

### New: Response Models Needed
```python
class ProjectSummary(BaseModel):
    id: int
    name: str
    slug: str
    path: str
    description: str
    stack: str  # detected from filesystem
    created_at: datetime
    last_used_at: datetime | None

class ProjectListResponse(BaseModel):
    projects: list[ProjectSummary]
    count: int

class ProjectCreateRequest(BaseModel):
    name: str
    description: str = ""
    template: str = "blank"

class ProjectCreateResponse(BaseModel):
    id: int
    name: str
    slug: str
    path: str
    description: str
    created_at: datetime
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single project_path in settings | Multi-project with DB tracking | v2.1 (Phase 12) | Projects table + FK on tasks |
| Manual folder creation | Template-based scaffolding | v2.1 (Phase 13) | 4 builtin templates ready |
| No context assembly | Full context from 5 sources | v2.1 (Phase 14) | assemble_full_context() ready |

**Key codebase facts:**
- `projects.py` router already exists with prefix `/projects` and auth -- just add new endpoints to it
- `ProjectRepository` has insert, get, list_all, delete, update_last_used -- needs upsert_by_path
- `create_project()` creates folder + src/ only -- needs template scaffolding layer on top
- STACK_INDICATORS in assembler.py needs to be extracted as reusable `detect_stack()` function
- `TEMPLATES_ROOT` is computed in templates.py via `Path(__file__).resolve()` -- import from there
- TaskManager._execute() is where task.started/completed/failed events should be emitted
- suggest_next_phase() in assembler.py is where phase.suggested event should be emitted

## Open Questions

1. **WORKSPACE_ROOT configurability**
   - What we know: The spec hardcodes `Path.home() / "projects"`. Docker container runs as non-root user.
   - What's unclear: Should WORKSPACE_ROOT come from settings (APP_WORKSPACE_ROOT env var)?
   - Recommendation: Default to `Path.home() / "projects"` but accept override from Settings for Docker flexibility. Low risk either way.

2. **Auto-scan exclusion patterns**
   - What we know: spec says "Ignora: .git, node_modules, file (non directory)" for scan_and_register.
   - What's unclear: Should we exclude hidden directories (e.g., .cache, .local)?
   - Recommendation: Only scan top-level directories in ~/projects/ (not recursive). Skip entries that are not directories. This matches the spec and is simplest.

3. **Event emission in TaskManager**
   - What we know: EVT-01 requires emit_event at task.started, task.completed, task.failed.
   - What's unclear: TaskManager is in src/engine/manager.py. Adding import of events.py creates a cross-module dependency.
   - Recommendation: The dependency is fine -- events.py is a simple module with no imports. Add emit_event calls in TaskManager._execute() method.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | pyproject.toml (pytest section) |
| Quick run command | `python -m pytest tests/test_project_service.py -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROJ-01 | GET /projects returns list with auto-scan | integration | `python -m pytest tests/test_project_service.py::TestListProjects -x` | Wave 0 |
| PROJ-02 | POST /projects creates from template + git init | integration | `python -m pytest tests/test_project_service.py::TestCreateProject -x` | Wave 0 |
| PROJ-03 | DELETE /projects/{id} removes DB record only | integration | `python -m pytest tests/test_project_service.py::TestDeleteProject -x` | Wave 0 |
| PROJ-04 | Auto-register with ON CONFLICT safety | unit | `python -m pytest tests/test_project_service.py::TestAutoRegister -x` | Wave 0 |
| PROJ-05 | Project list shows detected stack | unit | `python -m pytest tests/test_project_service.py::TestDetectStack -x` | Wave 0 |
| EVT-01 | emit_event() stub called at lifecycle points | unit | `python -m pytest tests/test_project_service.py::TestEvents -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_project_service.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before /gsd:verify-work

### Wave 0 Gaps
- [ ] `tests/test_project_service.py` -- covers PROJ-01 through PROJ-05, EVT-01
- [ ] No new fixtures needed -- existing `pg_pool`, `app_with_pool`, `tmp_path` patterns sufficient

## Sources

### Primary (HIGH confidence)
- Direct code inspection of src/db/pg_repository.py (ProjectRepository)
- Direct code inspection of src/db/pg_schema.py (Project dataclass, PROJECTS_DDL)
- Direct code inspection of src/pipeline/project.py (create_project, sanitize_project_name)
- Direct code inspection of src/context/assembler.py (STACK_INDICATORS, assemble_workspace_context)
- Direct code inspection of src/server/routers/projects.py (existing router structure)
- Direct code inspection of src/server/routers/templates.py (TEMPLATES_ROOT, Jinja2 patterns)
- Direct code inspection of src/engine/manager.py (TaskManager._execute lifecycle)
- docs/project-router-spec.md (design specification with full API/DB/UX details)

### Secondary (MEDIUM confidence)
- PostgreSQL ON CONFLICT documentation (well-known pattern, verified in PROJECTS_DDL UNIQUE constraints)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already in use, no new dependencies
- Architecture: HIGH - extends existing patterns (router, repository, service), all building blocks inspected
- Pitfalls: HIGH - based on existing codebase decisions (STATE.md blockers) and Docker deployment history
- Events: HIGH - spec defines exact interface, no-op implementation is trivial

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (stable codebase, no external dependency changes)
