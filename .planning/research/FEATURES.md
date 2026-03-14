# Feature Landscape: Template System Overhaul (v2.4)

**Domain:** AI agent orchestration platform - template/plugin/dynamic loading subsystem
**Researched:** 2026-03-14
**Confidence:** HIGH (codebase analyzed, Claude Code conventions verified, scaffolding patterns researched)

## Context

This research covers v2.4 Template System Overhaul features. The current state: templates create files on disk (Jinja2 scaffolding with `.claude/agents/*.md`, `.claude/commands/*.md`, `.claude/settings.local.json`) but these files are never loaded, parsed, or activated at runtime. The 4 builtin templates (blank, fastapi-pg, telegram-bot, cli-tool) ship agent and command definitions that are completely ignored by the pipeline.

Key integration points in existing code:
- `src/agents/config.py` -- `AGENT_REGISTRY` is a module-level hardcoded dict with 4 agents (plan, execute, test, review). `AgentConfig` dataclass: name, system_prompt_file, description, output_sections, next_agent, allowed_transitions.
- `src/pipeline/orchestrator.py` -- uses `build_agent_enum()` and `build_agent_descriptions()` from config.py. `ORCHESTRATOR_SCHEMA` built once at module load with hardcoded enum.
- `src/context/assembler.py` -- assembles workspace context (files, stack detection, CLAUDE.md, planning docs, git log, recent tasks) but has zero awareness of `.claude/agents/` or `.claude/commands/`.
- `templates/registry.yaml` -- lists 4 templates with id/name/description/builtin flag. No metadata about agents or commands.
- Template `.claude/agents/*.md` files -- plain text system prompts (no YAML frontmatter). Example: `db-migrator.md` is 3 lines of instructions.
- Template `.claude/commands/*.md` files -- plain text command instructions. Example: `migrate.md` is 1 line.
- Template `.claude/settings.local.json` -- JSON with permissions. Example: `{"permissions": {"allow": ["Bash", "WebSearch"]}}`.

---

## Table Stakes

Features users expect. Missing = the template system remains "broken" (files exist but do nothing).

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Agent discovery from `.claude/agents/*.md` | Templates already ship agent files (db-migrator, api-tester, handler-builder, command-builder). Users select "FastAPI + PostgreSQL" template and expect those agents to participate in their pipeline. Currently they are dead files. | Medium | Scan directory, parse MD content, extract name from filename, use file body as system prompt. Convert to `AgentConfig`. New module: `src/agents/loader.py`, ~100 LOC. |
| Agent registration in orchestrator routing | Discovered agents must appear in the orchestrator's JSON schema enum and descriptions, or the AI cannot route to them. `build_agent_enum()` and `build_agent_descriptions()` currently read only the hardcoded `AGENT_REGISTRY`. | Medium | Must accept project-scoped registry. `ORCHESTRATOR_SCHEMA` is built once at module load -- needs to become dynamic per-project. ~50 LOC refactor. |
| Per-project registry scoping | Two projects from different templates must not share agent registries. Project A's `db-migrator` must not bleed into Project B's CLI tool pipeline. The current module-level `AGENT_REGISTRY` is global. | Medium | `AGENT_REGISTRY` becomes a function `get_registry(project_path)` returning defaults + project agents. Orchestrator schema built per-task, not per-import. Touches config.py, orchestrator.py, assembler.py. |
| Command/skill discovery from `.claude/commands/*.md` | Templates ship command files (migrate, seed, test-api, release, deploy-bot). Users expect these to be available as actions during tasks on that project. | Medium | Same pattern as agent discovery. Parse MD for name (from filename) + instructions (from body). Inject into context assembly so orchestrator knows they exist. New module: `src/commands/loader.py`, ~80 LOC. |
| Command injection into context assembly | Discovered commands must be included in the orchestrator's context so it can reference or invoke them. Currently `assemble_full_context()` has no commands section. | Low | Add `commands` key to context dict. Format as list of name+description for system prompt injection. ~30 LOC in assembler.py. |
| Project settings application from `.claude/settings.local.json` | Templates ship settings with permissions (e.g., `{"permissions": {"allow": ["Bash", "WebSearch"]}}`). Not applying them means the execution context ignores template-defined permissions. | Low | Read JSON file, merge with defaults (project overrides global). Simple dict merge. ~50 LOC. Settings affect what tools/permissions are communicated to Claude CLI. |
| Automatic loading on project open / task start | Loading must be transparent. User opens project or starts task, agents/commands/settings load without manual steps. No "click to activate agents" button. | Low | Hook into task creation path (where `project_path` is already known). Call `load_project_agents()` and `discover_project_commands()`. ~20 LOC integration. |
| Default agent preservation | The 4 core agents (plan, execute, test, review) must always be present regardless of template. Template agents supplement the core pipeline, never replace it. | Low | Merge strategy: start with defaults, add project agents. If name collision, project wins with warning log. Core pipeline ordering unchanged. |

