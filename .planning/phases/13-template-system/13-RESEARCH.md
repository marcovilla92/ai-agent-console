# Phase 13: Template System - Research

**Researched:** 2026-03-13
**Domain:** Template filesystem management, PyYAML registry, FastAPI CRUD endpoints, Jinja2 scaffolding
**Confidence:** HIGH

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TMPL-01 | 4 builtin templates available: blank, fastapi-pg, telegram-bot, cli-tool | Template directory structure defined in spec; file layout fully specified |
| TMPL-02 | Each builtin template includes CLAUDE.md, .claude/ agents+commands, and source scaffolding | Spec defines file tree for each template; Jinja2 variables known |
| TMPL-03 | User can list templates (GET /templates) from registry.yaml | PyYAML safe_load pattern; existing tasks.py router is the model |
| TMPL-04 | User can view template detail with file list (GET /templates/{id}) | pathlib.Path.rglob for file manifest; file type detection (.j2 suffix) |
| TMPL-05 | User can create custom template with inline files (POST /templates) | Path traversal must be prevented; registry.yaml upsert with safe_dump |
| TMPL-06 | User can update custom template metadata and files (PUT /templates/{id}) | files_upsert + files_delete semantics defined in spec |
| TMPL-07 | User can delete custom template (DELETE /templates/{id}) | shutil.rmtree on template directory + registry entry removal |
| TMPL-08 | Builtin templates are protected from modification/deletion (403 Forbidden) | builtin flag in registry.yaml; check before any mutation |
</phase_requirements>

## Summary

Phase 13 delivers the Template System: four builtin project templates on disk, a `registry.yaml` index, and a full REST CRUD API (`GET/POST/PUT/DELETE /templates`) served by a new FastAPI router. No new pip dependencies are required — PyYAML 6.0.1 and Jinja2 3.1.2 are already installed. The phase is filesystem-centric: templates live under `src/templates/` (the existing directory currently holding Jinja2 HTML templates), but **must not** collide with those files. The builtin template tree is fully specified in `docs/project-router-spec.md` (lines 396–485); the API contract is fully specified on lines 232–354. This is an authoring + wiring phase, not a design-from-scratch phase.

The key design constraints are: (1) `registry.yaml` is the authoritative index — templates not in it do not appear in the API, (2) builtin templates are `builtin: true` in the registry and respond 403 to POST/PUT/DELETE, (3) custom template files written via API must be path-traversal-sanitized before touching disk, (4) the `templates/` root must be resolved at startup time relative to the package root, not the CWD, to survive Docker deployment.

**Primary recommendation:** Place the template tree at `src/templates/` alongside the existing HTML templates, but inside a dedicated `src/templates/project_templates/` subdirectory (or a top-level `templates/` directory at the repo root). The spec diagram shows `templates/` at the repo root (peer to `src/`). Use the repo-root location to avoid confusion with Jinja2 HTML templates in `src/templates/`.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PyYAML | 6.0.1 (installed) | Read/write `registry.yaml` | Already system-installed; `safe_load`/`safe_dump` is the secure API |
| Jinja2 | 3.1.2 (installed) | Render `.j2` template files at scaffold time | Already installed; `FileSystemLoader` + `StrictUndefined` prevents silent blank variables |
| pathlib.Path | stdlib | Filesystem traversal, path canonicalization | No deps; `.resolve().is_relative_to()` for path traversal prevention |
| shutil | stdlib | Recursive directory copy and delete | `shutil.copytree` for template copying; `shutil.rmtree` for deletion |
| FastAPI | 0.135.1 (installed) | REST router for `/templates` endpoints | Existing pattern in `tasks.py` |
| asyncpg | 0.31.0 (installed) | Pool injection (not needed for templates, but dependency context) | Existing `app.state.pool` pattern |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest + pytest-asyncio | installed | Tests for template router and file operations | All tests in `tests/test_template_*.py` |
| httpx (via fastapi TestClient) | installed | HTTP-level tests for template endpoints | Template CRUD endpoint tests |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| registry.yaml (PyYAML) | DB table for template metadata | DB adds FK complexity and migration; YAML is portable, inspectable, easy to ship with container |
| repo-root `templates/` | `src/templates/project_templates/` | Nesting inside src avoids a new top-level dir but confuses with Jinja2 HTML templates |
| pathlib `.resolve().is_relative_to()` | Manual prefix check | `.is_relative_to()` is Python 3.9+ stdlib — safe for Python 3.12.3 in use |

