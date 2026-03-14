# Phase 28: Orchestrator Dynamic Registry - Research

**Researched:** 2026-03-14
**Domain:** Pipeline orchestration with dynamic agent/command routing
**Confidence:** HIGH

## Summary

Phase 28 is the highest-risk change in v2.4. It threads a per-project `registry` parameter through the entire orchestration call chain so that project-defined agents and commands become routable targets. The good news: Phase 26 already prepared the infrastructure. `AgentConfig` has `system_prompt_inline`, `source`, and `file_path` fields. `get_project_registry()`, `merge_registries()`, `build_agent_enum(registry)`, `build_agent_descriptions(registry)`, `validate_transition(..., registry)`, and `get_agent_config(..., registry)` all accept an optional `registry` parameter. The hard part is wiring these through the actual execution path.

The critical path has 5 touch points that must change simultaneously: (1) `orchestrate_pipeline()` must accept and thread a `registry` parameter, (2) `_build_orchestrator_schema()` must be called per-task with the registry instead of using the module-level `ORCHESTRATOR_SCHEMA` constant, (3) `get_orchestrator_decision()` must receive the registry-specific schema and pass agent descriptions to the system prompt, (4) `WebTaskContext.stream_output()` must resolve agent config from the project registry instead of the global default, and (5) the orchestrator system prompt must dynamically list available agents including project-specific ones. Additionally, commands from `.claude/commands/` need to appear as routing targets, and `stream_claude`/`call_orchestrator_claude` need `--system-prompt` support for inline prompts from project agents.

**Primary recommendation:** Thread `registry` as a parameter from `TaskManager._execute()` through `orchestrate_pipeline()` and into every function that currently reads from the module-level `ORCHESTRATOR_SCHEMA` or calls `get_agent_config()` without a registry. Store the registry on `WebTaskContext` so `stream_output()` can resolve project agents. Keep `ORCHESTRATOR_SCHEMA` as a backward-compatible default for tests but never use it in the live pipeline.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ORCH-01 | Schema built dynamically per-task via `build_orchestrator_schema(registry)` | `_build_orchestrator_schema()` exists at orchestrator.py:63 but is called once at line 86 as module constant. Must convert to per-call with registry param. `build_agent_enum(registry)` already accepts registry (config.py:136). |
| ORCH-02 | Pipeline accepts registry as injected parameter | `orchestrate_pipeline()` at orchestrator.py:253 has no registry param. Must add it. `TaskManager._execute()` at manager.py:102 calls it -- must build registry from `project_path` and pass it. |
| ORCH-03 | Orchestrator can route to project-specific agents | Requires: (a) project agents in schema enum, (b) project agent descriptions in orchestrator system prompt, (c) `stream_output()` resolving inline prompts from registry, (d) `stream_claude` supporting `--system-prompt` flag for inline prompts. |
| CMLD-03 | Commands can be targeted as routing destinations by orchestrator | Commands discovered by `discover_project_commands()` need to be added to the routing enum. When routed to a command, the pipeline needs to run the command's content as an agent prompt. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12.3 | Runtime | Already installed |
| FastAPI | 0.135.1 | HTTP layer | Already used |
| asyncpg | 0.30+ | DB | Already used |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-frontmatter | 1.1.0 | Agent frontmatter parsing | Already installed from Phase 26 |

### No New Dependencies
This phase requires zero new dependencies. All changes are internal refactoring of existing modules.

## Architecture Patterns

### Current Call Chain (MUST change)

