# Project Research Summary

**Project:** AI Agent Console v2.4 — Template System Overhaul
**Domain:** Dynamic agent/plugin loading + AI-assisted template generation for a self-hosted Claude CLI orchestration console
**Researched:** 2026-03-14
**Confidence:** HIGH

## Executive Summary

AI Agent Console v2.4 solves a fundamental disconnect in the current system: templates already write `.claude/agents/*.md`, `.claude/commands/*.md`, and `.claude/settings.local.json` into project directories during scaffolding, but the runtime never reads them. The four builtin templates ship specialized agents (db-migrator, api-tester, handler-builder) and commands (migrate, seed, test-api) that are completely inert. The v2.4 overhaul activates these files — making templates "live" — and adds AI-driven template generation as the headline user-facing feature.

The recommended approach requires one new pip dependency (`python-frontmatter==1.1.0`) and is architectural in impact rather than additive in technology. The core challenge is that the orchestrator routing schema (`ORCHESTRATOR_SCHEMA`) is a module-level constant frozen at import time. Making templates live means making this schema dynamic per-project, per-task. This single refactor — parameter injection of a project-scoped registry into the orchestration call chain — is the critical path dependency that every other v2.4 feature depends on.

The primary risks are concurrent project contamination (naive global registry mutation poisons sibling tasks) and AI generation consuming the pipeline's constrained semaphore slots. Both have clear, implementable mitigations: never mutate the global registry (build per-task copies), and use a separate generation semaphore with HTTP 429 fallback. A secondary risk is AI-generated templates producing structurally invalid agent files; server-side validation through the same loader before the response reaches the frontend is the required prevention.

---

## Key Findings

### Recommended Stack

The existing stack (Python 3.12.3, FastAPI 0.135.1, Pydantic 2.12.5, asyncpg 0.30+, Jinja2 3.1.2, Alpine.js 3.x, Tailwind CSS 3.x) requires zero changes. All five v2.4 features build on existing patterns. The one addition is `python-frontmatter==1.1.0` for YAML frontmatter parsing — chosen over a custom `---` splitter because it handles encoding edge cases, BOM characters, and embedded `---` in YAML values correctly.

**Core technologies:**
- `python-frontmatter 1.1.0`: Parse YAML metadata + body from agent markdown files — only new dependency; single transitive dep (PyYAML already installed at 6.0.1)
- `pathlib` (stdlib): Directory scanning for agent/command discovery — already used throughout codebase
- `Pydantic 2.12.5` (existing): Validate settings JSON and generated template structure — no `jsonschema` lib needed
- `Claude CLI subprocess` (existing): AI template generation reuses `stream_claude()` with a different JSON schema — no LangChain or API client
- `Alpine.js x-for` (existing): Template tree view + file editor — textarea with monospace styling is sufficient for a single-user tool; CodeMirror/Monaco are not justified

### Expected Features

**Must have (table stakes) — without these, templates remain broken:**
- Agent discovery from `.claude/agents/*.md` — templates ship agent files that do nothing; users selecting FastAPI template expect db-migrator to participate in the pipeline
- Per-project registry scoping — two concurrent projects must not share agent registries; global mutation causes contamination
- Agent registration in orchestrator routing — dynamic agents must appear in the JSON schema enum or the orchestrator can never route to them
- Command discovery from `.claude/commands/*.md` — inject discovered commands into context assembly as available instructions for agents
- Project settings application from `.claude/settings.local.json` — permissions defined in templates must be honored
- Automatic loading on task start — transparent to user; no manual activation step

**Should have (differentiators):**
- AI template generation from natural language — no other self-hosted agent console generates complete `.claude/` scaffolding from a description
- Template preview before save — human verification step critical for AI-generated content before committing
- Template editor with inline file editing — full CRUD on template contents; extends preview tree view

**Defer to v2.5+:**
- Command execution via orchestrator routing — high complexity, requires new pipeline execution path
- Template export/import as ZIP — nice-to-have, low priority
- YAML frontmatter migration for existing template agents — backward compatible, existing plain-text files load with sensible defaults

### Architecture Approach

