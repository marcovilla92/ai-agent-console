---
phase: 28-orchestrator-dynamic-registry
verified: 2026-03-14T19:00:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
human_verification:
  - test: "Route a real task to a project agent"
    expected: "Agent executes with its markdown file content as inline system prompt via --system-prompt CLI flag"
    why_human: "Cannot launch Claude CLI subprocess in verification environment; requires real task execution"
---

# Phase 28: Orchestrator Dynamic Registry Verification Report

**Phase Goal:** The orchestrator builds its routing schema dynamically per-task from the injected registry — project agents and commands become routable targets in the pipeline
**Verified:** 2026-03-14T19:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Plan 01)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `build_orchestrator_schema(registry)` produces a JSON schema whose `next_agent` enum includes project agent names | VERIFIED | `orchestrator.py:63-87` — calls `build_agent_enum(registry)` which sorts all registry keys + "approved" |
| 2 | `stream_claude` supports `--system-prompt` flag for inline prompts from project agents | VERIFIED | `runner.py:57-59` — `if system_prompt: cmd += ["--system-prompt", system_prompt]` with inline-wins logic |
| 3 | `call_orchestrator_claude` supports `--system-prompt` flag for dynamic orchestrator prompts | VERIFIED | `runner.py:155,169-172` — same inline-wins pattern implemented |
| 4 | `inject_commands_as_agents` converts `CommandInfo` dicts into `AgentConfig` entries with `cmd-` prefix | VERIFIED | `config.py:196-245` — creates `AgentConfig(name=f"cmd-{cmd_name}", source="command", system_prompt_inline=content, ...)` |
| 5 | `build_orchestrator_system_prompt` appends project agent descriptions to base prompt text | VERIFIED | `orchestrator.py:98-126` — filters `source in ("project", "command")`, appends "Project-specific specialist agents:" section |

### Observable Truths (Plan 02)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 6 | `orchestrate_pipeline` accepts a `registry` parameter and uses it for schema building, decision calls, and transition validation | VERIFIED | `orchestrator.py:301-307` — `registry` kwarg; lines 326-327 build schema+prompt; line 387 passes `schema=schema, system_prompt=orch_system_prompt`; line 389 passes `registry=registry` to `validate_transition` |
| 7 | `WebTaskContext` stores registry and uses it in `stream_output` to resolve project agents with inline system prompts | VERIFIED | `context.py:47-54` — `registry` stored as `self._registry`; `stream_output` line 93 calls `get_agent_config(agent_name, registry=self._registry)`; lines 94-98 pick `system_prompt_inline` over `system_prompt_file` |
| 8 | `TaskManager._execute` builds a per-project registry (including command injection) and passes it to both `WebTaskContext` and `orchestrate_pipeline` | VERIFIED | `manager.py:104-122` — `_build_registry` static method calls `get_project_registry` + `inject_commands_as_agents`; `_execute` lines 139,141-148,153 pass `registry=registry` to both |
| 9 | Backward compatibility: calling `orchestrate_pipeline` without registry falls back to `DEFAULT_REGISTRY` | VERIFIED | `orchestrator.py:322-323` — `if registry is None: registry = dict(DEFAULT_REGISTRY)` |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/runner/runner.py` | `system_prompt` kwarg on both runner functions | VERIFIED | Lines 38, 155 — both functions accept `system_prompt: str \| None = None`; inline takes priority over file |
| `src/pipeline/orchestrator.py` | Public `build_orchestrator_schema(registry)`, `build_orchestrator_system_prompt(registry)` | VERIFIED | Lines 63, 98 — both public functions with registry param; backward-compat `ORCHESTRATOR_SCHEMA` constant at line 91 |
| `src/agents/config.py` | `inject_commands_as_agents` helper | VERIFIED | Lines 196-245 — full implementation with collision detection, file reading, and proper AgentConfig construction |
| `src/engine/context.py` | `WebTaskContext` with `_registry` field, inline prompt support in `stream_output` | VERIFIED | Lines 47-54 (`_registry`), 93-103 (registry-aware config resolution + inline prompt priority) |
| `src/engine/manager.py` | `_build_registry` static method with command injection; registry threading in `_execute` | VERIFIED | Lines 104-122 (`_build_registry`), 139,153 (threading in `_execute`), 297 (in `resume_interrupted`) |
| `tests/test_runner_inline.py` | 5 tests for inline system prompt behavior | VERIFIED | File exists; all 5 tests pass |
| `tests/test_orchestrator.py` | Phase-28 test classes: `TestDynamicSchemaBuilder`, `TestDynamicSystemPromptBuilder`, `TestWebTaskContextRegistry`, `TestOrchestrateWithRegistry`, `TestProjectAgentRouting`, `TestCommandRouting` | VERIFIED | All 6 classes present at lines 263, 290, 322, 426, 507, 555; 14 phase-28 tests all pass |
| `tests/test_agent_config.py` | 4 tests for `inject_commands_as_agents` | VERIFIED | `TestInjectCommandsAsAgents` class at line 277; all 4 tests pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/pipeline/orchestrator.py` | `src/agents/config.py` | `build_agent_enum(registry)` | WIRED | `orchestrator.py:74` — `"enum": build_agent_enum(registry)` inside `build_orchestrator_schema` |
| `src/pipeline/orchestrator.py` | `src/agents/config.py` | `build_agent_descriptions(registry)` | N/A — not used directly | `build_orchestrator_system_prompt` filters registry directly; `build_agent_descriptions` is available but the prompt builder implements its own inline formatting — functionally equivalent |
| `src/engine/manager.py` | `src/agents/config.py` | `get_project_registry(project_path)` | WIRED | `manager.py:114` — `registry = get_project_registry(project_path)` in `_build_registry` |
| `src/engine/manager.py` | `src/pipeline/orchestrator.py` | `orchestrate_pipeline(..., registry=registry)` | WIRED | `manager.py:153` — `await orchestrate_pipeline(ctx, prompt, self._pool, task_id, registry=registry)` |
| `src/engine/context.py` | `src/runner/runner.py` | `stream_claude` with `system_prompt=` kwarg | WIRED | `context.py:110` — `stream_claude(prompt, system_prompt=system_prompt_inline, system_prompt_file=system_prompt_file, ...)` |
| `src/pipeline/orchestrator.py` | `src/runner/runner.py` | `call_orchestrator_claude` with `system_prompt=` kwarg | WIRED | `orchestrator.py:253` — `call_orchestrator_claude(prompt, effective_schema, system_prompt=system_prompt)` |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ORCH-01 | 28-01 | Lo schema dell'orchestrator viene costruito dinamicamente per ogni task (`build_orchestrator_schema(registry)`) | SATISFIED | `build_orchestrator_schema(registry)` public at `orchestrator.py:63`; called per-task at line 326 in `orchestrate_pipeline` |
| CMLD-03 | 28-01 | I comandi possono essere eseguiti come target di routing dall'orchestrator | SATISFIED | `inject_commands_as_agents` at `config.py:196` creates `cmd-*` routing targets; wired into `_build_registry` in manager.py |
| ORCH-02 | 28-02 | Il pipeline accetta un registry come parametro iniettato (non modulo-level constant) | SATISFIED | `orchestrate_pipeline(registry=...)` at `orchestrator.py:306`; `TaskManager._execute` injects it at line 153 |
| ORCH-03 | 28-02 | L'orchestrator può routare verso agenti specifici del progetto | SATISFIED | Registry threading + `WebTaskContext.stream_output` resolves project agents with inline prompts; schema enum includes all registry keys |