```
TaskManager._execute(task_id, prompt, mode, project_path)
  |
  +-> WebTaskContext(task_id, pool, mode, project_path)     # NO registry
  |
  +-> orchestrate_pipeline(ctx, prompt, pool, task_id)      # NO registry
        |
        +-> ctx.stream_output(agent_name, prompt, {})       # Uses get_agent_config(name) -- global registry
        |     |
        |     +-> get_agent_config(agent_name)              # Falls back to AGENT_REGISTRY (global)
        |     +-> stream_claude(prompt, system_prompt_file=config.system_prompt_file)
        |
        +-> get_orchestrator_decision(state, sections)      # Uses module-level ORCHESTRATOR_SCHEMA
        |     |
        |     +-> call_orchestrator_claude(prompt, ORCHESTRATOR_SCHEMA, ORCHESTRATOR_PROMPT_FILE)
        |
        +-> validate_transition(current, next)              # Falls back to AGENT_REGISTRY (global)
```

### Target Call Chain (after Phase 28)

```
TaskManager._execute(task_id, prompt, mode, project_path)
  |
  +-> registry = get_project_registry(project_path)         # NEW: build per-project registry
  +-> WebTaskContext(task_id, pool, mode, project_path, registry=registry)  # NEW: receives registry
  |
  +-> orchestrate_pipeline(ctx, prompt, pool, task_id, registry=registry)   # NEW: receives registry
        |
        +-> schema = build_orchestrator_schema(registry)    # NEW: per-task schema
        +-> system_prompt = build_dynamic_orchestrator_prompt(registry)  # NEW: dynamic agent list
        |
        +-> ctx.stream_output(agent_name, prompt, {})
        |     |
        |     +-> get_agent_config(agent_name, registry=self._registry)  # Uses injected registry
        |     +-> IF config.system_prompt_inline:
        |     |     stream_claude(prompt, system_prompt=config.system_prompt_inline)  # --system-prompt flag
        |     +-> ELSE:
        |           stream_claude(prompt, system_prompt_file=config.system_prompt_file)
        |
        +-> get_orchestrator_decision(state, sections, schema=schema, system_prompt_file=...)
        |     |
        |     +-> call_orchestrator_claude(prompt, schema, system_prompt_file=...)
        |
        +-> validate_transition(current, next, registry=registry)
```

### Pattern 1: Registry Injection Through Context

**What:** Store the registry on `WebTaskContext` so `stream_output()` can resolve project agents without a separate parameter.
**When to use:** When the registry needs to flow through a Protocol boundary (`TaskContext`) where adding parameters would break the interface.
**Example:**
```python
# src/engine/context.py
class WebTaskContext:
    def __init__(self, task_id, pool, mode, project_path=".",
                 connection_manager=None, registry=None):
        self._registry = registry
        # ...

    async def stream_output(self, agent_name, prompt, sections):
        config = get_agent_config(agent_name, registry=self._registry)
        system_prompt_file = config.system_prompt_file or None
        system_prompt_inline = config.system_prompt_inline or None

        if system_prompt_inline:
            kwargs = {"system_prompt": system_prompt_inline}
        else:
            kwargs = {"system_prompt_file": system_prompt_file}

        async for event in stream_claude(prompt, **kwargs):
            # ...
```

### Pattern 2: Dynamic Orchestrator Schema

**What:** Replace the module-level `ORCHESTRATOR_SCHEMA` constant with a per-invocation function call.
**When to use:** Every orchestrator decision call.
**Example:**
```python
# src/pipeline/orchestrator.py
def build_orchestrator_schema(registry: dict[str, AgentConfig]) -> str:
    """Build orchestrator JSON schema from the given registry."""
    return json.dumps({
        "type": "object",
        "properties": {
            "next_agent": {
                "type": "string",
                "enum": build_agent_enum(registry),
            },
            "reasoning": {
                "type": "string",
                "description": "One-line explanation of the routing decision",
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
        },
        "required": ["next_agent", "reasoning", "confidence"],
    })

# Keep backward-compat constant for existing tests
ORCHESTRATOR_SCHEMA = build_orchestrator_schema(DEFAULT_REGISTRY)
```

### Pattern 3: Dynamic Orchestrator System Prompt