---

## Differentiators

Features that set this system apart from basic scaffolding tools (Cookiecutter, Copier, Yeoman). Not expected, but create significant value for an AI agent console.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| AI template generation from natural language | "Create a template for an e-commerce with Next.js and Stripe" produces complete template: directory tree, file contents, CLAUDE.md, specialized agents, commands, settings. No other self-hosted agent console generates full `.claude/` scaffolding from a description. This is the headline feature of v2.4. | High | Claude CLI call with structured output prompt. Must generate coherent file tree + agent definitions + command definitions + settings. Two-step flow: generate (returns JSON), then preview. Risk: output consistency varies per prompt. Mitigation: structured output schema + validation. ~300 backend LOC + endpoint. |
| Template preview before save | User sees the full file tree with contents in an interactive view, can inspect every generated file before committing the template. Critical for AI-generated templates where the output quality needs human verification. | Medium | Frontend: tree view component (collapsible directory listing) + code display panel. Backend: hold generated template in memory, return as JSON. No persistence until user confirms. ~400 frontend LOC (Alpine.js). |
| Template editor (inline file editing) | Modify any file in a template -- both AI-generated (before save) and existing (after save). Add/remove agents, commands, files. Full CRUD on template contents. | Medium | Extends preview component with edit capability. Textarea/code editor per file. API endpoints for update/create/delete template files. Reuses preview tree view. ~200 additional frontend LOC + ~100 backend LOC. |
| Agent metadata via YAML frontmatter | Parse YAML frontmatter in agent `.md` files to extract structured metadata: description, allowed_transitions, output_sections. Aligns with Claude Code's own agent format (which uses frontmatter for name, model, tools, color). Makes template agents first-class citizens with full routing configuration. | Medium | Current template agents are plain text (no frontmatter). Adding frontmatter parsing with `PyYAML` (already a dependency via other tools) allows richer agent definition. Fallback: if no frontmatter, use filename as name and full body as system prompt (backward compatible). |
| Context-aware agent injection into orchestrator prompt | Injected project agents appear in the orchestrator's system prompt with descriptions so the AI can intelligently decide when to route to them. The orchestrator learns "db-migrator: creates idempotent SQL migrations for PostgreSQL" and can decide to invoke it during database tasks. | Low | Already have `build_agent_descriptions()`. Extend to include project agents with descriptions extracted from MD content (first paragraph or frontmatter description). ~20 LOC. |
| Command execution via orchestrator routing | Template commands (migrate, seed, test-api) become actual routing targets. The orchestrator can decide "run the migrate command" as a pipeline step. Commands execute their instructions via Claude CLI within project context. | High | Requires new execution path: command becomes a pseudo-agent. Orchestrator routes to it, system feeds command instructions as prompt to Claude CLI in project directory. Needs new transition type in schema. Deferred: high complexity, pipeline architecture change. |
| Template export/import as ZIP | Export a complete template (directory tree + `.claude/` config) as downloadable ZIP. Import a ZIP to register a new template. Portable templates without git. | Low | Standard `zipfile` module. Export endpoint returns ZIP stream. Import endpoint accepts multipart upload, extracts to templates directory. ~100 LOC total. |

---

## Anti-Features

