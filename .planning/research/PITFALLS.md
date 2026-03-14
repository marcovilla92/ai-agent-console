# Domain Pitfalls

**Domain:** Dynamic agent/plugin loading + AI template generation added to existing agent pipeline
**Researched:** 2026-03-14
**System:** AI Agent Console v2.4 -- FastAPI + Claude CLI subprocess + Alpine.js SPA

---

## Critical Pitfalls

Mistakes that cause rewrites, broken pipelines, or data loss.

### Pitfall 1: Module-Level Constant Captures the Hardcoded Registry

**What goes wrong:** `ORCHESTRATOR_SCHEMA` is computed once at module import time via `_build_orchestrator_schema()`, which calls `build_agent_enum()` on the static `AGENT_REGISTRY`. When dynamic agents are loaded per-project, the orchestrator schema enum still only contains `["approved", "execute", "plan", "review", "test"]`. Claude CLI returns a dynamically-loaded agent name (e.g. `"db-migrator"`) but it fails JSON schema validation or gets rejected by `validate_transition()`.

**Why it happens:** The current code stores `ORCHESTRATOR_SCHEMA = _build_orchestrator_schema()` as a module-level constant in `orchestrator.py` (line 86). This is evaluated exactly once when the module is first imported. Dynamic agents loaded later never appear in the schema.

**Consequences:** Dynamically loaded agents are invisible to the orchestrator. It can never route to them. The entire dynamic loading feature silently does nothing useful.

**Warning signs:**
- Orchestrator always routes to the same default agents despite project having custom agents
- Claude CLI structured output never contains dynamic agent names
- `validate_transition()` logs warnings about invalid transitions to agent names that should exist

**Prevention:**
- Make `ORCHESTRATOR_SCHEMA` a function call, not a constant: `def get_orchestrator_schema(registry)` that accepts the current registry
- Pass the per-project registry into `get_orchestrator_decision()` and `build_orchestrator_prompt()`
- The orchestrator prompt (built by `build_agent_descriptions()`) must also receive the merged registry
- Write a test: create project with custom agent, run orchestrator, assert custom agent appears in schema enum

**Phase to address:** Phase 1 (agent loader) -- this must be solved simultaneously with the loader, not deferred.

---

### Pitfall 2: Mutating the Global AGENT_REGISTRY Across Concurrent Projects

**What goes wrong:** The naive approach is `AGENT_REGISTRY.update(project_agents)`. Since `AGENT_REGISTRY` is a module-level global dict, loading agents for Project A pollutes the registry for Project B (which may be running concurrently on the other semaphore slot). Project B sees agents from Project A's template. Worse: if projects use agents with the same name (e.g. both have a `helper` agent), they silently overwrite each other.

**Why it happens:** Python module globals are shared across the entire process. The system supports 2 concurrent tasks via `asyncio.Semaphore(2)`. Both tasks share the same event loop and module state.

**Consequences:** Agent cross-contamination between concurrent tasks. Wrong system prompts applied. Unpredictable routing. Debugging nightmare because behavior depends on task execution order.

**Warning signs:**
- Agent descriptions in orchestrator prompt mention tools/domains from a different project
- Intermittent test failures when running concurrent task tests
- Agent count in registry keeps growing across task runs

**Prevention:**
- Never mutate `AGENT_REGISTRY`. Treat it as an immutable default.
- Create a per-task `merged_registry` by copying the default and adding project agents: `registry = {**AGENT_REGISTRY, **project_agents}`
- Thread the registry through the orchestration loop via `OrchestratorState` or a new context parameter
- `build_agent_enum(registry)` and `build_agent_descriptions(registry)` must accept registry as argument
- `validate_transition(from_agent, to_agent, registry)` must accept registry as argument

**Phase to address:** Phase 1 (agent loader) -- architecture decision that affects every downstream component.

---

### Pitfall 3: AI Template Generation Consuming Both Semaphore Slots

**What goes wrong:** The AI template generation endpoint (`POST /templates/generate`) calls Claude CLI to generate a template. If a user triggers generation while 2 tasks are already running, the request blocks indefinitely on the semaphore. If generation itself counts as a task, it consumes one of only 2 available slots, halving the system's task capacity during generation.

**Why it happens:** The system has `asyncio.Semaphore(2)` as a hard constraint due to 7.6GB RAM on the VPS. Claude CLI subprocess uses significant memory. Template generation requires a Claude CLI call but is not a pipeline task -- it is an API request that should feel responsive.

**Consequences:** Either (a) generation blocks forever when slots are full, making the endpoint appear broken, or (b) generation steals a slot, causing running pipeline tasks to stall waiting for their next agent call.

