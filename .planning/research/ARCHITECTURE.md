# Architecture Patterns

**Domain:** Dynamic agent loading and AI template generation for AI Agent Console v2.4
**Researched:** 2026-03-14
**Confidence:** HIGH (direct codebase analysis of all affected components)

## Current Architecture Snapshot

```
HTTP Layer (FastAPI routers)
  projects.py  -- CRUD + context/phase endpoints
  templates.py -- template CRUD, registry.yaml management
    |
Service Layer
  ProjectService     -- create_project() scaffolds + git init
  ContextAssembler   -- 5-source context for system prompts
    |
Pipeline Layer
  orchestrator.py    -- AI-driven routing loop (Claude CLI)
  file_writer.py     -- writes code from execute agent output
  handoff.py         -- builds inter-agent handoff context
    |
Agent Layer
  config.py          -- AGENT_REGISTRY (hardcoded dict of 4 agents)
  prompts/           -- .txt system prompts for plan/execute/test/review
  base.py            -- AgentResult dataclass
    |
Runner Layer
  runner.py          -- Claude CLI subprocess, streaming, JSON schema
```

### Critical Architectural Constraint

The `AGENT_REGISTRY` is a **module-level constant**. The orchestrator imports `build_agent_enum()` and `build_agent_descriptions()` which read from this constant, and `ORCHESTRATOR_SCHEMA` is computed once at import time via `_build_orchestrator_schema()`. The entire routing schema is frozen at process startup. Dynamic agents require making this per-project and per-task.

### Template File Structure (Existing)

Templates already contain `.claude/` directories with agent files, command files, and settings. Example from `fastapi-pg`:

```
templates/fastapi-pg/
  .claude/
    agents/
      db-migrator.md      -- plain text system prompt (no metadata)
      api-tester.md        -- plain text system prompt (no metadata)
    commands/
      migrate.md           -- instruction text
      seed.md
      test-api.md
    settings.local.json    -- {"permissions": {"allow": ["Bash", "WebSearch"]}}
  CLAUDE.md.j2
  Dockerfile
  src/
    main.py
    ...
```

These files are copied during scaffolding but **never read by the runtime**. This is the core problem v2.4 solves.

---

## Recommended Architecture

### New and Modified Components

| Component | Status | Responsibility | Communicates With |
|-----------|--------|---------------|-------------------|
| `src/agents/loader.py` | **NEW** | Discover + parse `.claude/agents/*.md` into AgentConfig | config.py, assembler.py |
| `src/agents/config.py` | **MODIFY** | Provide `get_project_registry(project_path)`, add `system_prompt_inline` field | orchestrator.py, loader.py |
| `src/commands/loader.py` | **NEW** | Discover + parse `.claude/commands/*.md` into CommandConfig | assembler.py |
| `src/settings/loader.py` | **NEW** | Read + merge `.claude/settings.local.json` with defaults | assembler.py, runner.py |
| `src/context/assembler.py` | **MODIFY** | Include agents/commands/settings in context output | loader modules, orchestrator |
| `src/pipeline/orchestrator.py` | **MODIFY** | Accept dynamic registry per invocation, build schema per-run | config.py (dynamic) |
| `src/runner/runner.py` | **MODIFY** | Support inline system prompts (not just file paths) | orchestrator.py |
| `src/server/routers/templates.py` | **MODIFY** | Add `POST /templates/generate` endpoint | runner.py (Claude CLI) |
| `src/pipeline/project_service.py` | **MODIFY** | Trigger capability discovery after scaffolding | loader modules |
| `src/server/routers/projects.py` | **MODIFY** | Expose project capabilities in API responses | loader modules |
| `static/index.html` | **MODIFY** | Template generator UI + preview/editor | templates API |

### Component Boundaries

```
                    +-----------------+
                    |  HTTP Routers   |
                    |  (FastAPI)      |
                    +--------+--------+
                             |
              +--------------+--------------+
              |                             |
    +---------v---------+        +----------v----------+
    | ProjectService    |        | Template Router     |
    | (create, list)    |        | (CRUD + /generate)  |
    +---------+---------+        +----------+----------+
              |                             |
              |  +-- triggers --+           | uses Claude CLI
              |  |              |           | for generation
    +---------v--v----+   +-----v---------+ |
    | AgentLoader     |   | CommandLoader | |
    | (.claude/agents)|   | (.claude/cmds)| |
    +--------+--------+   +------+--------+ |
             |                   |          |
    +--------v-------------------v----------v---+
    |        ContextAssembler                    |
    |  (workspace + claude.md + planning +       |
    |   git log + tasks + agents + commands +    |
    |   settings)                                |
    +--------------------+-----------------------+
                         |
              +----------v----------+
              |   Orchestrator      |
              |   (per-run schema,  |
              |    dynamic registry)|
              +----------+----------+
                         |
              +----------v----------+
              |   Runner            |
              |   (Claude CLI,      |
              |    inline prompts)  |
              +---------------------+
```