The architecture follows a discovery-then-injection pattern: three new loader modules scan the project's `.claude/` directory at task start, then feed discovered capabilities into the context assembler and into the orchestrator's per-run schema. The critical refactor is threading a `registry` parameter through the orchestration call chain instead of reading a module-level constant. This is parameter injection — not global mutation — and it is the prerequisite for everything else in v2.4.

**Major components:**
1. `src/agents/loader.py` (NEW) — Scans `.claude/agents/*.md`, parses optional YAML frontmatter with sensible defaults for files lacking metadata; wraps per-file errors gracefully
2. `src/commands/loader.py` / `src/settings/loader.py` (NEW) — Same discovery pattern for commands and settings; feeds into context assembly
3. `src/agents/config.py` (MODIFY) — `AGENT_REGISTRY` becomes `DEFAULT_REGISTRY` (immutable); `get_project_registry(project_path)` returns shallow-copied default merged with project agents; core agents (plan, execute, test, review) are protected from override
4. `src/pipeline/orchestrator.py` (MODIFY) — `ORCHESTRATOR_SCHEMA` changes from module-level constant to `build_orchestrator_schema(registry)` called per task; orchestrator accepts `registry` parameter
5. `src/context/assembler.py` (MODIFY) — `assemble_full_context()` extended with `available_agents`, `available_commands`, and `project_settings` keys
6. `src/server/routers/templates.py` (MODIFY) — New `POST /templates/generate` endpoint using `stream_claude()` with template-generation JSON schema; separate `Semaphore(1)` from pipeline tasks
7. `static/index.html` (MODIFY) — Alpine.js collapsible tree view + inline textarea editor; no build system required

### Critical Pitfalls

1. **Module-level schema constant captures stale registry** — `ORCHESTRATOR_SCHEMA` is computed once at module import (confirmed at `orchestrator.py` line 86). Dynamic agents never appear in the routing enum and are silently ignored. Prevention: convert to `build_orchestrator_schema(registry)` called per task. Must be solved simultaneously with the loader in Phase 1, not deferred.

2. **Global AGENT_REGISTRY mutation causes cross-project contamination** — `AGENT_REGISTRY.update(project_agents)` pollutes concurrent tasks since the system supports 2 concurrent tasks via `asyncio.Semaphore(2)`. Prevention: never mutate the global; always create `merged_registry = {**DEFAULT_REGISTRY, **project_agents}` per task and thread it through the call chain.

3. **AI generation consuming pipeline semaphore slots** — Template generation via Claude CLI shares the same concurrency constraint (7.6GB VPS RAM). Prevention: use a separate `Semaphore(1)` for generation; return HTTP 429 with retry-after when unavailable; add 60s timeout.

4. **Dynamic agent prompts without metadata produce broken routing** — Existing `.md` files are plain text with no frontmatter. The loader must define a minimal frontmatter spec with fallback defaults: name from filename, broad `allowed_transitions` specialist contract, never crash on missing metadata.

5. **AI-generated templates producing invalid agent/command files** — LLMs produce plausible but structurally invalid output (bad YAML, reserved agent names like `plan`/`execute`). Prevention: validate all generated files through the same loader before returning to frontend; include `validation_errors` in the generation response.

---

## Implications for Roadmap

The dependency graph from research dictates a clear build sequence. Phases 1-4 are a strict chain: the loader must exist before the context can consume it, the context must be enriched before the orchestrator can use it, and the orchestrator must accept dynamic registries before project agents can route anywhere. Phases 5-7 deliver the user-facing features on top of that foundation.

### Phase 1: Agent Loader Foundation

**Rationale:** The loader and the dynamic registry pattern are the prerequisite for every downstream component. Pitfalls 1 and 2 (stale schema constant, global mutation) must be resolved here — they cannot be deferred because they invalidate every subsequent phase.
**Delivers:** `src/agents/loader.py`; `AgentConfig` extended with `source` and `file_path` fields (before `frozen=True` makes this hard); `DEFAULT_REGISTRY` (immutable); `get_project_registry(project_path)`; `merge_registries()` with core agent protection; YAML frontmatter format specified with graceful defaults
**Addresses:** Agent discovery (table stakes), per-project registry scoping (table stakes)
**Avoids:** Pitfalls 1, 2, 4, 9, 10, 11, 12