**What:** Append project agent descriptions to the orchestrator system prompt so it knows when to route to them.
**When to use:** When the registry contains project agents (source="project").
**Example:**
```python
def build_orchestrator_system_prompt(registry: dict[str, AgentConfig]) -> str:
    """Build orchestrator system prompt with dynamic agent descriptions."""
    base = Path(ORCHESTRATOR_PROMPT_FILE).read_text()

    # Add dynamic agent descriptions
    project_agents = {k: v for k, v in registry.items() if v.source == "project"}
    if project_agents:
        agent_lines = "\n".join(
            f"- {name.upper()}: {cfg.description}" for name, cfg in project_agents.items()
        )
        base += f"\n\nProject-specific specialist agents:\n{agent_lines}\n"
        base += "Route to a specialist when the task involves their specific domain.\n"
        base += "After a specialist completes, evaluate whether more work is needed.\n"

    return base
```

### Pattern 4: Commands as Routing Targets

**What:** Commands from `.claude/commands/` become entries in the orchestrator's routing enum and can be routed to like agents.
**When to use:** CMLD-03 requirement.
**Example:**
```python
# When building the registry, convert commands to pseudo-agent entries
def inject_commands_as_agents(
    registry: dict[str, AgentConfig],
    commands: dict[str, CommandInfo],
) -> dict[str, AgentConfig]:
    """Add command routing targets to the registry."""
    extended = dict(registry)
    for name, cmd in commands.items():
        cmd_agent_name = f"cmd-{name}"  # Prefix to avoid collision
        extended[cmd_agent_name] = AgentConfig(
            name=cmd_agent_name,
            system_prompt_file="",
            system_prompt_inline=cmd.description,  # Command content becomes the prompt
            description=f"Command: {cmd.description[:100]}",
            output_sections=[],
            next_agent=None,
            allowed_transitions=("plan", "execute", "test", "review", "approved"),
            source="command",
            file_path=cmd.file_path,
        )
    return extended
```

### Anti-Patterns to Avoid

- **Mutating ORCHESTRATOR_SCHEMA:** Never update the module-level constant. Build a new schema string per task.
- **Adding registry to TaskContext Protocol:** The Protocol should stay stable. Store registry on the concrete `WebTaskContext` class instead.
- **Reading command .md files at routing time:** Load commands once at task start, not on every routing decision.
- **Writing temp files for inline prompts:** Claude CLI supports `--system-prompt <text>` directly. No temp file needed.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Agent name in schema enum | Custom enum builder | `build_agent_enum(registry)` | Already exists, accepts registry param |
| Agent descriptions in prompt | Manual string formatting | `build_agent_descriptions(registry)` | Already exists, accepts registry param |
| Transition validation | New validation logic | `validate_transition(..., registry)` | Already exists, accepts registry param |
| Config lookup by name | Direct dict access | `get_agent_config(name, registry)` | Already exists, handles KeyError |
| Registry merging | Manual dict merge | `merge_registries(default, project)` | Already exists, protects core agents |

## Common Pitfalls

### Pitfall 1: Module-Level ORCHESTRATOR_SCHEMA Used in get_orchestrator_decision
**What goes wrong:** `get_orchestrator_decision()` at line 207 passes `ORCHESTRATOR_SCHEMA` (the module-level constant) to `call_orchestrator_claude()`. Even if you add a registry parameter to `orchestrate_pipeline()`, the schema passed to the AI is still frozen at import time.
**Why it happens:** The constant is captured at module import. Easy to miss when refactoring.
**How to avoid:** `get_orchestrator_decision()` must accept a `schema` parameter (or build it internally from a registry). The caller (`orchestrate_pipeline`) passes the per-task schema.
**Warning signs:** Project agents never appear in orchestrator routing decisions despite being in the registry.