---

## Data Flow

### Flow 1: Project Creation with Dynamic Capabilities

```
POST /projects { name, description, template: "fastapi-pg" }
  |
  v
ProjectService.create_project()
  |-- scaffold_from_template("fastapi-pg", target_dir, context)
  |     Copies all files including .claude/agents/, .claude/commands/, .claude/settings.local.json
  |
  |-- git_init_project(project_dir)
  |
  |-- [NEW] discover_capabilities(project_dir)
  |     |-- AgentLoader.discover(project_dir)
  |     |     Reads .claude/agents/db-migrator.md, api-tester.md
  |     |     Returns { "db-migrator": AgentConfig(...), "api-tester": AgentConfig(...) }
  |     |
  |     |-- CommandLoader.discover(project_dir)
  |     |     Reads .claude/commands/migrate.md, seed.md, test-api.md
  |     |     Returns [ CommandConfig(name="migrate", ...), ... ]
  |     |
  |     |-- SettingsLoader.load(project_dir)
  |           Reads .claude/settings.local.json
  |           Returns { "permissions": { "allow": ["Bash", "WebSearch"] } }
  |
  |-- Insert DB record
  |-- Emit PROJECT_CREATED event with capabilities summary
  |
  v
Response: { id, name, slug, path, capabilities: { agents: 2, commands: 3, settings: true } }
```

### Flow 2: Task Execution with Dynamic Agents

```
POST /tasks { prompt, project_id, mode }
  |
  v
TaskHandler.run_task()
  |
  |-- [MODIFIED] registry = get_project_registry(project_path)
  |     |-- Start with DEFAULT_REGISTRY (plan, execute, test, review)
  |     |-- AgentLoader.discover(project_path) -> project agents
  |     |-- merge_registries(default, project) -> merged
  |     |-- Returns: { plan, execute, test, review, db-migrator, api-tester }
  |
  |-- [MODIFIED] schema = build_orchestrator_schema(registry)
  |     JSON schema enum: ["api-tester", "approved", "db-migrator", "execute", "plan", "review", "test"]
  |
  |-- [MODIFIED] context = assemble_full_context(project_path, pool)
  |     Now includes:
  |       available_agents: "- PLAN: Creates structured dev plan\n- DB-MIGRATOR: Database migration specialist..."
  |       available_commands: "- /migrate: Analyze schema, generate migration...\n- /seed: ..."
  |       project_settings: { permissions: { allow: ["Bash", "WebSearch"] } }
  |
  |-- orchestrate_pipeline(ctx, prompt, pool, session_id, registry=registry)
  |     Orchestrator sees all agents in schema enum
  |     System prompt includes project agent descriptions
  |     Can route to db-migrator or api-tester when appropriate
  |
  |     When routing to project agent:
  |       runner uses agent's system_prompt_inline (from .md file content)
  |       instead of system_prompt_file (used by core agents)
```

### Flow 3: AI Template Generation

```
POST /templates/generate { description: "FastAPI app with Stripe payments and webhook handling" }
  |
  v
TemplateGenerateEndpoint
  |-- Build generation prompt:
  |     - User description
  |     - Reference structure from existing template (e.g., fastapi-pg file tree)
  |     - Expected JSON output format
  |     - Instructions for .claude/ convention
  |
  |-- stream_claude(prompt, system_prompt_file="prompts/template_gen_system.txt",
  |                 extra_args=["--json-schema", TEMPLATE_GEN_SCHEMA])
  |
  |-- Parse response -> TemplatePreview
  |     {
  |       id: "fastapi-stripe",
  |       name: "FastAPI + Stripe",
  |       description: "REST API with Stripe payment integration",
  |       files: {
  |         "src/main.py": "from fastapi import FastAPI...",
  |         "CLAUDE.md": "# FastAPI Stripe Project...",
  |         ".claude/agents/payment-handler.md": "You are a payment integration specialist...",
  |         ".claude/commands/test-webhooks.md": "Send test webhook events...",
  |         ".claude/settings.local.json": "{\"permissions\":{\"allow\":[\"Bash\"]}}",
  |         ...
  |       }
  |     }
  |
  v
Response: TemplatePreview JSON (frontend renders tree + editor)
  |
  v
User reviews, edits files in preview
  |
  v
POST /templates { id, name, description, files }   <-- existing endpoint, no changes needed
```

