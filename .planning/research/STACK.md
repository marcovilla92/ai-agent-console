# Technology Stack

**Project:** AI Agent Console v2.4 — Template System Overhaul
**Researched:** 2026-03-14
**Confidence:** HIGH

---

## Context: Existing Stack (Do Not Change)

The v2.0-v2.3 stack is validated and deployed. These stay as-is:

| Technology | Installed Version | Purpose |
|------------|------------------|---------|
| Python | 3.12.3 | Runtime |
| FastAPI | 0.135.1 | HTTP + WebSocket server |
| asyncpg | 0.30+ | PostgreSQL driver |
| Pydantic | 2.12.5 | Data validation, API models |
| Jinja2 | 3.1.2 | Template file rendering (.j2) |
| PyYAML | 6.0.1 | registry.yaml parsing |
| Alpine.js | 3.x (CDN) | Frontend reactivity |
| Tailwind CSS | 3.x (CDN) | Styling |

This document covers ONLY what the v2.4 features need beyond the existing stack.

---

## Key Finding: One New Dependency

All five v2.4 features (dynamic agent loading, command discovery, project settings, AI template generation, template editor) require **one** new pip dependency. Everything else uses existing libraries or Python stdlib.

**Net new pip dependency: `python-frontmatter==1.1.0`**
**Net new frontend dependencies: 0**

---

## New Dependency

### python-frontmatter 1.1.0 — Agent/Command Markdown Parsing

| | |
|---|---|
| **Package** | `python-frontmatter` |
| **Version** | 1.1.0 (latest stable, released 2024) |
| **Purpose** | Parse YAML frontmatter + markdown body from `.claude/agents/*.md` and `.claude/commands/*.md` files |
| **Confidence** | HIGH — verified on PyPI via `pip index versions`, 1.1.0 is latest |

**Why this library:**

The agent markdown files in existing templates (e.g., `templates/fastapi-pg/.claude/agents/db-migrator.md`) currently contain only a plain-text system prompt. For v2.4, these files need structured metadata (name, description, allowed_transitions, output_sections) alongside the free-text prompt body. YAML frontmatter is the standard format for this: metadata between `---` delimiters, content after.

`python-frontmatter` does exactly one thing: `post = frontmatter.load(path)` returns `post.metadata` (dict from YAML) and `post.content` (str of markdown body). Zero configuration. The only transitive dependency is PyYAML, which is already installed (6.0.1).

**Why not roll our own:**

Splitting on `---` looks trivial but has edge cases: YAML documents can contain `---`, the delimiter must be at column 0, encoding detection, BOM handling. python-frontmatter handles all of these. The alternative is 30+ lines of fragile regex that will break on the first template with a YAML multiline string.

**Proposed agent markdown format:**

```markdown
---
name: db-migrator
description: Database migration specialist for PostgreSQL with asyncpg
allowed_transitions:
  - execute
  - review
output_sections:
  - MIGRATION_PLAN
  - SQL
  - ROLLBACK
  - HANDOFF
---

You are a database migration specialist for PostgreSQL with asyncpg.

Create idempotent SQL migrations using CREATE TABLE IF NOT EXISTS...
```

This maps directly to `AgentConfig` fields:
- `post.metadata["name"]` -> `AgentConfig.name`
- `post.metadata["description"]` -> `AgentConfig.description`
- `post.metadata["allowed_transitions"]` -> `AgentConfig.allowed_transitions`
- `post.metadata["output_sections"]` -> `AgentConfig.output_sections`
- `post.content` -> written to a temp file, path used as `system_prompt_file`

**Backward compatibility:** Existing agent `.md` files without frontmatter will be loaded as body-only (frontmatter defaults to empty dict). The loader will generate a name from the filename and use sensible defaults for transitions. No migration needed for existing templates.

---

## Feature-by-Feature Stack Analysis

### R1: Dynamic Agent Loading — `python-frontmatter` + `pathlib` + `dataclasses`