### Pitfall 2: WebTaskContext.stream_output Uses Global get_agent_config
**What goes wrong:** `stream_output()` at context.py:90 calls `get_agent_config(agent_name)` without a registry parameter. When the orchestrator routes to a project agent like "db-migrator", `get_agent_config` looks in `AGENT_REGISTRY` (global), doesn't find it, and raises KeyError. The pipeline crashes.
**Why it happens:** `WebTaskContext` was created before project agents existed. No one passed it a registry.
**How to avoid:** Store registry on `WebTaskContext.__init__()`. Use it in `stream_output()`: `get_agent_config(agent_name, registry=self._registry)`.
**Warning signs:** KeyError when orchestrator routes to a project agent name.

### Pitfall 3: Inline System Prompt Not Passed to Claude CLI
**What goes wrong:** `stream_claude()` only supports `system_prompt_file` kwarg. Project agents have `system_prompt_inline` (the .md file body) but no file path. Without `--system-prompt` support, project agents run with no system prompt at all.
**Why it happens:** `stream_claude()` was built for core agents that always have `.txt` files.
**How to avoid:** Add `system_prompt: str | None = None` parameter to `stream_claude()`. When provided, use `--system-prompt` CLI flag instead of `--system-prompt-file`. Confirmed: Claude CLI supports `--system-prompt <prompt>` flag.
**Warning signs:** Project agents produce generic output, not domain-specific responses.

### Pitfall 4: TUI streaming.py Also Uses get_agent_config Without Registry
**What goes wrong:** `src/tui/streaming.py:46` calls `get_agent_config(agent_name)` without registry. If anyone uses the TUI path, project agents will crash.
**Why it happens:** TUI was the original UI before web; it was never updated for dynamic agents.
**How to avoid:** Either update TUI streaming to accept registry, or accept that TUI is deprecated and only fix the web path. The TUI is not actively used.
**Warning signs:** TUI crashes with KeyError on project agent names.

### Pitfall 5: Orchestrator System Prompt Has Static Agent List
**What goes wrong:** `orchestrator_system.txt` hardcodes the 4 agent descriptions. The orchestrator AI has no information about project-specific agents beyond seeing their names in the JSON schema enum. It doesn't know when to route to "db-migrator" because the system prompt never explains what it does.
**Why it happens:** The system prompt file is static text, not a template.
**How to avoid:** Build the orchestrator system prompt dynamically. Read the base file, append project agent descriptions. Pass the built prompt to `call_orchestrator_claude` either as an inline prompt or write to a temp file. Since `call_orchestrator_claude` already supports `system_prompt_file`, the simplest approach is to write a temp file or add `--system-prompt` support to `call_orchestrator_claude`.
**Warning signs:** Orchestrator always routes to core agents, never to project specialists.

### Pitfall 6: Command Routing Without Execution Semantics
**What goes wrong:** Commands are added to the routing enum but when routed to, there's no clear execution path. A command's `.md` content is an instruction for Claude, not a system prompt for running code.
**Why it happens:** Commands and agents have different semantics but are being treated identically in routing.
**How to avoid:** When the orchestrator routes to a command, treat it as a single-turn agent run: the command's content becomes the system prompt, the current task context becomes the prompt. After running, the orchestrator evaluates next steps. This is the simplest approach that makes commands functional without a separate execution engine.

## Code Examples

### Example 1: Modified orchestrate_pipeline signature
```python
# Source: src/pipeline/orchestrator.py (to be modified)
async def orchestrate_pipeline(
    ctx: TaskContext,
    prompt: str,
    pool: asyncpg.Pool | None = None,
    session_id: int | None = None,
    registry: dict[str, AgentConfig] | None = None,
) -> OrchestratorState:
    """AI-driven orchestration loop with dynamic agent registry."""
    if registry is None:
        registry = dict(DEFAULT_REGISTRY)

    schema = build_orchestrator_schema(registry)
    # ... rest of loop uses schema and registry
```