**Installation:**

No new pip installs needed. PyYAML and Jinja2 are already installed. If formalizing in pyproject.toml:
```bash
# No new pip install — already available. Add to pyproject.toml dependencies:
# "pyyaml>=6.0",
# "jinja2>=3.1",
```

## Architecture Patterns

### Recommended Project Structure

```
templates/                         # repo root (peer to src/)
├── registry.yaml                  # authoritative index of all templates
├── blank/
│   ├── CLAUDE.md.j2
│   └── .planning/
│       └── README.md
├── fastapi-pg/
│   ├── CLAUDE.md.j2
│   ├── .claude/
│   │   ├── settings.local.json
│   │   ├── agents/
│   │   │   ├── db-migrator.md
│   │   │   └── api-tester.md
│   │   └── commands/
│   │       ├── migrate.md
│   │       ├── seed.md
│   │       └── test-api.md
│   ├── src/{__init__,main,config,db/schema,routers/__init__}.py
│   ├── tests/conftest.py
│   ├── Dockerfile
│   ├── docker-compose.yml.j2
│   ├── pyproject.toml.j2
│   └── .gitignore
├── telegram-bot/
│   ├── CLAUDE.md.j2
│   ├── .claude/
│   │   ├── settings.local.json
│   │   ├── agents/handler-builder.md
│   │   └── commands/{test-bot,deploy-bot}.md
│   ├── src/{bot,handlers/__init__,config}.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .gitignore
└── cli-tool/
    ├── CLAUDE.md.j2
    ├── .claude/
    │   ├── settings.local.json
    │   ├── agents/command-builder.md
    │   └── commands/release.md
    ├── src/{__init__,cli,commands/__init__}.py
    ├── pyproject.toml.j2
    └── .gitignore

src/server/routers/templates.py    # NEW: /templates router
```

### Pattern 1: YAML Registry Load / Save

**What:** Read `registry.yaml` with `yaml.safe_load`, serialize back with `yaml.safe_dump`. Never share with the HTML Jinja2 environment.
**When to use:** All template list/detail/CRUD operations.
**Example:**
```python
# Source: PyYAML 6.0 official docs + existing project research
import yaml
from pathlib import Path

TEMPLATES_ROOT = Path(__file__).resolve().parent.parent.parent / "templates"
REGISTRY_PATH = TEMPLATES_ROOT / "registry.yaml"

def load_registry() -> dict:
    with open(REGISTRY_PATH) as f:
        return yaml.safe_load(f) or {"templates": []}

def save_registry(data: dict) -> None:
    with open(REGISTRY_PATH, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)
```

### Pattern 2: Template Detail File Manifest

**What:** Walk the template directory with `rglob("*")`, filter to files only, record path (relative to template root), type (`.j2` = jinja2, else `static`), and byte size.
**When to use:** `GET /templates/{id}` response.
**Example:**
```python
# Source: pathlib stdlib docs
def get_file_manifest(template_id: str) -> list[dict]:
    template_dir = TEMPLATES_ROOT / template_id
    result = []
    for p in sorted(template_dir.rglob("*")):
        if p.is_file():
            rel = p.relative_to(template_dir)
            result.append({
                "path": str(rel),
                "type": "jinja2" if p.suffix == ".j2" else "static",
                "size": p.stat().st_size,
            })
    return result
```

### Pattern 3: Safe Custom Template File Write (Path Traversal Prevention)

**What:** Canonicalize all file paths from user-supplied `files` dict using `Path.resolve()` and `.is_relative_to()` before writing.
**When to use:** `POST /templates` and `PUT /templates/{id}` file upserts.
**Example:**
```python
# Source: pathlib stdlib docs + research SUMMARY.md pitfall 5
def safe_write_template_file(template_dir: Path, rel_path: str, content: str) -> None:
    target = (template_dir / rel_path).resolve()
    if not target.is_relative_to(template_dir.resolve()):
        raise ValueError(f"Path traversal attempt: {rel_path!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
```