**Warning signs:**
- Template generation hangs with no error when tasks are running
- Pipeline tasks suddenly take much longer when someone generates a template
- OOM kills on the VPS during concurrent generation + pipeline execution

**Prevention:**
- Use a separate, smaller semaphore for generation (e.g. `Semaphore(1)`) that does NOT share with the pipeline semaphore
- Return 429 (Too Many Requests) if the generation semaphore is unavailable, with a retry-after header
- Consider using `--max-turns 1` for template generation to limit Claude CLI resource usage
- Add a timeout on the generation call (60s) so the endpoint never hangs indefinitely
- Frontend should show a clear "generating..." state and handle 429 gracefully

**Phase to address:** Phase 4 (AI template generation) -- must be designed before implementing the endpoint.

---

### Pitfall 4: Dynamic Agent System Prompts as Markdown Blobs Without Structure

**What goes wrong:** Template agent files like `handler-builder.md` contain a free-form markdown paragraph (existing example: "You are a database migration specialist..."). The loader parses these and must produce `AgentConfig` objects with `name`, `description`, `output_sections`, `next_agent`, and `allowed_transitions`. But the markdown files have none of this structured metadata. The loader either invents values (wrong) or leaves critical fields empty (broken routing).

**Why it happens:** The existing `.claude/agents/*.md` files in templates were written as Claude Code system prompts (which only need prose). They were never designed to contain pipeline metadata like `output_sections` or `allowed_transitions`.

**Consequences:** Dynamic agents either (a) break the pipeline because they lack `output_sections` (parser cannot extract structured handoffs), (b) have no `allowed_transitions` so `validate_transition()` allows everything (unsafe), or (c) require a complex frontmatter format that makes template authoring painful.

**Warning signs:**
- Loaded agents produce unstructured output that the section parser cannot split
- Orchestrator routes to dynamic agents but they have no valid transitions out
- Template authors confused about required metadata format

**Prevention:**
- Define a minimal YAML frontmatter format for agent markdown files:
  ```yaml
  ---
  name: db-migrator
  description: Creates database migrations
  role: specialist
  ---
  ```
- Default behavior for `role: specialist`: allowed_transitions = back to the agent that routed here + "approved". No `next_agent` (returns control to orchestrator after completion).
- Do NOT require `output_sections` -- let the section parser handle any sections found. Dynamic agents should not enforce a rigid section schema.
- Provide sensible defaults: if no frontmatter, derive `name` from filename, set `description` to first line of content, use `role: specialist` default.
- Validate at load time: log warnings for agents missing frontmatter, never crash.

**Phase to address:** Phase 1 (agent loader) -- the metadata format is a design decision that affects templates, the editor, and AI generation.

---

### Pitfall 5: AI-Generated Templates Producing Invalid Agent/Command Files

**What goes wrong:** Claude generates template content via a single prompt. The generated `.claude/agents/*.md` files may lack the required frontmatter format, use invalid YAML, reference non-existent transitions, or define agents that conflict with default pipeline agents (e.g. naming a custom agent `plan` or `execute`). The generated template passes the preview step but fails when actually used to create a project.

**Why it happens:** LLMs produce syntactically plausible but structurally invalid output. Without validation between generation and preview, the user sees a template that looks correct but is broken at runtime.

**Consequences:** User creates a project from an AI-generated template, starts a task, and the pipeline breaks mid-execution. Trust in AI generation erodes. User cannot debug because the error is in agent loading, not in the visible template files.

**Warning signs:**
- AI-generated templates work in preview but fail when creating actual projects
- Agent names in generated templates shadow default agent names
- Generated YAML frontmatter has syntax errors (wrong indentation, missing colons)

**Prevention:**
- Validate generated templates programmatically before returning them to the frontend:
  - Parse all `.claude/agents/*.md` files through the same loader the runtime uses
  - Check for name collisions with `AGENT_REGISTRY` defaults
  - Validate `.claude/settings.local.json` is valid JSON
  - Validate `.claude/commands/*.md` files have required structure
- Include a `"validation_errors"` field in the generation response so the frontend can highlight problems
- In the generation prompt, include the exact frontmatter schema as a constraint
- Reserved names list: `["plan", "execute", "test", "review", "orchestrator", "approved"]`

**Phase to address:** Phase 4 (AI generation) -- validation must be part of the generation endpoint, not added later.

---

## Moderate Pitfalls

### Pitfall 6: Context Assembler Not Passing Dynamic Agent Info to Orchestrator

**What goes wrong:** The context assembler (`assemble_full_context`) currently builds workspace context with file listings, CLAUDE.md, planning docs, git log, and recent tasks. It knows nothing about dynamically loaded agents or commands. The orchestrator receives no information about what custom agents are available beyond what the schema enum says, so it has no semantic understanding of when to route to them.