### Example 2: Modified get_orchestrator_decision
```python
# Source: src/pipeline/orchestrator.py (to be modified)
async def get_orchestrator_decision(
    state: OrchestratorState,
    latest_sections: dict[str, str],
    schema: str | None = None,
    system_prompt_file: str | None = None,
) -> OrchestratorDecision:
    prompt = build_orchestrator_prompt(state, latest_sections)
    effective_schema = schema or ORCHESTRATOR_SCHEMA
    effective_prompt_file = system_prompt_file or ORCHESTRATOR_PROMPT_FILE
    raw = await call_orchestrator_claude(prompt, effective_schema, effective_prompt_file)
    # ... parse as before
```

### Example 3: stream_claude with inline system prompt support
```python
# Source: src/runner/runner.py (to be modified)
async def stream_claude(
    prompt: str,
    *,
    system_prompt_file: str | None = None,
    system_prompt: str | None = None,  # NEW: inline prompt
    extra_args: list[str] | None = None,
    on_process: callable = None,
) -> AsyncGenerator[str | dict, None]:
    claude = _resolve_claude()
    cmd = [claude, "-p", "--verbose", "--output-format", "stream-json",
           "--dangerously-skip-permissions"]
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]
    elif system_prompt_file:
        cmd += ["--system-prompt-file", system_prompt_file]
    # ...
```

### Example 4: TaskManager._execute with registry
```python
# Source: src/engine/manager.py (to be modified)
async def _execute(self, task_id, prompt, mode, project_path):
    try:
        async with self._semaphore:
            # Build per-project registry
            from src.agents.config import get_project_registry
            registry = get_project_registry(project_path)

            # Also inject commands as routing targets
            from src.commands.loader import discover_project_commands
            from src.agents.config import AgentConfig
            commands = discover_project_commands(project_path)
            # ... inject commands into registry

            ctx = WebTaskContext(
                task_id=task_id, pool=self._pool, mode=mode,
                project_path=project_path,
                connection_manager=self._connection_manager,
                registry=registry,  # NEW
            )
            await orchestrate_pipeline(ctx, prompt, self._pool, task_id, registry=registry)
```

## Affected Files Summary