No orphaned requirements — all 4 IDs declared in plan frontmatter are accounted for.

### Anti-Patterns Found

None. No TODO/FIXME/placeholder comments, no stub implementations, no empty returns in phase-28 modified files.

### Test Suite Results

| Test File | Scope | Result |
|-----------|-------|--------|
| `tests/test_runner_inline.py` | All 5 tests | 5 passed |
| `tests/test_orchestrator.py` | Phase-28 classes (14 tests) | 14 passed |
| `tests/test_agent_config.py` | `TestInjectCommandsAsAgents` (4 tests) | 4 passed |
| `tests/test_agent_config.py` | Pre-existing tests (`test_execute_config_sections`, `test_resolve_pipeline_order_*`) | 3 FAILED — pre-existing failures; these tests assert `execute.next_agent == "review"` but the registry was updated to `"test"` in phase d7616fb (before phase 28); phase 28 did not touch these tests or the execute agent config |

**Pre-existing failures are not a phase-28 regression.** The execute agent's `next_agent` was set to `"test"` in an earlier phase and the corresponding tests were never updated. Phase 28 commit `7ebcc52` only added the `TestInjectCommandsAsAgents` class to `test_agent_config.py` without touching the pre-existing failing tests.

### Human Verification Required

#### 1. Project Agent End-to-End Routing

**Test:** Create a project with a `.claude/agents/db-migrator.md` file containing a specialist prompt. Submit a task to that project that should trigger DB migration work. Verify the orchestrator routes to `db-migrator` and Claude receives the markdown content as its system prompt (check logs for `stream_output: agent=db-migrator using inline system_prompt`).
**Expected:** Task executes with `db-migrator` agent using markdown file as inline prompt, log line confirms `--system-prompt` flag used instead of `--system-prompt-file`.
**Why human:** Cannot launch Claude CLI subprocess in verification environment.

#### 2. Command Routing in Pipeline

**Test:** Create a project with a `.claude/commands/deploy.md` file. Submit a task that mentions deployment. Verify the orchestrator schema enum includes `cmd-deploy` and the orchestrator can route to it.
**Expected:** Schema enum in orchestrator decision call includes `"cmd-deploy"`. If routed, command file content is used as the system prompt.
**Why human:** Requires real Claude CLI invocation and a project with command files.

### Gaps Summary

No gaps found. All must-have truths are fully verified with substantive implementations and complete wiring through the call chain. The phase goal is achieved: the orchestrator builds its routing schema dynamically per-task from the injected registry, and both project agents and commands are routable targets in the pipeline.

---

_Verified: 2026-03-14T19:00:00Z_
_Verifier: Claude (gsd-verifier)_
