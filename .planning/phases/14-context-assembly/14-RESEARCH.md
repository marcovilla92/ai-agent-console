# Phase 14: Context Assembly - Research

**Researched:** 2026-03-13
**Domain:** File I/O, async subprocess (git), PostgreSQL queries, text truncation, REST API
**Confidence:** HIGH

## Summary

Phase 14 builds two new capabilities on top of the existing codebase: (1) a context assembler that gathers information from 5 sources (workspace summary, CLAUDE.md, .planning/ docs, git log, recent tasks) into a single bounded output, and (2) a phase suggestion engine that parses STATE.md and ROADMAP.md to identify the next actionable phase. Both are exposed via REST endpoints on the existing project entity from Phase 12.

This is a pure Python phase with no new dependencies. The existing `assemble_workspace_context()` in `src/context/assembler.py` provides the workspace summary. The new code adds file reading with truncation, async git subprocess calls (following the pattern in `src/git/autocommit.py`), a database query for recent tasks, and simple text parsing for phase suggestion. Two new endpoints mount on an APIRouter following the established pattern from `src/server/routers/templates.py`.

**Primary recommendation:** Implement as a single module `src/context/assembler.py` (extend existing file) with `assemble_full_context()` and `suggest_next_phase()`, plus a new router `src/server/routers/projects.py` with two GET endpoints. Use `asyncio.wait_for()` with timeout on git subprocess calls since this runs in Docker.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CTX-01 | assemble_full_context() returns workspace + CLAUDE.md (2000 chars) + .planning/ docs (500 chars each) + git log (10 commits) + 5 recent tasks | Architecture pattern: extend assembler.py with 5 helper functions, each returning bounded text. MAX_CONTEXT_CHARS=6000 cap enforced at assembly level. |
| CTX-02 | GET /projects/{id}/context returns assembled context | New projects router with get_pool + ProjectRepository.get() to resolve path, then call assemble_full_context() |
| CTX-03 | Phase suggestion engine parses STATE.md/ROADMAP.md to suggest next phase | suggest_next_phase() uses regex/string parsing on STATE.md "Phase:" line and ROADMAP.md checkbox patterns |
| CTX-04 | GET /projects/{id}/suggested-phase returns phase suggestion | Same router, second endpoint calling suggest_next_phase(project.path) |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncpg | (existing) | Query recent tasks from DB | Already used by all repositories |
| asyncio | stdlib | Subprocess for git log | Already used in src/git/autocommit.py |
| pathlib | stdlib | File reading with Path objects | Already used throughout codebase |
| re | stdlib | Parse STATE.md/ROADMAP.md patterns | Lightweight text extraction |
| FastAPI | (existing) | REST endpoints | Already the web framework |
| Pydantic | (existing) | Response models | Already used for all API responses |

### Supporting
No new dependencies needed. Everything is stdlib or already installed.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| regex parsing for phase suggestion | YAML/TOML parser | STATE.md and ROADMAP.md are markdown, not structured data -- regex is simpler and correct |
| asyncio.create_subprocess_exec for git | GitPython library | Adds a dependency; the existing autocommit.py already proves the subprocess pattern works in this codebase |

## Architecture Patterns

### Recommended Project Structure
```
src/context/assembler.py        # EXTEND: add assemble_full_context(), suggest_next_phase(), helpers
src/server/routers/projects.py  # NEW: GET /projects/{id}/context, GET /projects/{id}/suggested-phase
src/server/app.py               # MODIFY: include project_router
```

### Pattern 1: Bounded Text Extraction
**What:** Each context source has a hard character limit. Truncation uses `text[:limit]` with a trailing `\n...[truncated]` marker when exceeded.
**When to use:** Every file-read helper function.
**Example:**
```python
MAX_CLAUDE_MD_CHARS = 2000
MAX_PLANNING_DOC_CHARS = 500
MAX_CONTEXT_CHARS = 6000

def read_file_truncated(project_path: str, rel_path: str, max_chars: int) -> str:
    """Read a file, truncating to max_chars. Returns empty string if missing."""
    target = Path(project_path) / rel_path
    if not target.is_file():
        return ""
    text = target.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + "\n...[truncated]"
    return text
```

