---
phase: 28-orchestrator-dynamic-registry
plan: 01
subsystem: pipeline
tags: [orchestrator, schema, system-prompt, command-injection, runner]

requires:
  - phase: 27-commands-settings-loaders
    provides: CommandInfo dataclass and discover_project_commands
  - phase: 26-project-agent-loader
    provides: AgentConfig extended fields (system_prompt_inline, source, file_path)
provides:
  - build_orchestrator_schema(registry) public function for dynamic schema generation
  - build_orchestrator_system_prompt(registry) for dynamic orchestrator prompts
  - inject_commands_as_agents() for converting commands to routing targets
  - system_prompt kwarg on stream_claude and call_orchestrator_claude
affects: [28-02-wiring, pipeline, orchestrator]

tech-stack:
  added: []
  patterns: [inline-system-prompt-priority, registry-parameterized-builders]

key-files:
  created:
    - tests/test_runner_inline.py
  modified:
    - src/runner/runner.py
    - src/pipeline/orchestrator.py
    - src/agents/config.py
    - tests/test_orchestrator.py
    - tests/test_agent_config.py

key-decisions:
  - "Inline system_prompt takes priority over system_prompt_file when both provided"
  - "build_orchestrator_system_prompt uses .upper() for agent names consistent with existing build_agent_descriptions"
  - "inject_commands_as_agents reads command file content into system_prompt_inline"

patterns-established:
  - "Registry-parameterized builders: public functions accept optional registry, default to DEFAULT_REGISTRY"
  - "Inline prompt priority: --system-prompt flag preferred over --system-prompt-file"

requirements-completed: [ORCH-01, CMLD-03]

duration: 4min
completed: 2026-03-14
---

# Phase 28 Plan 01: Dynamic Registry Foundation Summary

**Public schema builder, dynamic system prompt builder, command-to-agent injection, and inline system prompt support for Claude CLI runner**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-14T18:00:55Z
- **Completed:** 2026-03-14T18:05:17Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- stream_claude and call_orchestrator_claude now accept system_prompt kwarg with --system-prompt CLI flag
- build_orchestrator_schema is public, accepts any registry, produces correct JSON schema enum
- build_orchestrator_system_prompt dynamically appends project/command agent descriptions to base prompt
- inject_commands_as_agents converts CommandInfo objects into cmd-prefixed AgentConfig routing targets

## Task Commits

Each task was committed atomically:

1. **Task 1: Add inline system prompt support to runner functions** - `4c2f204` (feat)
2. **Task 2: Public schema builder, dynamic system prompt builder, and command injection helper** - `7ebcc52` (feat)

## Files Created/Modified
- `src/runner/runner.py` - Added system_prompt kwarg to stream_claude and call_orchestrator_claude
- `src/pipeline/orchestrator.py` - Renamed _build_orchestrator_schema to public, added build_orchestrator_system_prompt
- `src/agents/config.py` - Added inject_commands_as_agents helper function
- `tests/test_runner_inline.py` - 5 tests for inline system prompt in both runner functions
- `tests/test_orchestrator.py` - 4 tests for dynamic schema and system prompt builders
- `tests/test_agent_config.py` - 4 tests for inject_commands_as_agents

## Decisions Made
- Inline system_prompt takes priority over system_prompt_file when both provided
- build_orchestrator_system_prompt uses .upper() for agent names consistent with existing build_agent_descriptions
- inject_commands_as_agents reads command file content into system_prompt_inline for routing

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All building blocks ready for Plan 02 to wire registry through the pipeline call chain
- build_orchestrator_schema(registry) replaces private _build_orchestrator_schema
- ORCHESTRATOR_SCHEMA backward-compat constant preserved

---
*Phase: 28-orchestrator-dynamic-registry*
*Completed: 2026-03-14*