**Prevention:**
- Extend `assemble_full_context` to accept and include the merged agent registry
- Add a new section to the orchestrator system prompt listing available dynamic agents with their descriptions
- The orchestrator prompt template must be modified to explain that custom agents exist and when to use them
- The context must clearly distinguish default pipeline agents (always present) from project specialists (domain-specific)

**Phase to address:** Phase 1 (agent loader) and Phase 2 (commands) -- context assembly changes span both.

---

### Pitfall 7: Settings Override Breaking Pipeline Security

**What goes wrong:** `.claude/settings.local.json` is loaded and applied per-project. If a template's settings include permissions or configurations that conflict with the pipeline's hardcoded `--dangerously-skip-permissions` flag (see `runner.py` line 55), behavior becomes unpredictable. Conversely, a carelessly crafted template could set permissive settings that override intended restrictions.

**Prevention:**
- Define a clear precedence: system flags > project settings > template defaults
- Whitelist which settings keys the loader will apply. Ignore security-sensitive keys from templates.
- Log when template settings conflict with system flags
- Never let template settings modify the runner's CLI flags -- those are system-level, not project-level

**Phase to address:** Phase 3 (settings application).

---

### Pitfall 8: Template Editor Allowing Edits That Break Running Projects

**What goes wrong:** The template editor (R5) allows modifying templates after they are saved. If a user edits a template while a new project is being scaffolded from it, partial/inconsistent files get copied. Additionally, users may expect edits to propagate to existing projects (they do not -- templates are snapshot-copied at creation time).

**Prevention:**
- Templates are snapshotted at project creation time -- document this clearly in UI ("Editing this template affects future projects only")
- Add a lock or "in-use" flag during scaffolding to prevent concurrent edits
- Never hot-reload template changes into running projects (out of scope, keep it that way)

**Phase to address:** Phase 5 (template editor).

---

### Pitfall 9: Agent Markdown Parsing Fragility

**What goes wrong:** The loader must parse markdown files with optional YAML frontmatter. Edge cases: files without frontmatter, files with `---` in the body text (not frontmatter delimiters), files with BOM characters, Windows line endings, empty files, binary files accidentally placed in the directory. Each edge case crashes the loader or produces garbled agent configs.

**Prevention:**
- Use `python-frontmatter` library (well-tested, handles edge cases) instead of a custom parser
- Wrap parsing in try/except per file: a broken agent file should log a warning and be skipped, never crash the project load
- Add a `loaded_agents` count to the project context API response so the frontend can show "3 of 4 agents loaded (1 error)"
- Test with: empty file, no frontmatter, duplicate frontmatter delimiters, binary file, oversized file

**Phase to address:** Phase 1 (agent loader).

---

### Pitfall 10: `frozen=True` on AgentConfig Preventing Dynamic Extension

**What goes wrong:** `AgentConfig` is defined with `@dataclass(frozen=True)` in `config.py`. This means you cannot add attributes after creation. If the dynamic loader needs to add metadata (e.g. `source="project"`, `file_path="/path/to/agent.md"`) to distinguish dynamic agents from defaults, it must create a new dataclass or subclass, adding complexity.

**Prevention:**
- Add the needed fields now before writing the loader: `source: str = "default"` and `file_path: str | None = None`
- Prefer adding fields to the existing dataclass over creating a separate `DynamicAgentConfig` subclass -- avoid type-checking complexity
- Keep `frozen=True` (good practice for immutability); just add the fields upfront

**Phase to address:** Phase 1 (agent loader) -- first thing to change before writing the loader.

---

### Pitfall 11: Dynamic Agents Without Routing Rules Create Dead Ends

**What goes wrong:** A dynamically loaded agent (e.g. `db-migrator`) has no `next_agent` and empty `allowed_transitions`. The orchestrator routes to it, it runs successfully, but then `validate_transition()` has no valid forward path. The fallback logic (`config.next_agent or "approved"`) returns `"approved"`, prematurely ending the pipeline after one specialist agent run.

**Prevention:**
- Define a `specialist` agent contract: after a specialist runs, the orchestrator always evaluates what to do next (route back to the calling context agent, or move forward in the default pipeline)
- Set `allowed_transitions` for specialists to `("plan", "execute", "test", "review", "approved")` -- let the orchestrator decide freely
- The orchestrator system prompt must explain: "After a specialist agent, decide whether the task needs further work (route to execute/review) or is complete (approved)"

**Phase to address:** Phase 1 (agent loader).

---

## Minor Pitfalls

### Pitfall 12: Filename-to-Agent-Name Mapping Collisions

**What goes wrong:** Agent name derived from filename (`db-migrator.md` -> `db-migrator`) may conflict with reserved names or contain characters that cause issues. Filenames with spaces, dots, or unicode are problematic in JSON schema enums and dict keys.