### Pattern 4: FastAPI Router following tasks.py Model

**What:** New `template_router` registered in `app.py`. Dependencies follow the `verify_credentials` Depends pattern. No DB pool needed for pure filesystem operations.
**When to use:** All `/templates` endpoints.
**Example:**
```python
# Source: existing src/server/routers/tasks.py pattern
from fastapi import APIRouter, Depends, HTTPException, status
from src.server.dependencies import verify_credentials

template_router = APIRouter(
    prefix="/templates",
    tags=["templates"],
    dependencies=[Depends(verify_credentials)],
)

@template_router.get("", response_model=TemplateListResponse)
async def list_templates():
    data = load_registry()
    return TemplateListResponse(templates=data["templates"])

@template_router.delete("/{template_id}", status_code=200)
async def delete_template(template_id: str):
    data = load_registry()
    entry = next((t for t in data["templates"] if t["id"] == template_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if entry.get("builtin", False):
        raise HTTPException(status_code=403, detail="Cannot delete builtin template")
    shutil.rmtree(TEMPLATES_ROOT / template_id)
    data["templates"] = [t for t in data["templates"] if t["id"] != template_id]
    save_registry(data)
    return {"status": "deleted", "id": template_id}
```

### Anti-Patterns to Avoid

- **Reusing the HTML Jinja2 Environment for .j2 scaffolding:** The `src/templates/` HTML environment (used by `views.py`) must never be repurposed for template scaffolding. Create a separate `Environment(loader=FileSystemLoader(template_dir), undefined=StrictUndefined)` per render call.
- **Rendering user-supplied template content with from_string():** `jinja2.Environment().from_string(user_input)` is SSTI-vulnerable. Store custom template content verbatim; only render builtin `.j2` files (trusted, authored in-repo) with the standard Environment.
- **Hardcoded absolute paths:** `Path(__file__).resolve().parent` chains to find the `templates/` root — never use `os.getcwd()` or relative paths that break under Docker/uvicorn working directory changes.
- **Registering templates from directory scan instead of registry.yaml:** The registry is the source of truth. A directory existing without a registry entry is invisible; a registry entry pointing to a missing directory is a data integrity bug (validate at startup).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML parsing with comment preservation | Custom YAML parser | `yaml.safe_load` / `yaml.safe_dump` | Comments are not needed — registry is machine-managed |
| Path traversal prevention | Manual string prefix check | `pathlib.Path.resolve().is_relative_to()` | String prefix checks miss symlinks and `..` edge cases |
| Recursive directory deletion | `os.walk` + `os.remove` loop | `shutil.rmtree` | Handles symlinks, permissions, and non-empty dirs correctly |
| Template file discovery | Manual `os.listdir` | `pathlib.Path.rglob("*")` | Handles nested .claude/ subdirectories automatically |
| Jinja2 variable rendering | String `.format()` or `str.replace()` | `jinja2.Environment(undefined=StrictUndefined)` | StrictUndefined raises immediately on missing variable instead of silently inserting blank |

**Key insight:** This phase is primarily authoring (template file content) and wiring (router + registry YAML). Do not over-engineer the plumbing — it is 4 endpoints reading/writing files and a YAML registry.

## Common Pitfalls

### Pitfall 1: templates/ Root Location Resolved at CWD
**What goes wrong:** `Path("templates")` resolves relative to the uvicorn/pytest working directory, which changes between local dev, Docker, and test runs. The template files are not found in production.
**Why it happens:** Assuming `cwd == repo root` does not hold inside Docker containers or when uvicorn is started from a different directory.
**How to avoid:** Always use `Path(__file__).resolve().parent.parent.parent / "templates"` (or equivalent chain from the source file) to anchor to the package root.
**Warning signs:** `FileNotFoundError` on `registry.yaml` in Docker but works locally.