### Pattern 2: Async Git Subprocess with Timeout
**What:** Run `git log --oneline -10` as async subprocess with `asyncio.wait_for()` timeout.
**When to use:** Docker containers where git may not be configured or repo may not exist.
**Example:**
```python
async def get_recent_git_log(project_path: str, count: int = 10) -> str:
    """Return recent git log as string. Returns empty on error/timeout."""
    git_dir = Path(project_path) / ".git"
    if not git_dir.exists():
        return ""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "log", f"--oneline", f"-{count}",
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        return stdout.decode("utf-8", errors="replace").strip()
    except (asyncio.TimeoutError, Exception):
        return ""
```

### Pattern 3: Router with Pool Dependency (existing pattern)
**What:** New router follows the exact pattern of templates.py and tasks.py -- APIRouter with prefix, auth dependency, pool from request.
**Example:**
```python
project_router = APIRouter(
    prefix="/projects",
    tags=["projects"],
    dependencies=[Depends(verify_credentials)],
)

@project_router.get("/{project_id}/context")
async def get_project_context(
    project_id: int,
    pool: asyncpg.Pool = Depends(get_pool),
):
    repo = ProjectRepository(pool)
    project = await repo.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    context = await assemble_full_context(project.path, pool)
    return context
```

### Pattern 4: STATE.md / ROADMAP.md Parsing for Phase Suggestion
**What:** Parse known markdown patterns to extract current phase and find the next incomplete phase.
**When to use:** suggest_next_phase() function.
**Key patterns to parse:**
- STATE.md: `Phase: NN of NN (Phase Name)` line under `## Current Position`
- ROADMAP.md: `- [ ] **Phase NN: Name**` (incomplete) vs `- [x] **Phase NN: Name**` (complete)
- `.planning/phases/` directory: scan for phases without a `*-SUMMARY.md` file

```python
async def suggest_next_phase(project_path: str) -> dict | None:
    """Parse STATE.md and ROADMAP.md to suggest next phase."""
    planning = Path(project_path) / ".planning"
    if not planning.is_dir():
        return None

    # 1. Parse ROADMAP.md for incomplete phases
    roadmap = planning / "ROADMAP.md"
    if not roadmap.is_file():
        return None

    text = roadmap.read_text(encoding="utf-8", errors="replace")
    # Find all phase lines: - [ ] **Phase NN: Name** or - [x] **Phase NN: Name**
    import re
    phases = []
    for m in re.finditer(
        r"- \[([ x])\] \*\*Phase (\d+): (.+?)\*\*", text
    ):
        done = m.group(1) == "x"
        phases.append({
            "phase_id": m.group(2),
            "phase_name": m.group(3),
            "status": "complete" if done else "pending",
        })

    # 2. Find first incomplete phase
    next_phase = next((p for p in phases if p["status"] != "complete"), None)
    if next_phase:
        next_phase["reason"] = f"First incomplete phase in roadmap"

    return {
        "suggestion": next_phase,
        "all_phases": phases,
    }
```

### Anti-Patterns to Avoid
- **Reading entire large files into memory without limits:** Always use the truncation pattern. A CLAUDE.md could theoretically be very large.
- **Blocking I/O in async handlers:** File reads are fast enough for the file sizes involved (< 6KB total), but git subprocess MUST be async with timeout.
- **Hard-coding project paths in tests:** Use `tmp_path` fixture and create test fixtures on disk.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Workspace scanning | Custom file walker | Existing `assemble_workspace_context()` | Already implemented, tested, and handles exclusions |
| Git operations | Direct subprocess management | Follow `src/git/autocommit.py` pattern | Proven async subprocess pattern with error handling |
| Auth on endpoints | Custom auth logic | `Depends(verify_credentials)` | Existing dependency injection, used by all routers |
| Project lookup | Direct SQL | `ProjectRepository.get()` | Already implemented in Phase 12 |

## Common Pitfalls

### Pitfall 1: Git subprocess hanging in Docker
**What goes wrong:** `git log` hangs if git is not configured or the working directory has issues.
**Why it happens:** Docker containers may have minimal git config; some edge cases cause git to prompt for input.
**How to avoid:** Always use `asyncio.wait_for()` with a 5-second timeout. Add `--no-pager` flag. Return empty string on any error.
**Warning signs:** Endpoint hangs indefinitely, async task never completes.