Features to explicitly NOT build. These were considered and rejected for specific reasons.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Template marketplace / sharing | Single-user system on a personal VPS. Zero other users to share with. Building sharing infrastructure (accounts, permissions, search, ratings) is massive scope creep. Explicitly out of scope in PROJECT.md. | Templates live on disk in the templates/ directory. User can manually copy directories between installations. |
| Template versioning / history | Over-engineering for a system with 4 builtin + occasional custom templates. The templates/ directory is already in a git repo. | `git log templates/my-template/` provides full history. No custom versioning layer needed. |
| Template composition / chaining | "FastAPI + PostgreSQL + Docker + Auth" as composable layers sounds appealing but creates combinatorial conflict resolution: which CLAUDE.md wins? Which agents? Which settings merge how? The complexity grows exponentially. | Each template is self-contained. Use AI generation to describe a combined stack and get a unified template. One template = one coherent configuration. |
| Hot-reloading of agents mid-task | Changing the agent registry while a pipeline is running creates race conditions. The orchestrator schema was built with agent X, but agent X disappears mid-loop. Inconsistent state leads to routing failures. | Agents load at task start and are immutable for the task's lifetime. New agents take effect on next task. Clear lifecycle boundary. |
| Agent dependency graph resolution | Declaring that `db-migrator` requires `api-tester` adds directed graph complexity (topological sort, cycle detection, dependency satisfaction) for minimal benefit in a system with 2-5 custom agents. | Document recommended agent combinations in template CLAUDE.md. Human-readable guidance, zero runtime complexity. |
| Visual drag-and-drop pipeline builder | A graphical agent flow editor is a large frontend project (node graph, connections, validation) that duplicates what the AI orchestrator already does: dynamically decide routing based on output quality. | The AI orchestrator handles routing. `allowed_transitions` in AgentConfig provides guardrails. Users configure via `.claude/agents/*.md` files, not UI drag-and-drop. |
| Import from external git repositories | Cloning GitHub repos as templates requires git credentials management, network access handling, branch selection, conflict resolution. Significant scope creep for a single-user system. | User clones manually to local disk, then registers the directory as a template. Or uses AI generation to describe what they want. |
| Multi-model AI generation | Using OpenAI/Gemini/local models for template generation fragments the codebase and adds credential management. PROJECT.md explicitly scopes to Claude CLI only. | Claude CLI subprocess for all AI generation. Single code path, single auth model (Pro Max subscription via CLI). |
| Real-time template collaboration | Multi-cursor editing, conflict resolution, OT/CRDT. Single-user system. | Single-user Alpine.js editor. No collaboration needed. |

---

## Feature Dependencies

```
Settings application (R3) ---- standalone, no dependencies
    |
    v
Agent discovery (R1) ---- benefits from settings being applied first
    |
    v
Per-project registry scoping ---- architectural requirement for R1
    |
    v
Agent registration in orchestrator ---- requires discovery + scoping
    |
    v
Context-aware agent injection ---- requires registration (extends build_agent_descriptions)
    |
Command discovery (R2) ---- independent of agent discovery, same pattern
    |
    v
Command injection in context assembly ---- requires command discovery

Template preview UI ---- no backend dependencies, frontend work
    |
    v
AI template generation (R4) ---- requires preview UI to display results
    |
    v
Template editor (R5) ---- extends preview UI with edit + save
    |
    v
Template export/import ---- requires template persistence (extends editor)

Agent metadata frontmatter ---- enhances R1, not a dependency
Command execution via orchestrator ---- requires R2 + pipeline changes (defer)
```

### Critical Path

```
Phase 1: R3 (settings) + R1 (agents) + R2 (commands) + scoping
         [all independent, can parallelize]
              |
              v
Phase 2: Preview UI --> R4 (AI generation) --> R5 (editor)
         [sequential dependency chain]
```

---

## MVP Recommendation

### Phase 1: Dynamic Loading (makes templates "live")
Priority: **Highest** -- this is why v2.4 exists.