**What it needs:**
1. Scan `.claude/agents/*.md` in project directory
2. Parse each file for metadata + system prompt
3. Convert to `AgentConfig` compatible with `AGENT_REGISTRY`
4. Merge with default agents (plan/execute/test/review)

**Stack usage:**
- `pathlib.Path.glob("*.md")` — file discovery (stdlib)
- `python-frontmatter.load()` — metadata + content parsing (new dep)
- `dataclasses.AgentConfig` — existing config dataclass, no changes needed
- `tempfile` or direct write — system prompt content needs to be a file path for `--system-prompt-file` CLI flag

**Integration with existing code:**

The key change is in `src/agents/config.py`. Currently `AGENT_REGISTRY` is a module-level dict. It stays as the **default** registry. A new function `build_project_registry(project_path: str) -> dict[str, AgentConfig]` merges defaults with project agents. The orchestrator receives the merged registry as a parameter instead of importing the global.

```python
# src/agents/loader.py (NEW)
import frontmatter
from pathlib import Path
from src.agents.config import AgentConfig

def load_project_agents(project_path: str) -> dict[str, AgentConfig]:
    agents_dir = Path(project_path) / ".claude" / "agents"
    if not agents_dir.is_dir():
        return {}
    result = {}
    for md_file in sorted(agents_dir.glob("*.md")):
        post = frontmatter.load(str(md_file))
        name = post.metadata.get("name", md_file.stem)
        # Write system prompt content to a file the CLI can reference
        prompt_file = agents_dir / f".{name}_prompt.txt"
        prompt_file.write_text(post.content)
        result[name] = AgentConfig(
            name=name,
            system_prompt_file=str(prompt_file),
            description=post.metadata.get("description", ""),
            output_sections=post.metadata.get("output_sections", []),
            allowed_transitions=tuple(post.metadata.get("allowed_transitions", ())),
        )
    return result
```

**No new libraries needed beyond python-frontmatter.**

---

### R2: Command/Skill Discovery — `python-frontmatter` + `pathlib`

**What it needs:**
1. Scan `.claude/commands/*.md` in project directory
2. Parse each file for command name, description, instructions
3. Inject available commands into context assembly

**Stack usage:**
- Same `python-frontmatter` for parsing (reuses R1 dependency)
- Same `pathlib.Path.glob("*.md")` for discovery

**Command markdown format:**

```markdown
---
name: migrate
description: Run database migration
---

Analyze the current database schema, generate a new idempotent migration file...
```

**Integration:** Commands are injected into the system prompt context via `assemble_full_context()` in `src/context/assembler.py`. The existing function returns a dict with workspace, claude_md, planning_docs, git_log, recent_tasks. Add a sixth key: `commands` (list of dicts with name, description, instructions).

**No new libraries needed.**

---

### R3: Project Settings Application — `json` (stdlib)

**What it needs:**
1. Read `.claude/settings.local.json` from project directory
2. Parse JSON for permissions and configuration
3. Apply to execution context

**Stack usage:**
- `json.loads()` — stdlib, already used everywhere
- `Pydantic BaseModel` — validate settings schema (already installed 2.12.5)

**Integration:** Settings are read once on project open/task start and passed to the context. The existing settings format is simple: `{"permissions": {"allow": ["Bash", "WebSearch"]}}`. This gets injected into Claude CLI flags or context assembly.

**No new libraries needed.**

---

### R4: AI Template Generation — Claude CLI subprocess (existing)

**What it needs:**
1. Accept natural language description via API endpoint
2. Call Claude CLI to generate template structure
3. Return structured JSON (file tree + contents)
4. Frontend renders preview

**Stack usage:**
- Existing `src/runner/runner.py` subprocess pattern — Claude CLI with `--json-schema` for structured output
- Existing `FastAPI` route pattern — new `POST /templates/generate` endpoint
- `json` (stdlib) — parse structured output

**This is the most important "no new library" decision.** The system already calls Claude CLI via subprocess with JSON schema enforcement for the orchestrator. Template generation is the same pattern with a different schema:

```python
TEMPLATE_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    "required": ["files"],
})
```

The Claude CLI call uses the same `call_orchestrator_claude()` function (renamed or generalized to `call_claude_structured()`) with a template-generation system prompt.

**No new libraries needed.**

---

### R5: Template Editor UI — Alpine.js + textarea (existing)

**What it needs:**
1. File tree display with nested structure
2. Inline file editing (click file, edit content)
3. Preview before saving

**Stack usage:**
- Alpine.js `x-for` with nested data — existing pattern used in project list and task list
- `<textarea>` with `x-model` — two-way binding for editing
- Tailwind CSS for layout — existing

**No frontend build system needed.** The template editor is a JSON file tree rendered as Alpine.js components. Each file node has `path`, `content`, and `language`. Clicking a file opens its content in a textarea. The user edits, clicks save, and `POST /templates` sends the modified structure to the backend.

**No new libraries needed.**

---

## What NOT to Add (and Why)

| Library | Why It Seems Relevant | Why Wrong Here |
|---------|----------------------|----------------|
| **watchfiles / watchdog** | "Watch for agent file changes" | Agent loading triggers on project open/task start, not on file change. `Path.glob()` at load time is sufficient. No long-running watcher needed. |
| **pluggy / stevedore / yapsy** | "Plugin framework for agent loading" | The "plugin" is reading markdown files from a directory and building dataclasses. This is 50 lines of Python, not a plugin framework problem. |
| **LangChain / LiteLLM** | "LLM abstraction for template generation" | The system uses Claude CLI via subprocess. LangChain's API-based abstractions do not map to subprocess execution. Adding it would require rewriting the entire runner. |
| **jsonschema** | "Validate generated template structure" | Pydantic 2.12.5 already handles validation. Define a `TemplateOutput` model and validate with `model_validate()`. |
| **markdown / mistune** | "Render markdown in editor" | Agent prompts are injected as raw text into Claude CLI. Template editor shows file content in textareas. No HTML rendering needed. |
| **CodeMirror / Monaco Editor** | "Rich code editing in browser" | Adds 500KB+ JS and build complexity. A `<textarea>` with monospace font and basic Tailwind styling is sufficient for a single-user tool. Can revisit if users request syntax highlighting later. |
| **Redis / caching** | "Cache loaded agent configs" | Agent registry is per-project, loaded once on project open. The data source is a handful of small markdown files on local disk. Caching adds complexity for zero benefit. |
| **GitPython** | "Git operations for template repos" | `asyncio.create_subprocess_exec("git", ...)` already handles git throughout the codebase. GitPython is 30MB+ for wrapping the same binary. |
| **Celery / task queue** | "Queue template generation" | Template generation is a single Claude CLI call. The existing asyncio semaphore (max 2 processes) is sufficient. No queue needed. |

---

## Changes to requirements.txt

```txt
# Add one line:
python-frontmatter>=1.1
```

Full requirements.txt after change:
```txt
# Core dependencies
aiosqlite>=0.20
tenacity>=8.0
textual>=0.50

# v2.0 Web Platform
asyncpg>=0.30
fastapi>=0.115
uvicorn[standard]>=0.34
pydantic-settings>=2.0
httpx>=0.28
jinja2>=3.1

# v2.4 Template System
python-frontmatter>=1.1

# Dev/Test
pytest>=8.0
pytest-asyncio>=0.24
```

Installation:
```bash
pip install python-frontmatter==1.1.0
```

---

## Architecture Impact

### New Files (Stack-Related)

| File | Purpose | Key Dependency |
|------|---------|---------------|
| `src/agents/loader.py` | Discover + parse `.claude/agents/*.md` | python-frontmatter |
| `src/commands/loader.py` | Discover + parse `.claude/commands/*.md` | python-frontmatter |
| `src/settings/loader.py` | Read + validate `.claude/settings.local.json` | json (stdlib) + Pydantic |

### Modified Files

