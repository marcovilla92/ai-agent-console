# Phase 16: Task-Project Integration - Research

**Researched:** 2026-03-14
**Domain:** FastAPI endpoint modification, prompt enrichment, database FK wiring
**Confidence:** HIGH

## Summary

Phase 16 is a focused integration phase that connects the existing task creation flow (POST /tasks) with the project system built in Phases 12-15. The work is entirely within existing code -- no new files or libraries are needed. The three changes are: (1) add optional `project_id` to `TaskCreate` and propagate it through `TaskManager.submit()` and `TaskRepository.create()`, (2) when `project_id` is present, call `assemble_full_context()` and prepend the result to the prompt before passing it to the pipeline, and (3) call `ProjectRepository.update_last_used()` when a task is created with a `project_id`.

All building blocks already exist. `assemble_full_context()` works (Phase 14), `ProjectRepository.update_last_used()` works (Phase 12), and the `tasks.project_id` FK column already exists in the schema (Phase 12). The remaining work is wiring these together in the task creation path.

**Primary recommendation:** Modify 3 files (tasks.py router, manager.py, pg_repository.py) with minimal, backward-compatible changes. Keep context formatting as a simple string concatenation function in the router or a small helper.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TASK-11 | TaskCreate accepts optional project_id, falls back to settings.project_path | Add `project_id: Optional[int] = None` to TaskCreate model. When present, look up project to get its path; when absent, use `settings.project_path` as today. |
| TASK-12 | Task creation prepends assembled project context to prompt | Call `assemble_full_context(project.path, pool)` and format the dict into a string prefix prepended to the user's prompt before calling `manager.submit()`. |
| TASK-13 | Task creation updates project last_used_at | Call `ProjectRepository.update_last_used(project_id)` in the create_task handler after successful task submission. |
</phase_requirements>

## Standard Stack

### Core (already installed, no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | existing | REST framework | Already in use |
| asyncpg | existing | PostgreSQL driver | Already in use |
| Pydantic | existing | Request/response models | Already in use |

### Supporting (already available)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| src.context.assembler | Phase 14 | assemble_full_context() | When project_id is provided |
| src.db.pg_repository | Phase 12 | ProjectRepository.get(), update_last_used() | Project lookup and timestamp update |
| src.pipeline.events | Phase 15 | emit_event() | Already wired in TaskManager |

**Installation:** None needed -- all dependencies already present.

## Architecture Patterns

### Recommended Change Structure
```
src/
  server/
    routers/
      tasks.py           # MODIFY: Add project_id to TaskCreate, lookup project, prepend context, update last_used
  engine/
    manager.py           # MODIFY: Accept project_id in submit(), pass to Task and TaskRepository
  db/
    pg_repository.py     # MODIFY: Include project_id in TaskRepository.create() INSERT
```

### Pattern 1: Optional Field with Fallback
**What:** TaskCreate gains `project_id: Optional[int] = None`. When None, behavior is identical to today (uses settings.project_path). When provided, the project's path replaces settings.project_path.
**When to use:** This is the only approach -- backward compatibility is a hard requirement.
**Example:**
```python
# In TaskCreate model
class TaskCreate(BaseModel):
    prompt: str
    mode: str = "autonomous"
    project_id: Optional[int] = None  # NEW

# In create_task handler
@task_router.post("", status_code=201, response_model=TaskResponse)
async def create_task(
    body: TaskCreate,
    manager: TaskManager = Depends(get_task_manager),
    pool: asyncpg.Pool = Depends(get_pool),
):
    settings = get_settings()
    prompt = body.prompt
    project_path = settings.project_path

    if body.project_id is not None:
        repo = ProjectRepository(pool)
        project = await repo.get(body.project_id)
        if project is None:
            raise HTTPException(404, detail="Project not found")
        project_path = project.path

        # TASK-12: Prepend assembled context
        context = await assemble_full_context(project.path, pool)
        prompt = format_context_prefix(context) + "\n\n" + body.prompt

        # TASK-13: Update last_used_at
        await repo.update_last_used(body.project_id)

    task_id = await manager.submit(
        prompt=prompt,
        mode=body.mode,
        project_path=project_path,
        project_id=body.project_id,
    )
    ...
```