### Pitfall 2: .planning/ directory doesn't exist
**What goes wrong:** `suggest_next_phase()` or `read_planning_docs()` crashes with FileNotFoundError.
**Why it happens:** Not all projects have a `.planning/` directory -- only GSD-managed ones do.
**How to avoid:** Always check `.is_dir()` / `.is_file()` before reading. Return empty/None gracefully.
**Warning signs:** 500 errors on context endpoint for projects without planning docs.

### Pitfall 3: MAX_CONTEXT_CHARS budget exceeded
**What goes wrong:** Combined context exceeds 6000 chars, inflating prompt costs.
**Why it happens:** Each section uses its own limit independently; combined they can exceed the global cap.
**How to avoid:** Apply individual limits first (2000 for CLAUDE.md, 500 per planning doc, etc.), then apply a final `MAX_CONTEXT_CHARS = 6000` truncation on the assembled output. Budget: workspace ~500 + claude_md 2000 + planning 1500 (3 docs x 500) + git_log ~800 + tasks ~1200 = ~6000.
**Warning signs:** Assembled context string exceeds 6000 characters.

### Pitfall 4: Encoding errors reading project files
**What goes wrong:** `UnicodeDecodeError` when reading a file with non-UTF-8 encoding.
**Why it happens:** Binary files or files with different encoding accidentally placed in .planning/.
**How to avoid:** Use `errors="replace"` in all `read_text()` calls.
**Warning signs:** 500 errors on context endpoint for specific projects.

### Pitfall 5: Recent tasks query without project_id linkage
**What goes wrong:** Cannot query tasks by project because project_id is nullable and may not be set yet (Phase 16 adds task-project linking).
**Why it happens:** Phase 14 runs before Phase 16 (task-project integration).
**How to avoid:** Query tasks by `project_path` (TEXT column that always exists) instead of `project_id`. Use `WHERE project_path = $1 ORDER BY created_at DESC LIMIT 5`.
**Warning signs:** Empty recent_tasks even for active projects.

## Code Examples

### assemble_full_context() complete implementation pattern
```python
MAX_CONTEXT_CHARS = 6000
MAX_CLAUDE_MD_CHARS = 2000
MAX_PLANNING_DOC_CHARS = 500
GIT_LOG_COUNT = 10
RECENT_TASKS_LIMIT = 5
PLANNING_FILES = ["PROJECT.md", "STATE.md", "ROADMAP.md", "REQUIREMENTS.md"]

async def assemble_full_context(project_path: str, pool: asyncpg.Pool) -> dict:
    """Assemble project context from 5 sources with char budget."""
    # 1. Workspace (reuse existing)
    workspace = assemble_workspace_context(project_path)

    # 2. CLAUDE.md
    claude_md = read_file_truncated(project_path, "CLAUDE.md", MAX_CLAUDE_MD_CHARS)

    # 3. .planning/ docs
    planning_docs = {}
    planning_dir = Path(project_path) / ".planning"
    if planning_dir.is_dir():
        for fname in PLANNING_FILES:
            content = read_file_truncated(
                str(planning_dir), fname, MAX_PLANNING_DOC_CHARS
            )
            if content:
                planning_docs[fname] = content

    # 4. Git log (async subprocess)
    git_log = await get_recent_git_log(project_path, GIT_LOG_COUNT)

    # 5. Recent tasks from DB by project_path
    recent_tasks = await get_recent_tasks(pool, project_path, RECENT_TASKS_LIMIT)

    return {
        "workspace": workspace,
        "claude_md": claude_md,
        "planning_docs": planning_docs,
        "git_log": git_log,
        "recent_tasks": recent_tasks,
    }
```

### Recent tasks query pattern
```python
async def get_recent_tasks(
    pool: asyncpg.Pool, project_path: str, limit: int = 5
) -> list[dict]:
    """Fetch recent tasks for a project by path."""
    rows = await pool.fetch(
        "SELECT id, prompt, status, created_at FROM tasks "
        "WHERE project_path = $1 ORDER BY created_at DESC LIMIT $2",
        project_path, limit,
    )
    return [
        {
            "id": r["id"],
            "prompt": r["prompt"][:200],  # Truncate long prompts
            "status": r["status"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]
```