### Phase 2: Commands and Settings Loaders

**Rationale:** Identical pattern to Phase 1 but for commands and settings. Commands must be defined as context-injection targets only (not execution endpoints) to avoid building an unnecessary execution engine.
**Delivers:** `src/commands/loader.py`; `src/settings/loader.py`; `disabled_agents` support in settings merge; security-sensitive settings whitelisted (system flags always win)
**Addresses:** Command discovery (table stakes), settings application (table stakes)
**Avoids:** Pitfalls 7, 14, 15

### Phase 3: Context Assembly Integration

**Rationale:** Loaders produce data; this phase delivers it to the orchestrator's system prompt. Without this phase, loaded agents and commands are discovered but invisible to Claude.
**Delivers:** `assemble_full_context()` extended with `available_agents`, `available_commands`, `project_settings`; orchestrator prompt updated to explain when to route to specialist agents
**Addresses:** Command injection into context (table stakes), automatic loading (table stakes)
**Avoids:** Pitfall 6 (context assembler unaware of dynamic agents)

### Phase 4: Orchestrator Dynamic Registry

**Rationale:** This is the highest-risk, highest-value change. It makes the pipeline actually route to dynamic agents. Requires Phases 1 and 3 to be complete and tested. Extensive test coverage required before merge.
**Delivers:** `build_orchestrator_schema(registry)` per-run function; `orchestrate_pipeline()` accepts `registry` parameter; `build_agent_enum(registry)` and `build_agent_descriptions(registry)` accept registry; runner supports `--system-prompt` flag for inline prompts (no temp files)
**Addresses:** Agent registration in orchestrator routing (table stakes)
**Avoids:** Pitfalls 1 and 2 at the pipeline level
**Risk:** HIGH — test assertion required: project with custom agent, run orchestrator, assert custom agent name appears in schema enum

### Phase 5: Project Service Integration

**Rationale:** Project creation should discover capabilities immediately so the API response includes how many agents and commands loaded. Connects the loader layer to the HTTP layer.
**Delivers:** `discover_capabilities()` called after scaffolding; project creation response includes `capabilities: { agents: N, commands: M, settings: true }`; template scaffolding adds a write lock to prevent concurrent edits causing partial copies
**Addresses:** Automatic loading on project open (table stakes)
**Avoids:** Pitfall 8 (concurrent template edits during scaffolding)

### Phase 6: AI Template Generation

**Rationale:** Headline user-facing feature. Isolated endpoint. The generation semaphore and server-side validation must be built into the initial implementation — not added later.
**Delivers:** `POST /templates/generate` endpoint; `prompts/template_gen_system.txt` dynamically referencing current loader schema; validation of generated agent/command files before response; `validation_errors` field in response; separate `Semaphore(1)` for generation with HTTP 429 fallback
**Addresses:** AI template generation from natural language (differentiator)
**Avoids:** Pitfalls 3, 5, 13

### Phase 7: Template Preview and Editor UI

**Rationale:** Pure frontend work. No backend changes. Depends on the `/generate` API from Phase 6. Alpine.js patterns already used in the codebase make this lower-risk than it appears.
**Delivers:** Alpine.js collapsible tree view + file content display panel; inline textarea editor per file; preview-before-save flow; save triggers existing `POST /templates` endpoint without changes
**Addresses:** Template preview (differentiator), template editor (differentiator)

### Phase Ordering Rationale