### Pattern 2: Context Formatting as Helper Function
**What:** A small `format_context_prefix()` function that turns the assemble_full_context dict into a readable string for prompt prepending.
**When to use:** Keeps the router handler clean; the formatting logic is isolated and testable.
**Example:**
```python
def format_context_prefix(ctx: dict) -> str:
    """Format assembled context dict into a string prefix for prompt injection."""
    parts = []
    if ctx.get("workspace"):
        parts.append(ctx["workspace"])
    if ctx.get("claude_md"):
        parts.append(f"=== CLAUDE.md ===\n{ctx['claude_md']}")
    if ctx.get("planning_docs"):
        for name, content in ctx["planning_docs"].items():
            parts.append(f"=== {name} ===\n{content}")
    if ctx.get("git_log"):
        parts.append(f"=== Recent Commits ===\n{ctx['git_log']}")
    if ctx.get("recent_tasks"):
        task_lines = [f"  #{t['id']} [{t['status']}] {t['prompt']}" for t in ctx["recent_tasks"]]
        parts.append(f"=== Recent Tasks ===\n" + "\n".join(task_lines))
    return "\n\n".join(parts)
```

### Pattern 3: project_id Propagation Through TaskManager
**What:** `TaskManager.submit()` already accepts `project_path`. Add `project_id: Optional[int] = None` parameter. Pass it to the `Task` dataclass and include it in the `TaskRepository.create()` INSERT.
**Example:**
```python
# manager.py - submit method signature change
async def submit(
    self, prompt: str, mode: str = "autonomous",
    project_path: str = ".", project_id: Optional[int] = None,
) -> int:
    task = Task(
        name=prompt[:50],
        project_path=project_path,
        created_at=now,
        status="queued",
        mode=mode,
        prompt=prompt,
        project_id=project_id,  # NEW
    )
    ...

# pg_repository.py - TaskRepository.create() change
async def create(self, task: Task) -> int:
    return await self._pool.fetchval(
        "INSERT INTO tasks (name, project_path, created_at, status, mode, prompt, project_id) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id",
        task.name, task.project_path, task.created_at,
        task.status, task.mode, task.prompt, task.project_id,
    )
```

### Anti-Patterns to Avoid
- **Modifying TaskManager._execute to do context assembly:** Context should be assembled in the router layer before submission, not deep in the engine. The engine just runs the prompt it receives.
- **Making project_id required:** This breaks backward compatibility. The spec demands optional with fallback.
- **Storing enriched prompt in DB:** Store only the original user prompt. The context enrichment is ephemeral -- it's prepended to what Claude sees but the DB stores the user's original prompt for display purposes.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Context assembly | Custom file reading | `assemble_full_context()` | Already built in Phase 14, handles all 5 sources with truncation |
| last_used_at update | Raw SQL in router | `ProjectRepository.update_last_used()` | Already built in Phase 12, uses NOW() |
| Project lookup | Custom query | `ProjectRepository.get()` | Already returns Optional[Project], handles None case |

## Common Pitfalls

### Pitfall 1: Breaking Existing Tests
**What goes wrong:** Changing `TaskRepository.create()` SQL without updating the parameter count breaks all task creation tests.
**Why it happens:** The INSERT statement is positional ($1, $2, ... $7) and all existing tests create tasks via the API.
**How to avoid:** Add project_id as the LAST column in the INSERT. Since `Task.project_id` defaults to None, it passes NULL for existing tasks. Run full test suite after change.
**Warning signs:** Any test_task_endpoints test failing.

### Pitfall 2: Context Assembly Failure Blocking Task Creation
**What goes wrong:** If assemble_full_context() throws (e.g., filesystem permission, git timeout), task creation fails entirely.
**Why it happens:** Project path may not exist on disk, or git may hang.
**How to avoid:** Wrap context assembly in try/except -- if it fails, log a warning and proceed with the original prompt only. Task creation should never fail because context assembly failed.
**Warning signs:** 500 errors on POST /tasks when project_id is provided.

### Pitfall 3: Prompt vs Enriched Prompt Confusion
**What goes wrong:** Storing the enriched prompt (context + user prompt) in the DB makes the task list display context noise instead of the user's original prompt.
**Why it happens:** Using the same variable for both the DB prompt and the pipeline prompt.
**How to avoid:** Keep two separate variables: `original_prompt` (stored in DB, displayed in UI) and `enriched_prompt` (sent to Claude only). Pass `enriched_prompt` to `orchestrate_pipeline` but store `original_prompt` in the Task record.
**Warning signs:** Task list showing workspace context dumps.