| File | Change | Stack Impact |
|------|--------|-------------|
| `src/agents/config.py` | `AGENT_REGISTRY` stays as default; add `build_project_registry()` that merges defaults with project agents | None — pure refactor |
| `src/context/assembler.py` | Extend `assemble_full_context()` with agents, commands, settings keys | None — existing patterns |
| `src/pipeline/orchestrator.py` | Accept registry as parameter instead of importing global | None — dependency injection refactor |
| `src/server/routers/templates.py` | Add `POST /templates/generate` endpoint | None — existing FastAPI pattern |
| `src/server/routers/projects.py` | Trigger agent/command/settings loading on project open | None — adds loader calls |
| `static/index.html` | Template editor UI, generation form | None — Alpine.js patterns |

### Key Refactoring: Registry Injection

The orchestrator currently does this (line 22 of orchestrator.py):
```python
from src.agents.config import ROUTING_SECTIONS, build_agent_descriptions, build_agent_enum, validate_transition
```

These functions read from the module-level `AGENT_REGISTRY`. With dynamic loading, the orchestrator needs to work with a project-specific registry. Two approaches:

**Option A: Parameter injection (recommended)**
```python
async def orchestrate_pipeline(ctx, prompt, pool, session_id, registry=None):
    if registry is None:
        registry = AGENT_REGISTRY
    # Use registry throughout instead of global AGENT_REGISTRY
```

**Option B: Context-scoped registry**
```python
# Set project-specific registry on TaskContext
ctx.agent_registry = build_project_registry(project_path)
```

**Recommendation: Option A.** Parameter injection is explicit, testable, and does not expand the TaskContext Protocol. The registry is built once when a task starts and passed down. No global mutation, no thread-safety concerns.

---

## Backward Compatibility

### Existing templates without frontmatter

The current agent `.md` files (e.g., `templates/fastapi-pg/.claude/agents/db-migrator.md`) contain only a plain text system prompt with no frontmatter. The loader must handle this gracefully:

```python
post = frontmatter.load(str(md_file))
if not post.metadata:
    # No frontmatter — legacy format
    # Name from filename, body is the entire prompt
    name = md_file.stem
    config = AgentConfig(
        name=name,
        system_prompt_file=...,
        description=f"Project agent: {name}",
        output_sections=[],
        allowed_transitions=(),
    )
```

`python-frontmatter` handles files without frontmatter correctly: `post.metadata` returns an empty dict and `post.content` returns the full file content. No special handling needed in the parser itself.

### Existing registry.yaml

The `templates/registry.yaml` currently lists template id, name, description, builtin flag. For v2.4, it could gain agent/command metadata, but this is optional: the system discovers agents/commands from the filesystem at load time. The registry.yaml remains a lightweight index for the template list endpoint.

---

## Sources

- **python-frontmatter PyPI:** Verified version 1.1.0 via `pip index versions python-frontmatter`. Latest stable release. HIGH confidence.
- **Existing codebase inspection (HIGH confidence):**
  - `src/agents/config.py` — AgentConfig dataclass, AGENT_REGISTRY dict, build_agent_enum/descriptions
  - `src/pipeline/orchestrator.py` — Global registry imports on line 22, schema generation, routing
  - `src/context/assembler.py` — assemble_full_context() returns 5-key dict, extend to 8 keys
  - `src/pipeline/project_service.py` — scaffold_from_template() copies files, git_init_project()
  - `src/runner/runner.py` — call_orchestrator_claude() subprocess pattern reusable for template gen
  - `templates/fastapi-pg/.claude/agents/db-migrator.md` — current agent file format (no frontmatter)
  - `templates/fastapi-pg/.claude/settings.local.json` — current settings format
- **Installed versions verified via `pip show`:** FastAPI 0.135.1, Pydantic 2.12.5, PyYAML 6.0.1, Jinja2 3.1.2
- **Python 3.12.3 confirmed via `python3 --version`**

---
*Stack research for: AI Agent Console v2.4 Template System Overhaul*
*Researched: 2026-03-14*
