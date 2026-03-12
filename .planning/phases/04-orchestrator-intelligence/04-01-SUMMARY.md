---
phase: 04-orchestrator-intelligence
plan: 01
subsystem: pipeline
tags: [orchestrator, claude-cli, json-schema, state-machine, sqlite]

# Dependency graph
requires:
  - phase: 02-agent-pipeline
    provides: "AgentResult, build_handoff, stream_claude, AGENT_REGISTRY"
  - phase: 03-tui-shell
    provides: "stream_agent_to_panel, StatusBar, OutputPanel, AGENT_PANEL_MAP"
provides:
  - "OrchestratorState dataclass with iteration tracking and halted/approved flags"
  - "OrchestratorDecision dataclass for routing decisions"
  - "get_orchestrator_decision with JSON parsing and text fallback"
  - "orchestrate_pipeline main loop with re-routing and iteration limits"
  - "call_orchestrator_claude non-streaming CLI call with --json-schema"
  - "OrchestratorDecisionRepository for DB persistence"
  - "orchestrator_decisions DB table"
affects: [04-orchestrator-intelligence, 05-polish]

# Tech tracking
tech-stack:
  added: []
  patterns: [orchestrator-loop, json-schema-structured-output, text-fallback-parsing, stub-modal-functions]

key-files:
  created:
    - src/pipeline/orchestrator.py
    - src/agents/prompts/orchestrator_system.txt
    - tests/test_orchestrator.py
  modified:
    - src/db/schema.py
    - src/db/repository.py
    - src/runner/runner.py
    - tests/conftest.py

key-decisions:
  - "Dedicated call_orchestrator_claude function (non-streaming) instead of extending collect_claude, to avoid breaking existing streaming path"
  - "Text fallback defaults to 'review' when no clear decision keyword found, as safest forward progression"
  - "Stub modal functions (_stub_reroute_confirmation, _stub_halt_dialog) return True/'continue' for Plan 02 to replace"

patterns-established:
  - "Non-streaming Claude CLI call with --json-schema for structured JSON responses"
  - "JSON parse with text fallback for resilience against LLM output variance"
  - "Orchestrator prompt truncation (500 char max per section) to prevent context bloat"

requirements-completed: [ORCH-01, ORCH-03, ORCH-04]

# Metrics
duration: 5min
completed: 2026-03-12
---

# Phase 4 Plan 1: Orchestrator Core Summary

**AI-driven orchestrator with OrchestratorState, Claude CLI JSON routing via --json-schema, iteration limits, DB decision logging, and orchestration loop with stub modals**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-12T14:06:09Z
- **Completed:** 2026-03-12T14:11:16Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- OrchestratorState and OrchestratorDecision dataclasses with mutable iteration tracking
- call_orchestrator_claude non-streaming subprocess call with --json-schema for guaranteed structure
- get_orchestrator_decision with JSON parsing (handles Claude CLI result wrapper) and text fallback
- orchestrate_pipeline main loop: streams agents, calls routing, updates status bar, logs to DB, handles re-routing with iteration limits
- orchestrator_decisions DB table with OrchestratorDecisionRepository
- 17 unit tests covering all orchestrator behaviors

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests** - `41c6bd7` (test)
2. **Task 1 (GREEN): Implementation** - `1c403b1` (feat)
3. **Task 2: Full suite regression check** - no code changes, all 109 tests pass

## Files Created/Modified
- `src/pipeline/orchestrator.py` - Core orchestrator: state, decisions, prompt building, parsing, loop
- `src/agents/prompts/orchestrator_system.txt` - Routing rules system prompt
- `src/db/schema.py` - OrchestratorDecisionRecord dataclass + SQL table
- `src/db/repository.py` - OrchestratorDecisionRepository (create, get_by_session)
- `src/runner/runner.py` - call_orchestrator_claude non-streaming CLI function
- `tests/test_orchestrator.py` - 17 tests for orchestrator behaviors
- `tests/conftest.py` - Added orchestrator_decisions table to in-memory DB fixture

## Decisions Made
- Used dedicated `call_orchestrator_claude` function (non-streaming via proc.communicate) instead of extending existing `collect_claude` which uses stream-json parsing
- Text fallback parser defaults to "review" for unknown text (safest forward progression)
- Stub modal functions return True/"continue" as placeholders for Plan 02's real Textual modals
- Re-routing only triggers when current_agent is "review" (prevents false re-route on forward progression)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Orchestrator core ready for Plan 02 to wire real Textual modal dialogs (RerouteConfirmDialog, HaltDialog)
- Plan 02 needs to replace _stub_reroute_confirmation and _stub_halt_dialog with real ModalScreen implementations
- Plan 03 wires orchestrate_pipeline into TUI send_prompt action

---
*Phase: 04-orchestrator-intelligence*
*Completed: 2026-03-12*
