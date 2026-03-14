---
phase: 15-project-service-and-api
plan: 02
subsystem: api
tags: [fastapi, jinja2, git-init, project-crud, event-lifecycle]

requires:
  - phase: 15-project-service-and-api
    provides: ProjectService, ProjectEvent enum, emit_event stub, detect_stack
provides:
  - GET /projects endpoint with auto-scan and stack enrichment
  - POST /projects endpoint with template scaffolding and git init
  - DELETE /projects/{id} endpoint with DB-only removal
  - create_project method with template rendering and git initialization
  - emit_event calls at all 6 lifecycle points
affects: [16-spa]

tech-stack:
  added: [jinja2]
  patterns: [template-scaffolding, git-subprocess-with-timeout, tdd-endpoint-testing]

key-files:
  created: []
  modified:
    - src/server/routers/projects.py
    - src/pipeline/project_service.py
    - src/engine/manager.py
    - src/context/assembler.py
    - tests/test_project_service.py

key-decisions:
  - "scaffold_from_template uses Jinja2 Template directly (not Environment) for simplicity"
  - "git init errors swallowed with log.warning -- project creation succeeds even if git fails"
  - "Router routes reordered: GET/POST '' before /{project_id}/ to avoid FastAPI route conflicts"
  - "Endpoint tests use minimal FastAPI app with noop_lifespan to avoid full server bootstrap"

patterns-established:
  - "Template scaffolding: .j2 files rendered, static files copied, EXCLUDE_DIRS honored"
  - "git subprocess pattern: asyncio.create_subprocess_exec with 10s timeout via wait_for"

requirements-completed: [PROJ-01, PROJ-02, PROJ-03]

duration: 4min
completed: 2026-03-14
---

# Phase 15 Plan 02: Project Router Endpoints Summary

**GET/POST/DELETE project endpoints with template scaffolding, git init, and emit_event at all 6 lifecycle points**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-14T00:32:26Z
- **Completed:** 2026-03-14T00:36:26Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Implemented create_project with Jinja2 template scaffolding, async git init, and DB insert
- Added GET /projects, POST /projects, DELETE /projects/{id} endpoints to router
- Wired emit_event at all 6 lifecycle points: project.created/deleted, task.started/completed/failed, phase.suggested
- 30 project service tests passing (14 new tests added)

## Task Commits

Each task was committed atomically:

1. **Task 1: POST /projects with template scaffolding + git init, and DELETE endpoint** - `fb7e248` (feat)
2. **Task 2: Wire emit_event into TaskManager and suggest_next_phase** - `5925719` (feat)

_Note: Task 1 was TDD -- RED/GREEN phases combined in single commit_

## Files Created/Modified
- `src/pipeline/project_service.py` - Added create_project method, scaffold_from_template helper, git_init_project helper
- `src/server/routers/projects.py` - Rewrote with GET/POST/DELETE collection endpoints before per-project routes
- `src/engine/manager.py` - Added emit_event calls at task.started, task.completed, task.failed
- `src/context/assembler.py` - Added emit_event call for phase.suggested in suggest_next_phase
- `tests/test_project_service.py` - Added TestCreateProject (4 tests), TestProjectEndpoints (5 tests), TestLifecycleEvents (5 tests)

## Decisions Made
- scaffold_from_template uses Jinja2 Template directly rather than full Environment -- simpler for our use case
- git init errors are swallowed with log.warning so project creation succeeds even without git
- Router routes reordered so collection endpoints (GET "", POST "") come before parametric routes (/{project_id}/...)
- Endpoint tests create a minimal FastAPI app with noop_lifespan to avoid full server bootstrap complexity

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All Phase 15 API surface complete (projects CRUD + events at all lifecycle points)
- Ready for Phase 16 SPA frontend to consume these endpoints
- 30 project service tests green; pre-existing TUI test failures unchanged

---
*Phase: 15-project-service-and-api*
*Completed: 2026-03-14*
