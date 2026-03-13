# Stack Research

**Domain:** Project Router additions to existing AI Agent Console (v2.1 milestone)
**Researched:** 2026-03-13
**Confidence:** HIGH

---

## Context: What Already Exists (Do Not Re-research)

The v2.0 stack is validated and deployed:
- FastAPI + asyncpg + uvicorn — backend fully operational
- Jinja2 >= 3.1 — already installed, used for HTML templates
- Alpine.js 3.x (CDN) + Pico CSS 2.x — frontend in use
- asyncio.create_subprocess_exec — already in `src/git/autocommit.py`
- subprocess / asyncio patterns — established codebase patterns
- PostgreSQL 16 — live on VPS

This document covers ONLY new capabilities needed for v2.1.

---

## New Capabilities Required

### 1. YAML Parsing — registry.yaml for template system

**Requirement:** Read/write `templates/registry.yaml` (template index). Must support round-trip — add/remove entries without destroying formatting.

**Recommendation: PyYAML >= 6.0.2 (already a Python stdlib companion, zero new deps)**

PyYAML is already available on the system (confirmed: `python3 -c "import yaml"` succeeds). The `registry.yaml` use case is simple: load a dict, append/remove an entry, write it back. Comment preservation is not needed because `registry.yaml` is machine-managed only (not human-edited between API calls).

Use `yaml.safe_load()` and `yaml.safe_dump()`. This is sufficient.

**Do NOT add ruamel.yaml.** It is a heavier dependency (multiple sub-packages) and is justified only when round-trip comment preservation is a hard requirement. For a machine-managed index file, PyYAML safe_dump is correct.

```python
import yaml

def load_registry(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {"templates": []}

def save_registry(path: Path, data: dict) -> None:
    with open(path, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)
```

**Version:** PyYAML 6.0.2+ (already installed system-wide; add `pyyaml>=6.0` to pyproject.toml if not already there to make it explicit).

---

### 2. Template Rendering — `.j2` scaffolding files

**Requirement:** Render Jinja2 templates (`.j2` files) with project variables (`name`, `slug`, `date`) during project creation.

**Recommendation: Jinja2 (already installed — zero new dependency)**

Jinja2 >= 3.1 is already in requirements.txt. The `templates/` directory is being repurposed from HTML templates to project scaffolding (confirmed in PROJECT.md key decisions). The `Environment` class with a `FileSystemLoader` is the correct API — not `Jinja2Templates` (which is the FastAPI/Starlette wrapper for HTTP responses).

```python
from jinja2 import Environment, FileSystemLoader, StrictUndefined

def render_template_file(template_path: Path, context: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        undefined=StrictUndefined,  # Fail fast on missing variables
        keep_trailing_newline=True,
    )
    template = env.get_template(template_path.name)
    return template.render(**context)
```

Context variables for all templates: `name` (display name), `slug` (kebab-case), `date` (ISO date string), `description`.

**Use StrictUndefined** — template scaffolding errors must be loud, not silently blank.

**Version:** Jinja2 >= 3.1 (already installed). No version change needed.

---

### 3. Git Subprocess — `git init` for new project creation

**Requirement:** Run `git init` (and optionally `git add`, first `git commit`) when creating a new project via `POST /projects`.

**Recommendation: asyncio.create_subprocess_exec (already established pattern)**

The codebase already uses `asyncio.create_subprocess_exec` in `src/git/autocommit.py` for git operations. Use the same pattern for `git init`. No new library needed.

```python
async def git_init(project_path: Path) -> None:
    """Initialize a git repository in the new project directory."""
    proc = await asyncio.create_subprocess_exec(
        "git", "init",
        cwd=str(project_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"git init failed: {stderr.decode()}")

async def git_initial_commit(project_path: Path, project_name: str) -> None:
    """Stage all scaffolded files and create initial commit."""
    for cmd in [
        ["git", "add", "."],
        ["git", "commit", "-m", f"init: scaffold {project_name} from template"],
    ]:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(project_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode != 0:
            break  # Silently skip if commit fails (no git identity configured)
```

**Why asyncio.create_subprocess_exec over subprocess.run in executor:**
The codebase already uses the async subprocess pattern. Consistent is better than introducing a `run_in_executor` pattern for the same concern. `git init` on a local path is fast (< 100ms) and non-blocking in practice.

**No new library.** Git is already present on the VPS (Ubuntu 24.04 ships git).

---

### 4. Filesystem Scanning — `~/projects/` auto-registration

**Requirement:** Scan `~/projects/` on `GET /projects` to discover unregistered directories and reconcile with the DB.

**Recommendation: pathlib.Path (stdlib — zero new dependency)**