**Prevention:**
- Sanitize filenames to agent names: lowercase, replace spaces with hyphens, strip non-alphanumeric-hyphen characters
- Reject names that collide with reserved names (`plan`, `execute`, `test`, `review`, `orchestrator`, `approved`) at load time with a warning
- Log the filename-to-name mapping for debuggability

**Phase to address:** Phase 1 (agent loader).

---

### Pitfall 13: AI Generation Prompt Becoming Stale

**What goes wrong:** The system prompt for AI template generation hardcodes the available frontmatter fields, template structure conventions, and file patterns. As the system evolves (new frontmatter fields, new `.claude/` conventions), the generation prompt falls behind and produces templates using the old format.

**Prevention:**
- Generate the AI template prompt dynamically from the same schema definitions used by the loader
- Include a concrete working template (e.g. `fastapi-pg`) in the generation prompt as a reference example
- When the loader schema changes, the generation prompt automatically reflects it

**Phase to address:** Phase 4 (AI generation).

---

### Pitfall 14: No Way to Disable Default Agents Per-Project

**What goes wrong:** A project loads custom agents but cannot disable or replace the default `test` agent (which does static analysis). For some project types, the default test agent is inappropriate but it still runs because the pipeline always includes defaults.

**Prevention:**
- Support a `disabled_agents` list in project settings: `{"disabled_agents": ["test"]}`
- The merge function should check this and exclude specified defaults
- Guard against disabling core agents: `plan` and `execute` should be non-disablable

**Phase to address:** Phase 3 (settings application).

---

### Pitfall 15: Commands Loaded But Never Invocable

**What goes wrong:** The command loader discovers `.claude/commands/*.md` files and parses them, but there is no execution path. Commands need to be either (a) injected into agent system prompts so agents know they can use them, or (b) exposed as API endpoints the user can trigger. Without an execution mechanism, loaded commands are dead data.

**Prevention:**
- Define clear command semantics: commands are injected into the context assembly as available instructions for agents, NOT as user-triggerable API endpoints (that would be a much larger feature)
- The agent system prompt should include: "Available project commands: [list with descriptions]"
- Defer user-triggerable commands to a future milestone

**Phase to address:** Phase 2 (command loader).

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Agent loader (Phase 1) | Module-level constants capture stale registry (#1, #2) | Pass registry as parameter everywhere, never mutate global |
| Agent loader (Phase 1) | Markdown parsing edge cases (#9) | Use `python-frontmatter`, skip broken files gracefully |
| Agent loader (Phase 1) | Frozen dataclass blocks extension (#10) | Add `source` and `file_path` fields to AgentConfig first |
| Agent loader (Phase 1) | No metadata in existing agent .md files (#4) | Define frontmatter format with sensible defaults for missing fields |
| Agent loader (Phase 1) | Dynamic agents create routing dead ends (#11) | Define specialist contract with broad allowed_transitions |
| Agent loader (Phase 1) | Context assembler unaware of dynamic agents (#6) | Extend context assembly to include dynamic agent descriptions |
| Command loader (Phase 2) | Commands loaded but not usable (#15) | Inject into context assembly, not as separate API endpoints |
| Settings application (Phase 3) | Security-sensitive settings overridden (#7) | Whitelist allowed settings keys |
| Settings application (Phase 3) | No way to disable inappropriate default agents (#14) | Support `disabled_agents` in settings |
| AI generation (Phase 4) | Semaphore starvation under load (#3) | Separate semaphore for generation, return 429 when busy |
| AI generation (Phase 4) | Generated files fail validation (#5) | Validate through loader before returning to frontend |
| AI generation (Phase 4) | Generation prompt becomes stale (#13) | Generate prompt dynamically from loader schema |
| Template editor (Phase 5) | Edits during scaffolding cause corruption (#8) | Lock template during scaffolding |

---

## Sources

- Direct codebase analysis: `src/agents/config.py` (149 lines), `src/pipeline/orchestrator.py` (454 lines), `src/pipeline/project_service.py` (208 lines), `src/context/assembler.py` (283 lines), `src/runner/runner.py` (203 lines), `src/agents/base.py` (74 lines)
- Existing template structure: `templates/fastapi-pg/.claude/agents/db-migrator.md`, `templates/telegram-bot/.claude/agents/handler-builder.md`
- Project constraints: `.planning/PROJECT.md` (v2.4 milestone definition)
- Design document: `docs/template-system-overhaul.md` (requirements R1-R5)
- Confidence: HIGH -- all pitfalls derived from direct analysis of existing code paths and architecture, not external sources

---
*Pitfalls research for: v2.4 Template System Overhaul -- dynamic agent/plugin loading, AI template generation*
*Researched: 2026-03-14*