### Pitfall 4: TaskResponse Missing project_id
**What goes wrong:** The existing TaskResponse model doesn't include project_id, so the frontend can't tell which project a task belongs to.
**Why it happens:** TaskResponse was defined before projects existed.
**How to avoid:** Add `project_id: Optional[int] = None` to TaskResponse model.

## Code Examples

### Current Task Creation Flow (for reference)
```python
# tasks.py create_task handler (current)
settings = get_settings()
task_id = await manager.submit(
    prompt=body.prompt,
    mode=body.mode,
    project_path=settings.project_path,  # Always from settings
)
```

### TaskRepository.create() Current SQL
```python
# Current -- 6 params, no project_id
"INSERT INTO tasks (name, project_path, created_at, status, mode, prompt) "
"VALUES ($1, $2, $3, $4, $5, $6) RETURNING id"
```

### TaskRepository.create() After Change
```python
# After -- 7 params, project_id added
"INSERT INTO tasks (name, project_path, created_at, status, mode, prompt, project_id) "
"VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id",
task.name, task.project_path, task.created_at,
task.status, task.mode, task.prompt, task.project_id,
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single project_path from settings | project_id selects project, falls back to settings | Phase 16 | Tasks become project-aware |
| Bare prompt to Claude | Context-enriched prompt when project selected | Phase 16 | Claude has project context |

## Open Questions

1. **Should enriched prompt be stored separately?**
   - What we know: The spec says store original prompt for display, send enriched to Claude.
   - What's unclear: Should we add an `enriched_prompt` column for debugging? Probably not -- adds complexity.
   - Recommendation: Keep it simple. Store original prompt only. Enriched prompt is transient.

2. **MAX_CONTEXT_CHARS enforcement on enriched prompt**
   - What we know: `assemble_full_context()` already respects individual limits (2000 for CLAUDE.md, 500 per planning doc, etc.)
   - What's unclear: Should the total formatted prefix be capped at 6000 chars?
   - Recommendation: Yes, truncate the formatted prefix to MAX_CONTEXT_CHARS to match the existing cap.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | pyproject.toml (existing) |
| Quick run command | `pytest tests/test_task_endpoints.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TASK-11 | POST /tasks with project_id creates task using project path | integration | `pytest tests/test_task_endpoints.py::test_post_tasks_with_project_id -x` | No -- Wave 0 |
| TASK-11 | POST /tasks without project_id still uses settings.project_path | integration | `pytest tests/test_task_endpoints.py::test_post_tasks_without_project_id -x` | Existing tests cover this |
| TASK-11 | POST /tasks with invalid project_id returns 404 | integration | `pytest tests/test_task_endpoints.py::test_post_tasks_invalid_project_id -x` | No -- Wave 0 |
| TASK-12 | Task prompt is enriched with project context when project_id given | integration | `pytest tests/test_task_endpoints.py::test_post_tasks_context_prepended -x` | No -- Wave 0 |
| TASK-13 | last_used_at is updated when task created with project_id | integration | `pytest tests/test_task_endpoints.py::test_post_tasks_updates_last_used -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_task_endpoints.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before verify

### Wave 0 Gaps
- [ ] `tests/test_task_endpoints.py` -- add 4 new test functions for TASK-11/12/13 (file exists, tests are additive)
- [ ] Test helper to create a project record in DB before task creation tests

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: `src/server/routers/tasks.py`, `src/engine/manager.py`, `src/db/pg_repository.py`, `src/db/pg_schema.py`
- Direct codebase inspection: `src/context/assembler.py` (assemble_full_context implementation)
- Direct codebase inspection: `src/pipeline/project_service.py` (ProjectService, ProjectRepository usage)
- Direct codebase inspection: `tests/test_task_endpoints.py` (existing test patterns)

### Secondary (MEDIUM confidence)
- Design spec: `docs/project-router-spec.md` (describes the intended integration)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all code exists
- Architecture: HIGH - straightforward wiring of existing components, 3 files changed
- Pitfalls: HIGH - identified from direct code reading, well-understood patterns

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (stable codebase, no external dependencies involved)
