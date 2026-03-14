---
phase: 22-bug-fixes-foundation
plan: 01
subsystem: pipeline
tags: [claude-cli, system-prompts, orchestrator, agents]

requires:
  - phase: none
    provides: existing agent config registry and runner module
provides:
  - stream_output passes system_prompt_file from agent config to stream_claude
  - call_orchestrator_claude accepts and uses system_prompt_file parameter
  - get_orchestrator_decision wires ORCHESTRATOR_PROMPT_FILE constant
affects: [23-structured-output, 24-context-assembly]

tech-stack:
  added: []
  patterns: [agent-config-lookup-in-stream-output, system-prompt-file-flag-plumbing]

key-files:
  created: [tests/test_system_prompts.py]
  modified: [src/engine/context.py, src/runner/runner.py, src/pipeline/orchestrator.py]

key-decisions:
  - "System prompt lookup lives inside WebTaskContext.stream_output, not in the TaskContext Protocol"
  - "Unknown agent names log warning and fall back to None rather than crashing"

patterns-established:
  - "Agent config lookup: get_agent_config(agent_name) with KeyError fallback for unknown agents"
  - "System prompt plumbing: all CLI-calling functions accept system_prompt_file parameter"

requirements-completed: [FIX-01, FIX-02]

duration: 2min
completed: 2026-03-14
---

# Phase 22 Plan 01: System Prompt Fixes Summary

**Wired agent system_prompt_file into web execution path and orchestrator routing decisions via get_agent_config lookup**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-14T14:36:59Z
- **Completed:** 2026-03-14T14:38:50Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- stream_output now looks up agent config and passes system_prompt_file to stream_claude for every agent call
- Unknown agent names gracefully fall back to None with a warning log (no crash)
- call_orchestrator_claude accepts system_prompt_file and builds --system-prompt-file CLI flag
- get_orchestrator_decision passes ORCHESTRATOR_PROMPT_FILE constant to call_orchestrator_claude
- 5 new unit tests covering all fix scenarios

## Task Commits

Each task was committed atomically:

1. **Task 1: Write tests for system prompt fixes** - `6a1f0a7` (test) - TDD RED phase
2. **Task 2: Wire system prompts into stream_output and call_orchestrator_claude** - `5e9137f` (feat) - TDD GREEN phase

## Files Created/Modified
- `tests/test_system_prompts.py` - 5 tests covering FIX-01 and FIX-02 scenarios
- `src/engine/context.py` - Added get_agent_config import and system prompt lookup in stream_output
- `src/runner/runner.py` - Added system_prompt_file parameter to call_orchestrator_claude
- `src/pipeline/orchestrator.py` - Added ORCHESTRATOR_PROMPT_FILE constant, passed to call_orchestrator_claude

## Decisions Made
- System prompt lookup lives inside WebTaskContext.stream_output, not in the TaskContext Protocol -- keeps the protocol clean
- Unknown agent names log a warning and fall back to None rather than crashing -- defensive fallback

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- System prompts now flow through the web execution path, prerequisite for structured output parsing in phase 23
- Pre-existing test_orchestrator.py::TestLogDecision::test_persists_to_db failure (aiosqlite vs asyncpg mismatch) is unrelated

## Self-Check: PASSED

All files and commits verified.

---
*Phase: 22-bug-fixes-foundation*
*Completed: 2026-03-14*
