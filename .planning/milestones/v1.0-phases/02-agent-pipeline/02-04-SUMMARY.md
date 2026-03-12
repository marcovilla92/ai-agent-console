---
phase: 02-agent-pipeline
plan: 04
subsystem: pipeline
tags: [config-driven, dynamic-resolution, agent-registry, pipeline-order]

requires:
  - phase: 02-agent-pipeline
    provides: "AGENT_REGISTRY with next_agent chain, pipeline runner"
provides:
  - "resolve_pipeline_order() function for config-driven pipeline execution"
  - "Dynamic pipeline steps derived from AGENT_REGISTRY next_agent chain"
affects: [04-orchestrator-loop, agent-registry-extensions]

tech-stack:
  added: []
  patterns: [config-driven-pipeline, chain-traversal-with-cycle-guard]

key-files:
  created: []
  modified:
    - src/agents/config.py
    - src/pipeline/runner.py
    - tests/test_agent_config.py
    - tests/test_pipeline.py

key-decisions:
  - "resolve_pipeline_order uses seen-set O(1) cycle detection rather than length-based limit"

patterns-established:
  - "Config-driven pipeline: execution order derived from registry, not hardcoded constants"

requirements-completed: [AGNT-05]

duration: 3min
completed: 2026-03-12
---

# Phase 2 Plan 4: Dynamic Pipeline Order Summary

**Config-driven pipeline execution via resolve_pipeline_order() walking AGENT_REGISTRY next_agent chain**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-12T12:42:56Z
- **Completed:** 2026-03-12T12:45:45Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Added resolve_pipeline_order() to config.py with cycle detection and KeyError handling
- Removed hardcoded PIPELINE_STEPS constant from runner.py
- Pipeline now dynamically resolves execution order from AGENT_REGISTRY
- New test proves adding a 4th agent to registry extends pipeline without code changes

## Task Commits

Each task was committed atomically:

1. **Task 1: Add resolve_pipeline_order() to config.py and test it** - `10e2a1a` (feat, TDD)
2. **Task 2: Replace hardcoded PIPELINE_STEPS in runner.py and update pipeline tests** - `729cc15` (feat)

## Files Created/Modified
- `src/agents/config.py` - Added resolve_pipeline_order() with chain traversal and cycle guard
- `src/pipeline/runner.py` - Removed PIPELINE_STEPS, imports resolve_pipeline_order
- `tests/test_agent_config.py` - 4 new tests for resolve_pipeline_order edge cases
- `tests/test_pipeline.py` - Updated imports, added dynamic agent extension test

## Decisions Made
- Used seen-set for O(1) cycle detection rather than a chain-length limit

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Pipeline is fully config-driven; adding agents requires only AGENT_REGISTRY updates
- All 82 tests pass with zero regressions
- Ready for orchestrator loop (Phase 4) which may add dynamic agent routing

---
*Phase: 02-agent-pipeline*
*Completed: 2026-03-12*

## Self-Check: PASSED