### Response models for endpoints
```python
class PlanningDocsResponse(BaseModel):
    """Planning docs as key-value pairs."""
    model_config = {"extra": "allow"}

class RecentTaskResponse(BaseModel):
    id: int
    prompt: str
    status: str
    created_at: str

class ContextResponse(BaseModel):
    workspace: str
    claude_md: str
    planning_docs: dict[str, str]
    git_log: str
    recent_tasks: list[RecentTaskResponse]

class PhaseSuggestion(BaseModel):
    phase_id: str
    phase_name: str
    status: str
    reason: str

class PhaseSuggestionResponse(BaseModel):
    suggestion: PhaseSuggestion | None
    all_phases: list[PhaseSuggestion]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single workspace context only | Multi-source context assembly | Phase 14 (now) | Richer prompts with project history and planning docs |
| No phase awareness | Parse .planning/ for phase suggestion | Phase 14 (now) | Enables guided workflow continuation |

## Open Questions

1. **Which planning files to include?**
   - What we know: Spec mentions PROJECT.md, STATE.md, ROADMAP.md. REQUIREMENTS.md also exists.
   - What's unclear: Should all .planning/ files be included or just the core three?
   - Recommendation: Include PROJECT.md, STATE.md, ROADMAP.md, REQUIREMENTS.md (the 4 standard files). Skip phase subdirectories to stay within budget.

2. **Phase status granularity**
   - What we know: Spec shows "pending", "in_progress", "researched" as possible statuses.
   - What's unclear: How to detect "in_progress" vs "researched" without complex parsing.
   - Recommendation: Use three statuses: "complete" (checked `[x]`), "in_progress" (matches STATE.md current phase), "pending" (unchecked). Simple and sufficient.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | pyproject.toml (existing) |
| Quick run command | `pytest tests/test_context.py tests/test_context_assembly.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CTX-01 | assemble_full_context() returns 5 sources with truncation | unit | `pytest tests/test_context_assembly.py::test_assemble_full_context -x` | No -- Wave 0 |
| CTX-01 | MAX_CONTEXT_CHARS=6000 cap respected | unit | `pytest tests/test_context_assembly.py::test_context_respects_char_cap -x` | No -- Wave 0 |
| CTX-02 | GET /projects/{id}/context returns context | integration | `pytest tests/test_context_assembly.py::test_context_endpoint -x` | No -- Wave 0 |
| CTX-03 | suggest_next_phase() parses STATE.md/ROADMAP.md | unit | `pytest tests/test_context_assembly.py::test_suggest_next_phase -x` | No -- Wave 0 |
| CTX-04 | GET /projects/{id}/suggested-phase endpoint | integration | `pytest tests/test_context_assembly.py::test_suggested_phase_endpoint -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_context_assembly.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_context_assembly.py` -- covers CTX-01 through CTX-04
- Framework install: None needed -- pytest and pytest-asyncio already in place

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `src/context/assembler.py` -- existing workspace context assembler
- Codebase inspection: `src/git/autocommit.py` -- async subprocess pattern for git
- Codebase inspection: `src/db/pg_repository.py` -- ProjectRepository and TaskRepository patterns
- Codebase inspection: `src/server/routers/templates.py` -- router pattern with auth dependency
- Codebase inspection: `src/server/routers/tasks.py` -- TaskCreate and endpoint patterns
- Codebase inspection: `src/server/dependencies.py` -- get_pool, verify_credentials
- Codebase inspection: `src/server/app.py` -- router registration pattern
- Design spec: `docs/project-router-spec.md` -- Context Assembler and Phase Suggestion sections

### Secondary (MEDIUM confidence)
- Design spec API response shapes: `GET /projects/{id}/context` and `GET /projects/{id}/suggested-phase` response formats

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all patterns already exist in codebase
- Architecture: HIGH -- extends existing assembler.py, follows existing router pattern exactly
- Pitfalls: HIGH -- identified from codebase analysis (Docker git, nullable project_id, encoding)

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (stable -- pure Python, no external API dependencies)