| File | Change Type | What Changes |
|------|-------------|-------------|
| `src/pipeline/orchestrator.py` | MODIFY | `orchestrate_pipeline()` gets `registry` param; `get_orchestrator_decision()` gets `schema` param; `_build_orchestrator_schema()` renamed to `build_orchestrator_schema(registry)` (public); `ORCHESTRATOR_SCHEMA` kept as backward-compat default; dynamic orchestrator system prompt building |
| `src/engine/context.py` | MODIFY | `WebTaskContext.__init__()` gets `registry` param; `stream_output()` uses `get_agent_config(name, registry=self._registry)`; supports `system_prompt` kwarg for inline prompts |
| `src/engine/manager.py` | MODIFY | `_execute()` builds registry via `get_project_registry(project_path)`, injects commands, passes to `WebTaskContext` and `orchestrate_pipeline()` |
| `src/runner/runner.py` | MODIFY | `stream_claude()` gets `system_prompt: str` kwarg for `--system-prompt` flag; `call_orchestrator_claude()` may also need inline prompt support |
| `src/agents/config.py` | MINOR | Possibly add command-to-agent conversion helper; existing functions already support registry param |
| `src/agents/prompts/orchestrator_system.txt` | KEEP | Base prompt stays. Dynamic parts appended at runtime. |
| `tests/test_orchestrator.py` | MODIFY | Tests need updating for new signatures; add tests for dynamic schema with project agents |
| `tests/test_pipeline_extension.py` | MODIFY | Update tests that import `ORCHESTRATOR_SCHEMA` directly |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio |
| Config file | pytest.ini or pyproject.toml |
| Quick run command | `python -m pytest tests/test_orchestrator.py tests/test_pipeline_extension.py -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ORCH-01 | Schema enum includes project agents when built with merged registry | unit | `python -m pytest tests/test_orchestrator.py::TestDynamicSchema -x` | Wave 0 |
| ORCH-02 | `orchestrate_pipeline()` accepts and uses registry param | unit | `python -m pytest tests/test_orchestrator.py::TestOrchestrateWithRegistry -x` | Wave 0 |
| ORCH-03 | Routing to project agent executes with inline system prompt | unit | `python -m pytest tests/test_orchestrator.py::TestProjectAgentRouting -x` | Wave 0 |
| CMLD-03 | Commands appear in routing enum and are routable | unit | `python -m pytest tests/test_orchestrator.py::TestCommandRouting -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_orchestrator.py tests/test_pipeline_extension.py tests/test_agent_config.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_orchestrator.py::TestDynamicSchema` -- tests for `build_orchestrator_schema(registry)` with project agents
- [ ] `tests/test_orchestrator.py::TestOrchestrateWithRegistry` -- test `orchestrate_pipeline` accepts registry, passes to decision function
- [ ] `tests/test_orchestrator.py::TestProjectAgentRouting` -- test routing to project agent uses inline system prompt
- [ ] `tests/test_orchestrator.py::TestCommandRouting` -- test commands as routing targets
- [ ] Update existing tests that import `ORCHESTRATOR_SCHEMA` as constant to use `build_orchestrator_schema()`

## Open Questions

1. **Should `call_orchestrator_claude` also support `--system-prompt` for inline text?**
   - What we know: Currently only supports `--system-prompt-file`. The dynamic orchestrator prompt with project agent descriptions needs to be passed somehow.
   - What's unclear: Whether to write a temp file or add inline support.
   - Recommendation: Add `system_prompt: str | None` param to `call_orchestrator_claude()`, matching `stream_claude()`. Use `--system-prompt` flag. Avoids temp file cleanup.

2. **How should commands differ from agents in routing behavior?**
   - What we know: Commands are instructions for Claude, agents have system prompts. Both can be routing targets.
   - What's unclear: Should commands run as single-turn or multi-turn? Should they have their own section parsing?
   - Recommendation: Treat commands as single-turn agents with their content as system prompt. No special section parsing -- just raw output. After a command runs, orchestrator evaluates next steps normally.

3. **Should the `TaskContext` Protocol gain a `registry` property?**
   - What we know: Protocol currently has `project_path` and `mode`. Adding `registry` would require updating all implementations.
   - What's unclear: Whether other TaskContext implementations (TUI) need registry access.
   - Recommendation: Do NOT add to Protocol. Store on `WebTaskContext` concretely. TUI is not actively maintained. Keep Protocol stable.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of `src/pipeline/orchestrator.py` (454 lines) -- full call chain traced
- Direct codebase analysis of `src/engine/context.py` (217 lines) -- `stream_output()` flow traced
- Direct codebase analysis of `src/engine/manager.py` (320 lines) -- `_execute()` flow traced
- Direct codebase analysis of `src/runner/runner.py` (205 lines) -- CLI flag construction traced
- Direct codebase analysis of `src/agents/config.py` (220 lines) -- all registry functions confirmed to accept optional registry param
- Direct codebase analysis of `src/agents/loader.py` (89 lines) -- `discover_project_agents()` confirmed working
- Direct codebase analysis of `src/commands/loader.py` (79 lines) -- `discover_project_commands()` confirmed working
- Claude CLI `--help` output -- confirmed `--system-prompt <prompt>` flag exists
- `tests/test_orchestrator.py` (256 lines) -- existing test coverage mapped
- `tests/test_pipeline_extension.py` -- existing PIPE-01 through PIPE-05 tests mapped

### Secondary (MEDIUM confidence)
- `.planning/research/ARCHITECTURE.md` -- architecture decisions from project-level research
- `.planning/research/PITFALLS.md` -- pitfalls catalogue from project-level research

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all existing code analyzed line-by-line
- Architecture: HIGH -- full call chain traced through 6 source files, all function signatures verified
- Pitfalls: HIGH -- every pitfall identified from direct code analysis with specific line numbers
- CLI flags: HIGH -- `--system-prompt` confirmed via `claude --help`

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (stable codebase, no external dependencies changing)