### Pitfall 2: Jinja2 SSTI via Custom Template Content
**What goes wrong:** If user-supplied file content from `POST /templates` is rendered through `jinja2.Environment().from_string()`, it becomes a server-side template injection vulnerability.
**Why it happens:** Custom template content looks like Jinja2 syntax (it contains `{{ name }}`), making it tempting to render.
**How to avoid:** Custom templates are stored verbatim. Only render during project scaffolding time (Phase 15), and only with `SandboxedEnvironment` if user content must be rendered. For Phase 13, just store files; rendering happens in Phase 15.
**Warning signs:** Any call to `from_string(request_body_content)`.

### Pitfall 3: registry.yaml / Filesystem Drift
**What goes wrong:** A `POST /templates` creates files on disk but fails to update `registry.yaml` (or vice versa), leaving the registry and filesystem out of sync.
**Why it happens:** Writing to disk succeeds but `save_registry()` throws, or the operation is not atomic.
**How to avoid:** Write registry update AFTER filesystem writes succeed. On error during filesystem write, clean up the partially-created directory. Wrap both steps: create dir → write files → update registry. If registry write fails, remove the created directory.
**Warning signs:** Template directory exists on disk but `GET /templates` does not list it.

### Pitfall 4: Builtin Template builtin Flag Not Checked
**What goes wrong:** `PUT /templates/fastapi-pg` overwrites builtin template files, breaking all future project scaffolding using that template.
**Why it happens:** The builtin guard is forgotten in the PUT/DELETE handlers.
**How to avoid:** Extract `get_registry_entry(template_id)` helper that also checks `builtin: true` and raises 403 immediately. Call it first in all mutation endpoints.
**Warning signs:** Manual `curl -X DELETE /templates/blank` succeeds instead of returning 403.

### Pitfall 5: .j2 Files in Custom Templates Rendered at Creation Time
**What goes wrong:** Files uploaded in `POST /templates` with `.j2` extension are immediately rendered with Jinja2, destroying the template variables.
**Why it happens:** Confusing "store template" with "render template".
**How to avoid:** `POST/PUT /templates` stores `.j2` files verbatim — no Jinja2 rendering at template CRUD time. Rendering happens only at project scaffold time (Phase 15, `POST /projects`).

### Pitfall 6: GET /templates/{id} Lists Hidden Files from .git
**What goes wrong:** `rglob("*")` traverses `.git/` inside the template directory (if git init was accidentally run there) and returns hundreds of git object files in the manifest.
**Why it happens:** Template directories are not git repos, but if one is mistakenly initialized, rglob finds everything.
**How to avoid:** Filter out EXCLUDE_DIRS in the manifest walk: `if not any(part in EXCLUDE_DIRS for part in p.parts)`.

## Code Examples

Verified patterns from official sources and the existing codebase:

### registry.yaml Format
```yaml
# Source: docs/project-router-spec.md lines 402-420
templates:
  - id: blank
    name: Vuoto
    description: Struttura minima con CLAUDE.md e .planning/
    builtin: true
  - id: fastapi-pg
    name: FastAPI + PostgreSQL
    description: API REST con agenti per migration, testing, deploy
    builtin: true
  - id: telegram-bot
    name: Bot Telegram
    description: Bot con agenti per handler testing e deploy
    builtin: true
  - id: cli-tool
    name: CLI Tool
    description: CLI Python con agenti per packaging e release
    builtin: true
```

### Jinja2 Variables Available in .j2 Templates
```python
# Source: docs/project-router-spec.md lines 488-494
# These are rendered at scaffold time (Phase 15), not at template CRUD time.
TEMPLATE_VARS = {
    "name": "My Project",           # project display name
    "slug": "my-project",           # URL/directory safe name
    "description": "...",           # user-provided description
    "date": "2026-03-13",           # creation date ISO format
    "author": "ubuntu",             # single-user, always "ubuntu"
}
```

### CLAUDE.md.j2 Content Pattern for blank Template
```jinja2
# {{ name }}

**Created:** {{ date }}
**Description:** {{ description }}

## Project Instructions

- Work in the project root directory
- Use git for version control
- Follow consistent code style for the detected language
```