Directory scanning is pure stdlib. No library is needed.

```python
import os
from pathlib import Path

def scan_projects_dir(base_path: str = "~/projects") -> list[Path]:
    """Return all immediate subdirectories of base_path."""
    root = Path(base_path).expanduser()
    if not root.exists():
        return []
    return [
        p for p in root.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    ]

def detect_stack(project_path: Path) -> str:
    """Heuristic stack detection from project files."""
    markers = {
        "pyproject.toml": "Python",
        "requirements.txt": "Python",
        "package.json": "Node.js",
        "go.mod": "Go",
        "Cargo.toml": "Rust",
        "pom.xml": "Java",
    }
    for filename, stack in markers.items():
        if (project_path / filename).exists():
            return stack
    return "Unknown"
```

Stack detection is a heuristic used for the frontend display (e.g., "Python, Docker"). Check for `Dockerfile` presence separately.

**No new library.** `pathlib` and `os` are stdlib.

---

### 5. Alpine.js SPA — replacing multi-page Jinja2 templates

**Requirement:** Replace three Jinja2 server-rendered pages (base.html, task_list.html, task_detail.html) with a single `index.html` SPA serving three views: project-select → prompt → running.

**Recommendation: Alpine.js 3.x + `x-show` view switching (no router library)**

The existing Alpine.js 3 CDN tag is already present (`alpinejs@3/dist/cdn.min.js`). For this SPA, three views are switched via a single `currentView` state variable. This is the correct Alpine.js pattern for small SPAs.

**Do NOT add a router library** (alpinejs-router, pinecone-router). Three fixed views with no deep-linking requirement do not justify an external dependency. `x-show` with a global Alpine.store is sufficient and zero-overhead.

**Pattern:**

```html
<script>
document.addEventListener('alpine:init', () => {
    Alpine.store('app', {
        // View state: 'project-select' | 'prompt' | 'running'
        view: 'project-select',

        // Selected project
        project: null,

        // Active task
        taskId: null,

        // Navigate views
        goToPrompt(project) {
            this.project = project;
            this.view = 'prompt';
        },
        goToRunning(taskId) {
            this.taskId = taskId;
            this.view = 'running';
        },
        reset() {
            this.project = null;
            this.taskId = null;
            this.view = 'project-select';
        }
    });
});
</script>

<!-- Each view section uses x-show for visibility toggling -->
<section x-show="$store.app.view === 'project-select'">...</section>
<section x-show="$store.app.view === 'prompt'">...</section>
<section x-show="$store.app.view === 'running'">...</section>
```

**Why `Alpine.store` over `x-data` on a root element:**
`Alpine.store` is globally accessible from any component without prop drilling. With three distinct sections that need shared state (project selection affects prompt which affects running), a global store is cleaner than a single massive `x-data` object on `<body>`.

**Why `x-show` over `x-if`:**
`x-show` keeps DOM elements alive (preserving WebSocket connections and scroll position in the running view). `x-if` destroys and recreates elements on each transition, which would kill an active WebSocket stream.

**Current Alpine.js version:** 3.15.8 (confirmed via web search, March 2026).
Pin CDN to specific version for production stability: `alpinejs@3.15.8`.

---

### 6. Context Assembly — reading .planning/ docs and git log

**Requirement:** `GET /projects/{id}/context` reads CLAUDE.md, .planning/ files, recent git log, and last N tasks from DB.

**All stdlib + existing asyncpg. No new library.**

```python
async def assemble_context(project_path: Path, pool: asyncpg.Pool, project_id: int) -> dict:
    context = {}

    # CLAUDE.md
    claude_md = project_path / "CLAUDE.md"
    context["claude_md"] = claude_md.read_text() if claude_md.exists() else ""

    # .planning/ docs
    planning_dir = project_path / ".planning"
    context["planning_docs"] = {}
    if planning_dir.exists():
        for doc in ["PROJECT.md", "STATE.md", "ROADMAP.md"]:
            p = planning_dir / doc
            if p.exists():
                context["planning_docs"][doc] = p.read_text()

    # Git log (last 10 commits)
    proc = await asyncio.create_subprocess_exec(
        "git", "log", "--oneline", "-10",
        cwd=str(project_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    context["git_log"] = stdout.decode() if proc.returncode == 0 else ""

    # Recent tasks from DB
    rows = await pool.fetch(
        "SELECT id, prompt, status, created_at FROM tasks "
        "WHERE project_id = $1 ORDER BY created_at DESC LIMIT 5",
        project_id
    )
    context["recent_tasks"] = [dict(r) for r in rows]
    return context
```

**No new library.** File I/O via `pathlib`, async subprocess for git, asyncpg for DB.