---

## Key Architectural Decisions

### Decision 1: Per-Project Registry, Not Global Mutation

**Do not** mutate the global `AGENT_REGISTRY` when a project loads. Build a scoped registry per task execution.

**Why:** Multiple tasks can run concurrently on different projects (max 2 via semaphore). A global mutable registry creates race conditions and agent leakage between projects.

```python
# src/agents/config.py

# Rename existing constant (alias for backward compat)
DEFAULT_REGISTRY: dict[str, AgentConfig] = { ... }
AGENT_REGISTRY = DEFAULT_REGISTRY  # backward compat

def get_project_registry(project_path: str | None = None) -> dict[str, AgentConfig]:
    """Build a scoped registry: defaults + project agents."""
    registry = dict(DEFAULT_REGISTRY)  # shallow copy
    if project_path:
        from src.agents.loader import discover_project_agents
        project_agents = discover_project_agents(project_path)
        registry = merge_registries(registry, project_agents)
    return registry
```

### Decision 2: Agent Markdown Format with Optional YAML Front-Matter

Template agent `.md` files today are plain text (just a system prompt, no metadata). Define a lightweight front-matter convention:

```markdown
---
name: db-migrator
description: Database migration specialist for PostgreSQL
allowed_transitions:
  - execute
  - review
---

You are a database migration specialist for PostgreSQL with asyncpg...
```

**Fallback for files without front-matter** (backward compatible with existing templates):
- `name`: derived from filename (`db-migrator.md` -> `db-migrator`)
- `description`: `"Project agent: {name}"`
- `allowed_transitions`: `("execute", "review")` as safe defaults
- `system_prompt_inline`: entire file content

**Why front-matter:** Lightest convention that avoids parsing natural language for structured data. YAML front-matter is standard in documentation tooling (Jekyll, Hugo, MDX). Existing template files work without modification.

### Decision 3: Orchestrator Schema Built Per-Run

The current `ORCHESTRATOR_SCHEMA` is a module-level constant computed once at import. Change to per-invocation:

```python
# BEFORE (frozen at import):
ORCHESTRATOR_SCHEMA = _build_orchestrator_schema()

# AFTER (built per task from dynamic registry):
def build_orchestrator_schema(registry: dict[str, AgentConfig]) -> str:
    enum_values = sorted(list(registry.keys()) + ["approved"])
    return json.dumps({
        "type": "object",
        "properties": {
            "next_agent": {"type": "string", "enum": enum_values},
            ...
        },
        ...
    })
```

Pass registry into `orchestrate_pipeline()`. Schema computation is <1ms, no caching needed.

### Decision 4: Template Generation via Claude CLI

Use the existing `stream_claude()` with a generation-specific system prompt and JSON schema. This keeps the stack uniform (Claude CLI everywhere) and reuses the concurrency semaphore (max 2 processes).

**Concurrency:** Template generation takes one Claude CLI slot. Acceptable since generation is infrequent and user-initiated. If a user generates a template while 2 tasks are running, the semaphore makes them wait. This is fine -- generation is not time-critical.

### Decision 5: Commands as Context Injection, Not Execution

Commands (`.claude/commands/*.md`) are injected into the orchestrator's system prompt as available instructions, not executed directly by the console. The Claude CLI agent references them when running.

**Why:** Commands are instructions for Claude ("analyze schema, generate migration"), not for the console to execute. The console's job is to make Claude aware they exist. Avoids building a command execution engine.

### Decision 6: Inline System Prompts for Project Agents

Add `system_prompt_inline: str | None` to `AgentConfig`. The runner checks `system_prompt_inline` first, falls back to `system_prompt_file`. Core agents use file-based prompts (unchanged). Project agents use inline prompts (from `.md` file content).

**Why not write project agent prompts to temp files?** Adds filesystem cleanup complexity. Inline is simpler -- the runner just passes the text differently to Claude CLI (`--system-prompt` flag instead of `--system-prompt-file`).

### Decision 7: Core Agents are Protected from Override

Project agents cannot override core agents (plan, execute, test, review). If a project template ships a `plan.md` in `.claude/agents/`, it is skipped with a warning log.

**Why:** The pipeline depends on core agents having specific `output_sections` and `allowed_transitions`. Overriding them breaks routing logic. A project can add new specialized agents, but cannot modify the pipeline backbone.

---

## Patterns to Follow

### Pattern 1: Discovery Module Structure

Each loader follows the same scan-parse-return pattern:

```python
# src/agents/loader.py
from pathlib import Path
from src.agents.config import AgentConfig

CLAUDE_AGENTS_DIR = ".claude/agents"

def discover_project_agents(project_path: str) -> dict[str, AgentConfig]:
    """Scan .claude/agents/*.md and return dict of agent_name -> AgentConfig."""
    agents_dir = Path(project_path) / CLAUDE_AGENTS_DIR
    if not agents_dir.is_dir():
        return {}
    result = {}
    for md_file in sorted(agents_dir.glob("*.md")):
        config = _parse_agent_md(md_file)
        if config:
            result[config.name] = config
    return result

def _parse_agent_md(md_path: Path) -> AgentConfig | None:
    """Parse a .claude/agents/*.md file into an AgentConfig."""
    content = md_path.read_text(encoding="utf-8", errors="replace")
    name = md_path.stem
    meta, body = _extract_front_matter(content)
    return AgentConfig(
        name=meta.get("name", name),
        system_prompt_file="",
        system_prompt_inline=body,  # NEW field
        description=meta.get("description", f"Project agent: {name}"),
        output_sections=meta.get("output_sections", []),
        next_agent=meta.get("next_agent"),
        allowed_transitions=tuple(meta.get("allowed_transitions", ("execute", "review"))),
    )

def _extract_front_matter(content: str) -> tuple[dict, str]:
    """Extract YAML front-matter from markdown. Returns (metadata, body)."""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    import yaml
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}, content
    return meta, parts[2].strip()
```

### Pattern 2: Registry Merge with Protected Core

```python
PROTECTED_AGENTS = {"plan", "execute", "test", "review"}

def merge_registries(
    default: dict[str, AgentConfig],
    project: dict[str, AgentConfig],
) -> dict[str, AgentConfig]:
    """Merge project agents into default registry. Core agents are protected."""
    merged = dict(default)
    for name, config in project.items():
        if name in PROTECTED_AGENTS:
            log.warning("Project agent '%s' conflicts with core agent, skipping", name)
            continue
        merged[name] = config
    return merged
```

### Pattern 3: Capability Aggregate