- Phases 1-4 form a strict dependency chain and cannot be reordered: loader -> loaders -> context -> pipeline
- Phase 5 depends on Phases 1-2 (loaders must exist) but is independent of Phase 4
- Phases 6-7 depend on Phase 1 knowledge (must understand valid agent file format) but are otherwise independent of Phases 2-5
- "Make templates live" (Phases 1-5) should ship before AI generation (Phases 6-7) — generated templates are only valuable if the live loading system activates them correctly

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4 (Orchestrator Dynamic Registry):** The exact call chain through `orchestrate_pipeline` -> `get_orchestrator_decision` -> `validate_transition` needs line-level mapping before implementation. High regression risk in the core pipeline loop.
- **Phase 6 (AI Template Generation):** The system prompt for template generation is primarily a prompt engineering challenge. Structured output schema helps but generated YAML frontmatter quality requires empirical iteration. Allocate time budget for prompt tuning.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Agent Loader):** File discovery + frontmatter parsing with `python-frontmatter` is fully documented. Working code examples in ARCHITECTURE.md.
- **Phase 2 (Commands/Settings):** Identical pattern to Phase 1.
- **Phase 3 (Context Assembly):** Additive change to existing dict-returning function.
- **Phase 5 (Project Service):** Wiring existing loaders into existing service.
- **Phase 7 (Template Editor UI):** Alpine.js `x-for` with nested data is already in use; textarea binding is standard.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified via `pip show`; python-frontmatter 1.1.0 confirmed on PyPI; no speculation about library choices |
| Features | HIGH | Features derived from direct codebase analysis of what template files exist vs what the runtime reads; the gap is concrete and inspected |
| Architecture | HIGH | All affected files analyzed with line-level specificity; AgentConfig dataclass fields, ORCHESTRATOR_SCHEMA location (line 86), assembler return shape all confirmed |
| Pitfalls | HIGH | All pitfalls derived from direct code analysis, not inference; module-level constant location confirmed; concurrency constraint from semaphore value confirmed |

**Overall confidence:** HIGH

### Gaps to Address

- **Orchestrator call chain depth for Phase 4:** The exact parameter threading path from `run_task()` through all orchestrator helper functions needs to be mapped during Phase 4 planning. ARCHITECTURE.md provides direction but the full list of callsites requires code-level verification.
- **`--system-prompt` vs `--system-prompt-file` flag in installed Claude CLI:** Runner currently only uses `--system-prompt-file`. Adding inline prompt support (Phase 4) requires confirming the exact flag name in the installed Claude CLI version before implementation.
- **Semaphore separation for Phase 6:** If the generation endpoint reuses the same semaphore acquisition function as pipeline tasks, splitting requires a refactor rather than just adding a new semaphore. Verify the acquisition path before Phase 6 planning.
- **AI generation prompt quality:** Structured output schema constrains format but generated YAML frontmatter content quality is empirical. Not a design gap but an execution reality requiring iteration budget in Phase 6.
- **Existing template frontmatter migration:** The 3 non-blank templates have agent files without frontmatter. They load with backward-compatible defaults. Decision needed: migrate now with the Phase 1 work, or migrate on next edit. Either is valid; pick one explicitly.

---

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis — `src/agents/config.py`, `src/pipeline/orchestrator.py`, `src/context/assembler.py`, `src/runner/runner.py`, `src/agents/base.py`, `src/pipeline/project_service.py` (all files read with line-level specificity)
- Existing template structure — `templates/fastapi-pg/.claude/agents/`, `.claude/commands/`, `.claude/settings.local.json` (current format confirmed)
- `python-frontmatter 1.1.0` — confirmed latest stable via `pip index versions`
- `docs/template-system-overhaul.md` — team-authored design document with requirements R1-R5
- `.planning/PROJECT.md` — v2.4 milestone scope definition

### Secondary (MEDIUM confidence)
- [Claude Code .claude folder structure](https://deepwiki.com/FlorianBruniaux/claude-code-ultimate-guide/4.4-the-.claude-folder-structure) — YAML frontmatter conventions for agent markdown files
- [Claude Code settings documentation](https://code.claude.com/docs/en/settings) — settings.json/settings.local.json schema and permission structure
- [AI Agent Architecture Patterns 2025](https://nexaitech.com/multi-ai-agent-architecutre-patterns-for-scale/) — modular agent loading as dominant pattern

### Tertiary (LOW confidence)
- [Cookiecutter vs Yeoman comparison](https://www.cookiecutter.io/article-post/compare-cookiecutter-to-yeoman) — scaffolding tool patterns (referenced only for anti-feature justification)
- [Dynamo MCP dynamic template registry](https://github.com/ruvnet/dynamo-mcp) — template discovery patterns

---
*Research completed: 2026-03-14*
*Ready for roadmap: yes*