---

## Summary: New Dependencies for v2.1

| Dependency | Action | Rationale |
|------------|--------|-----------|
| `pyyaml>=6.0` | Add to pyproject.toml | Make explicit; already system-installed. For registry.yaml read/write. |
| Alpine.js `@3.15.8` | Pin CDN version | Was `@3` (floating). Pin for stability. |
| Everything else | No change | Jinja2, asyncio subprocess, pathlib — all existing. |

**Net new pip dependencies: 1 (pyyaml, made explicit)**

---

## Updated pyproject.toml dependencies

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "asyncpg>=0.30",
    "jinja2>=3.1",
    "python-multipart>=0.0.18",
    "httpx>=0.28",
    "pydantic-settings>=2.0",
    "tenacity>=8.0",
    "pyyaml>=6.0",      # NEW: template registry.yaml parsing
]
```

---

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| PyYAML safe_load/dump | ruamel.yaml | ruamel.yaml justified only for round-trip comment preservation. registry.yaml is machine-managed — no comments to preserve. Extra dependency for zero benefit. |
| Alpine.store + x-show | alpinejs-router | Three fixed views with no deep-link requirement. Router adds 15KB+ and API surface for a problem that x-show solves in 5 lines. |
| Alpine.store + x-show | x-data on root body | Store is globally accessible without prop drilling. Root x-data becomes a 300-line god-object. Store separates concerns cleanly. |
| asyncio.create_subprocess_exec | subprocess.run in run_in_executor | Consistent with existing git/autocommit.py pattern. Subprocess is async-native. run_in_executor adds thread-pool indirection for equivalent behavior. |
| pathlib.Path.iterdir() | os.scandir / glob | pathlib is the modern Python stdlib standard. Already used throughout codebase. |
| Jinja2 Environment + FileSystemLoader | Mako / Chevron | Jinja2 already installed. Mako/Chevron would be extra deps for identical capability. |

---

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| ruamel.yaml | Heavier than PyYAML, needed only for comment preservation in human-edited files. registry.yaml is not human-edited. | PyYAML safe_load/dump |
| alpinejs-router / pinecone-router | 3-view SPA with no URL routing requirement. External dependency for a 5-line x-show pattern. | Alpine.store + x-show |
| GitPython | 30MB+ dependency for git subprocess operations. asyncio.create_subprocess_exec already handles the 3 commands needed (init, add, commit). | asyncio.create_subprocess_exec |
| watchdog / inotify | Project scan happens on demand (GET /projects), not via filesystem events. Event-driven scanning is over-engineering for a single-user tool. | pathlib.iterdir() on request |
| Cookiecutter | External project scaffolding library. Template structure is simple (.j2 files + static files). Jinja2 Environment handles rendering. Cookiecutter adds CLI-oriented abstractions that don't fit the API-driven use case. | Jinja2 Environment |

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| PyYAML 6.0.x | Python >= 3.8 | PyYAML 6.0.2 removed `yaml.load()` without Loader (security). Always use `yaml.safe_load()`. |
| Jinja2 3.1.x | Python >= 3.8 | `Environment(undefined=StrictUndefined)` is the correct mode for scaffolding — fail loud. |
| Alpine.js 3.15.8 | Any modern browser | `Alpine.store()` API stable since 3.0. No breaking changes expected in 3.x. |
| asyncio.create_subprocess_exec | Python 3.12 (stdlib) | Already proven in autocommit.py. No compatibility concerns. |

---

## Sources

- PyYAML 6.0.2 PyPI: https://pypi.org/project/PyYAML/ — version 6.0.2 confirmed stable (HIGH confidence)
- Alpine.js releases: https://github.com/alpinejs/alpine/releases — 3.15.8 latest as of March 2026 (HIGH confidence)
- Alpine.js store docs: https://alpinejs.dev/essentials/state — `Alpine.store()` pattern (HIGH confidence)
- Python asyncio subprocess docs: https://docs.python.org/3/library/asyncio-subprocess.html — create_subprocess_exec (HIGH confidence)
- Existing codebase: `src/git/autocommit.py` — asyncio subprocess pattern already in use (HIGH confidence)
- Jinja2 docs: https://jinja.palletsprojects.com/en/3.1.x/api/#jinja2.Environment — StrictUndefined (HIGH confidence)
- Web search (Alpine.js SPA patterns, 2025) — x-show vs x-if DOM behavior verified (MEDIUM confidence)
- Web search (PyYAML vs ruamel.yaml comparison, 2025) — comment preservation tradeoff verified (MEDIUM confidence)

---
*Stack research for: AI Agent Console v2.1 Project Router additions*
*Researched: 2026-03-13*