### fastapi-pg CLAUDE.md.j2 Content Pattern
```jinja2
# {{ name }}

**Created:** {{ date }}
**Stack:** FastAPI + PostgreSQL

## Coding Conventions

- Use `async/await` everywhere — no sync DB calls
- Pydantic models for all request/response validation
- asyncpg Pool for database access (never raw psycopg2)
- pytest + pytest-asyncio for all tests

## Database

- Migrations in `src/db/migrations.py` — idempotent `CREATE TABLE IF NOT EXISTS`
- Connection pool injected via `app.state.pool`

## Structure

- `src/main.py` — FastAPI app factory
- `src/config.py` — pydantic-settings Settings class
- `src/db/schema.py` — DDL + dataclasses
- `src/routers/` — one file per resource
```

### FastAPI Template Router Registration
```python
# Source: existing src/server/app.py pattern
# In src/server/app.py — add after existing router includes:
from src.server.routers.templates import template_router

def create_app() -> FastAPI:
    app = FastAPI(title="AI Agent Console", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(task_router)
    app.include_router(ws_router)
    app.include_router(view_router)
    app.include_router(template_router)   # NEW
    return app
```

### GET /templates/{id} Response Model
```python
# Source: docs/project-router-spec.md lines 334-355
class TemplateFile(BaseModel):
    path: str
    type: str   # "jinja2" or "static"
    size: int

class TemplateDetail(BaseModel):
    id: str
    name: str
    description: str
    builtin: bool
    files: list[TemplateFile]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `src/templates/` used exclusively for Jinja2 HTML | New `templates/` at repo root for project templates | Phase 13 | Zero collision with existing HTML template machinery |
| No template system | `registry.yaml` + filesystem tree | Phase 13 | Enables `POST /projects?template=fastapi-pg` in Phase 15 |
| `create_project()` creates only `src/` dir | Phase 15 will render `.j2` files + copy static files | Phase 15 (not 13) | Phase 13 only creates the template files; Phase 15 wires the scaffold engine |

**Deprecated/outdated:**

- Nothing is deprecated in Phase 13. This phase is purely additive.

## Open Questions

1. **templates/ root location: repo root vs. src/templates/project_templates/**
   - What we know: The spec diagram shows `templates/` at repo root (peer to `src/`). The existing `src/templates/` holds Jinja2 HTML files.
   - What's unclear: Docker COPY context — `templates/` must be included in the Docker image. Current `Dockerfile` likely only COPYs `src/`.
   - Recommendation: Use repo-root `templates/`. Update Dockerfile to `COPY templates/ ./templates/` alongside `COPY src/ ./src/`. This matches the spec diagram and avoids any naming confusion.

2. **CLAUDE.md.j2 content quality for each template**
   - What we know: File locations are fully specified. Variable names (`name`, `slug`, `description`, `date`, `author`) are defined.
   - What's unclear: Exact prose content for the `.claude/agents/*.md` and `.claude/commands/*.md` files is not in the spec — these need domain judgment per stack.
   - Recommendation: Author minimal but functional agent/command descriptions for each template. Focus on: what the agent knows, what tools it uses, the slash command trigger and what it does. See examples above. This is content authoring, not a technical blocker.

3. **Where to anchor TEMPLATES_ROOT in tests**
   - What we know: Tests run from the repo root; Docker runs from `/app` (or wherever uvicorn starts).
   - What's unclear: Whether `Path(__file__).resolve()` in the router module correctly resolves during pytest runs.
   - Recommendation: Expose `TEMPLATES_ROOT` as a module-level constant in `src/server/routers/templates.py` and override it in tests via a fixture or monkeypatch, similar to how `settings.project_path` is currently used.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.23.x |
| Config file | pytest.ini or `pyproject.toml [tool.pytest]` — check existing |
| Quick run command | `pytest tests/test_templates.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TMPL-01 | 4 builtin template directories exist on disk | unit (filesystem) | `pytest tests/test_templates.py::test_builtin_template_dirs_exist -x` | ❌ Wave 0 |
| TMPL-02 | Each builtin has CLAUDE.md.j2, .claude/, source files | unit (filesystem) | `pytest tests/test_templates.py::test_builtin_template_contents -x` | ❌ Wave 0 |
| TMPL-03 | GET /templates returns list from registry.yaml | integration (HTTP) | `pytest tests/test_template_endpoints.py::test_list_templates -x` | ❌ Wave 0 |
| TMPL-04 | GET /templates/{id} returns file manifest | integration (HTTP) | `pytest tests/test_template_endpoints.py::test_get_template_detail -x` | ❌ Wave 0 |
| TMPL-05 | POST /templates creates custom template | integration (HTTP) | `pytest tests/test_template_endpoints.py::test_create_custom_template -x` | ❌ Wave 0 |
| TMPL-06 | PUT /templates/{id} updates custom template | integration (HTTP) | `pytest tests/test_template_endpoints.py::test_update_custom_template -x` | ❌ Wave 0 |
| TMPL-07 | DELETE /templates/{id} removes custom template | integration (HTTP) | `pytest tests/test_template_endpoints.py::test_delete_custom_template -x` | ❌ Wave 0 |
| TMPL-08 | Builtin templates return 403 on PUT/DELETE | integration (HTTP) | `pytest tests/test_template_endpoints.py::test_builtin_protected -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_templates.py tests/test_template_endpoints.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_templates.py` — covers TMPL-01, TMPL-02 (filesystem assertion tests, no DB needed)
- [ ] `tests/test_template_endpoints.py` — covers TMPL-03 through TMPL-08 (HTTP client tests using FastAPI TestClient with tmp_path registry override)
- [ ] `templates/registry.yaml` — must exist before any template endpoint test can run
- [ ] `templates/blank/`, `templates/fastapi-pg/`, `templates/telegram-bot/`, `templates/cli-tool/` — builtin template directories

*(No new framework installs needed — pytest + pytest-asyncio already present)*

## Sources

### Primary (HIGH confidence)
- `docs/project-router-spec.md` (808 lines) — complete Template System section (lines 384–538), API contracts (lines 232–354), file trees (lines 424–484)
- Existing codebase: `src/server/routers/tasks.py` — router pattern to follow
- Existing codebase: `src/server/app.py` — router registration pattern
- Existing codebase: `src/server/dependencies.py` — `verify_credentials` injection pattern
- Existing codebase: `src/pipeline/project.py` — `sanitize_project_name` / `create_project` already available
- Existing codebase: `src/context/assembler.py` — EXCLUDE_DIRS constant for file manifest filtering
- Existing codebase: `tests/test_project_repository.py` — integration test pattern with `pg_pool` fixture
- Python 3.12.3 stdlib: `pathlib.Path.resolve()`, `.is_relative_to()`, `shutil.rmtree`, `shutil.copytree`
- PyYAML 6.0.1 (installed): `yaml.safe_load`, `yaml.safe_dump`
- Jinja2 3.1.2 (installed): `Environment(loader=FileSystemLoader(...), undefined=StrictUndefined)`

### Secondary (MEDIUM confidence)
- `.planning/research/SUMMARY.md` — Phase 2 (Template System) research notes; pitfall 5 (Jinja2 SSTI); pitfall 3 (concurrent scan race — not applicable to templates but informs path safety discipline)
- FastAPI TestClient patterns for filesystem-dependent endpoints: standard practice, no official source needed

### Tertiary (LOW confidence — verify during implementation)
- Jinja2 CVE-2025-27516: Sandbox bypass via `|attr` filter — only relevant if `SandboxedEnvironment` is used for custom template rendering (not planned for Phase 13; custom content stored verbatim)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries are already installed and in use in the codebase
- Architecture: HIGH — router pattern is identical to `tasks.py`; filesystem operations are stdlib-only; spec defines all API contracts precisely
- Template content: MEDIUM — CLAUDE.md.j2 prose and .claude/agents/*.md content requires authoring judgment, not technical research
- Pitfalls: HIGH — all 6 pitfalls are derived from direct codebase analysis (Jinja2 env collision, path anchoring) and prior research summary (SSTI, registry drift)

**Research date:** 2026-03-13
**Valid until:** 2026-06-13 (90 days — PyYAML and Jinja2 are stable; FastAPI router pattern is stable)