```python
# src/context/assembler.py (addition)
def discover_capabilities(project_path: str) -> dict:
    """Discover all project capabilities from .claude/ directory."""
    from src.agents.loader import discover_project_agents
    from src.commands.loader import discover_project_commands
    from src.settings.loader import load_project_settings

    return {
        "agents": discover_project_agents(project_path),
        "commands": discover_project_commands(project_path),
        "settings": load_project_settings(project_path),
    }
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Global Mutable Registry

**What:** Modifying `AGENT_REGISTRY` in place when a project loads.
**Why bad:** Race conditions with concurrent tasks on different projects. Agent contamination between projects.
**Instead:** Build per-project registry as a new dict. Pass through call chain.

### Anti-Pattern 2: Storing Generated Templates in Database

**What:** Saving template file contents as JSON blobs in PostgreSQL.
**Why bad:** Templates are file trees. The existing filesystem-based storage (in `templates/`) works. Adding a database layer duplicates storage and complicates template CRUD which already works.
**Instead:** Keep templates on disk. The existing `POST /templates` endpoint already writes files and updates `registry.yaml`. AI generation produces the same `{files: {path: content}}` dict the create endpoint consumes.

### Anti-Pattern 3: Complex Agent Capability Negotiation

**What:** Building a protocol where agents declare capabilities, negotiate handoffs, or register/unregister during a task.
**Why bad:** Over-engineering. The orchestrator already handles routing via Claude CLI judgment. Project agents just need to appear in the routing enum.
**Instead:** Flat merge into registry. Orchestrator sees all agents equally and routes based on AI judgment.

### Anti-Pattern 4: Separate Orchestration Flow for Project Agents

**What:** Building a different orchestration path for project-specific agents vs core agents.
**Why bad:** Doubles orchestration logic. Creates confusion about which path a task takes.
**Instead:** Single orchestrator, single merged registry. Project agents participate in the same pipeline. The orchestrator routes to them when it judges appropriate.

### Anti-Pattern 5: Writing a Command Execution Engine

**What:** Building infrastructure to actually execute `.claude/commands/*.md` as runnable actions triggered from the UI.
**Why bad:** Commands are Claude instructions, not shell scripts. The console should inform Claude about them, not try to run them itself. Building execution adds security concerns, error handling, and a whole new subsystem.
**Instead:** Inject command descriptions into the orchestrator context. Claude reads them and follows the instructions when relevant.

---

## Suggested Build Order

Dependencies dictate this sequence. Each phase builds on the previous.

### Phase 1: Agent Loader Foundation

```
NEW:    src/agents/loader.py
MODIFY: src/agents/config.py (add system_prompt_inline, get_project_registry, merge_registries)
NEW:    tests/test_agent_loader.py

WHY FIRST: Everything depends on the loader and dynamic registry pattern.
DEPENDS ON: Nothing.
RISK: Low -- new module, minimal changes to existing code.
```

### Phase 2: Commands + Settings Loaders

```
NEW:    src/commands/__init__.py
NEW:    src/commands/loader.py
NEW:    src/settings/__init__.py
NEW:    src/settings/loader.py
NEW:    tests/test_command_loader.py
NEW:    tests/test_settings_loader.py

WHY SECOND: Same pattern as agent loader, simpler scope.
DEPENDS ON: Nothing (parallel with Phase 1 is possible but linear is safer).
RISK: Low -- new modules only.
```

### Phase 3: Context Assembly Integration

```
MODIFY: src/context/assembler.py (add discover_capabilities, enrich assemble_full_context)
MODIFY: tests/test_assembler.py

DEPENDS ON: Phase 1 + 2 (needs all three loaders).
RISK: Low -- additive changes to existing function return value.
```

### Phase 4: Orchestrator Dynamic Registry

```
MODIFY: src/pipeline/orchestrator.py (per-run schema, accept registry param)
MODIFY: src/runner/runner.py (support --system-prompt for inline prompts)
MODIFY: src/agents/config.py (build_agent_enum/descriptions accept registry)
MODIFY: tests/test_orchestrator.py

DEPENDS ON: Phase 1 + 3 (needs dynamic registry + enriched context).
RISK: HIGH -- changes core pipeline behavior. Must test thoroughly.
This is the riskiest phase. Extra test coverage needed.
```

### Phase 5: Project Service Integration

```
MODIFY: src/pipeline/project_service.py (trigger discovery after scaffolding)
MODIFY: src/server/routers/projects.py (expose capabilities in responses)
MODIFY: tests/test_project_service.py

DEPENDS ON: Phase 1 + 2 (needs loaders).
RISK: Medium -- modifies project creation flow.
```

### Phase 6: AI Template Generation

```
MODIFY: src/server/routers/templates.py (add POST /templates/generate)
NEW:    src/agents/prompts/template_gen_system.txt
NEW:    tests/test_template_generation.py

DEPENDS ON: Phase 1 knowledge (to generate valid agent files).
RISK: Medium -- new Claude CLI interaction pattern, but isolated endpoint.
```

### Phase 7: Template Editor UI

```
MODIFY: static/index.html (generator form, tree preview, file editor)

DEPENDS ON: Phase 6 (needs /generate API).
RISK: Low -- pure frontend, no backend changes.
```

### Critical Path

```
Phase 1 ──> Phase 3 ──> Phase 4    (pipeline works with dynamic agents)
   |
   +──> Phase 5                      (creation triggers loading)
   |
   +──> Phase 6 ──> Phase 7          (AI generation + editor UI)

Phase 2 ──> Phase 3                  (commands/settings feed context)
```

Phase 4 (orchestrator changes) is the highest-risk, highest-value phase. It should be built carefully with extensive testing.

---

## Scalability Considerations

| Concern | Current (4 agents) | With templates (4-10 agents) | At 20+ agents |
|---------|---------------------|------------------------------|----------------|
| Registry lookup | O(1) dict | O(1) same | O(1) same |
| Schema build | Computed once at import | Computed per task (<1ms) | Still fast |
| Orchestrator prompt | ~50 tokens for agent list | ~150 tokens | ~400 tokens, may need trimming |
| Agent discovery | N/A | ~5ms filesystem scan | Add TTL cache if >50ms |
| CLI routing quality | Excellent (few choices) | Good | May degrade -- keep under 10 total |

**Practical limit:** Keep total agents per project under 10. The Claude CLI orchestrator's routing quality degrades with too many choices. This is a model limitation, not an architectural one.

---

## Sources

- Direct codebase analysis of all affected files (HIGH confidence)
- `docs/template-system-overhaul.md` -- team-authored design document with architecture proposal (HIGH confidence)
- Existing template structure in `templates/fastapi-pg/.claude/` (HIGH confidence)
- `src/agents/config.py` -- AgentConfig dataclass, registry pattern (HIGH confidence)
- `src/pipeline/orchestrator.py` -- orchestration loop, schema building, routing (HIGH confidence)
- `src/context/assembler.py` -- context assembly pattern (HIGH confidence)
- `src/server/routers/templates.py` -- template CRUD endpoints (HIGH confidence)

---
*Architecture research for: AI Agent Console v2.4 Template System Overhaul*
*Researched: 2026-03-14*
