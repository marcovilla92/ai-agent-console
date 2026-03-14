---
phase: 15-project-service-and-api
plan: 01
subsystem: api
tags: [asyncpg, events, stack-detection, project-service]

requires:
  - phase: 12-project-schema
    provides: ProjectRepository CRUD and Project dataclass
provides:
  - ProjectEvent enum with 6 lifecycle events
  - emit_event async no-op stub
  - detect_stack() reusable function extracted from assembler
  - ProjectRepository.upsert_by_path with ON CONFLICT DO NOTHING
  - ProjectService with list_projects and delete_project
affects: [15-02-project-router, 16-spa]

tech-stack:
  added: []
  patterns: [event-stub-pattern, workspace-auto-registration, upsert-idempotent]

key-files:
  created:
    - src/pipeline/events.py
    - src/pipeline/project_service.py
    - tests/test_project_service.py
  modified:
    - src/context/assembler.py
    - src/db/pg_repository.py

key-decisions:
  - "ProjectService filters list_all by workspace_root prefix to avoid cross-contamination"
  - "detect_stack extracted as standalone function, assembler refactored to call it"
  - "workspace_root override param in ProjectService.__init__ for testability"

patterns-established:
  - "Event stub: async no-op with DEBUG log, ready for future WebSocket/webhook wiring"
  - "Auto-registration: scan filesystem + upsert_by_path for idempotent project discovery"

requirements-completed: [PROJ-04, PROJ-05, EVT-01]

duration: 4min
completed: 2026-03-14
---

# Phase 15 Plan 01: Project Service Summary

**ProjectEvent enum + emit_event stub, detect_stack extraction, upsert_by_path, and ProjectService with auto-registration and delete**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-14T00:06:26Z
- **Completed:** 2026-03-14T00:10:26Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Created event system stub with 6 lifecycle events and async emit_event no-op
- Extracted detect_stack() as reusable function from assembler.py (refactored existing code)
- Added upsert_by_path to ProjectRepository with ON CONFLICT DO NOTHING for safe auto-registration
- Built ProjectService.list_projects() that scans workspace, auto-registers folders, enriches with stack
- Built ProjectService.delete_project() that removes DB record only, emits event

## Task Commits

Each task was committed atomically:

1. **Task 1: Events stub, detect_stack, upsert_by_path** - `26c55f3` (feat)
2. **Task 2: ProjectService with list and delete** - `84d4fad` (feat)

_Note: TDD tasks -- RED/GREEN phases combined in single commits_

## Files Created/Modified
- `src/pipeline/events.py` - ProjectEvent enum (6 values) + emit_event async no-op stub
- `src/pipeline/project_service.py` - ProjectService class with list_projects and delete_project
- `src/context/assembler.py` - Extracted detect_stack() as standalone function
- `src/db/pg_repository.py` - Added upsert_by_path method to ProjectRepository
- `tests/test_project_service.py` - 16 tests covering events, detect_stack, upsert, list, delete

## Decisions Made
- ProjectService filters list_all results by workspace_root prefix to avoid returning projects from other workspaces during testing
- detect_stack extracted as standalone function; assembler.py refactored to call it instead of inline logic
- workspace_root override parameter in ProjectService.__init__ enables test isolation with tmp_path

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- ProjectService ready for router endpoints in Plan 02
- emit_event stub in place for future WebSocket/webhook wiring
- All 16 tests green; existing suite unaffected (pre-existing failures in TUI tests unchanged)

---
*Phase: 15-project-service-and-api*
*Completed: 2026-03-14*