1. **Agent discovery and loader** (`src/agents/loader.py`) -- scan `.claude/agents/*.md`, parse content, create AgentConfig entries
2. **Per-project registry scoping** -- refactor `AGENT_REGISTRY` from module dict to `get_registry(project_path)` function
3. **Command discovery and loader** (`src/commands/loader.py`) -- scan `.claude/commands/*.md`, parse name + instructions
4. **Settings application** -- read `.claude/settings.local.json`, merge with defaults
5. **Context assembly integration** -- inject agents, commands, settings into `assemble_full_context()` output
6. **Orchestrator dynamic schema** -- build `ORCHESTRATOR_SCHEMA` per-task from actual registry, not hardcoded enum

### Phase 2: AI Generation and Editor (the differentiator)
Priority: **High** -- headline user-facing feature.

7. **Template preview UI** -- Alpine.js tree view + file content display
8. **AI template generation endpoint** -- `POST /templates/generate` with Claude CLI structured output
9. **Template editor** -- extend preview with inline editing, add/remove files, save

### Defer to v2.5+
- Command execution via orchestrator routing (high complexity, pipeline architecture change)
- Template export/import as ZIP (nice-to-have, low priority)
- YAML frontmatter for agent metadata (enhancement, backward compatible, can add anytime)

---

## Complexity Budget

| Feature Group | Estimated LOC | Risk Level | Notes |
|---------------|---------------|------------|-------|
| Discovery + loading (R1, R2, R3) | ~250 | Low | Well-understood pattern: scan dir, parse files, merge config. No external dependencies. |
| Registry scoping refactor | ~150 | Medium | Touches config.py, orchestrator.py, assembler.py. Risk: module-level ORCHESTRATOR_SCHEMA must become dynamic. |
| Context assembly integration | ~80 | Low | Add agents/commands/settings to existing dict output. |
| AI template generation (R4) | ~300 backend | Medium | Claude CLI structured output. Main risk: prompt engineering for consistent output quality. |
| Template preview + editor (R5) | ~600 frontend | Medium | Most complex Alpine.js component so far. Tree view + inline code editor. |
| **Total estimated** | **~1380** | | Reasonable for 2 phases of 2-3 sub-phases each |

---

## Sources

- Codebase analysis: `src/agents/config.py` (AGENT_REGISTRY, AgentConfig dataclass), `src/pipeline/orchestrator.py` (schema building, routing), `src/context/assembler.py` (context assembly), `templates/registry.yaml`, template `.claude/` directories with agent/command/settings files
- [Claude Code .claude folder structure](https://deepwiki.com/FlorianBruniaux/claude-code-ultimate-guide/4.4-the-.claude-folder-structure) -- YAML frontmatter in agent MDs, command format, settings hierarchy, skills directory. HIGH confidence.
- [Claude Code settings documentation](https://code.claude.com/docs/en/settings) -- Official settings.json/settings.local.json schema, permission structure. HIGH confidence.
- [Claude Code project templates guide](https://claudefa.st/blog/guide/development/project-templates) -- Template patterns, CLAUDE.md as convention document, clone-analyze-customize workflow. MEDIUM confidence.
- [Cookiecutter vs Yeoman comparison](https://www.cookiecutter.io/article-post/compare-cookiecutter-to-yeoman) -- Scaffolding tool patterns: composable generators (Yeoman) vs template-only (Cookiecutter). MEDIUM confidence.
- [Claude Agent Skills Framework](https://www.digitalapplied.com/blog/claude-agent-skills-framework-guide) -- Progressive disclosure pattern (metadata first, full instructions on demand), three scopes (personal/project/plugin). MEDIUM confidence.
- [AI Agent Architecture Patterns 2025](https://nexaitech.com/multi-ai-agent-architecutre-patterns-for-scale/) -- Modular agent loading, composable skills as the dominant pattern. MEDIUM confidence.
- [Dynamo MCP dynamic template registry](https://github.com/ruvnet/dynamo-mcp) -- Cookiecutter templates via MCP with discovery, registration, and management. MEDIUM confidence.
- [DLCodeGen: Planning-guided code generation](https://arxiv.org/html/2504.15080v1) -- Structured solution plans as blueprints for LLM code generation, Template RAG approach. MEDIUM confidence.

---
*Feature research for: AI Agent Workflow Console -- v2.4 Template System Overhaul*
*Researched: 2026-03-14*
