---
phase: 12-db-foundation
plan: 01
subsystem: database
tags: [postgresql, asyncpg, dataclass, schema, migration, repository]

# Dependency graph
requires: []
provides:
  - "projects table with 7 columns (id, name, slug, path, description, created_at, last_used_at)"
  - "Project dataclass in pg_schema.py"
  - "Task.project_id nullable FK field"
  - "ProjectRepository with insert/get/list_all/delete/update_last_used"
  - "Migration wiring for PROJECTS_DDL and ALTER_TASKS_PROJECT_FK"
affects: [13-project-templates, 14-context-assembly, 15-project-service, 16-task-integration, 17-spa]

# Tech tracking
tech-stack:
  added: []
  patterns: [nullable FK for backward compatibility, TDD red-green for DB layer]

key-files:
  created:
    - tests/test_project_repository.py
  modified:
    - src/db/pg_schema.py
    - src/db/pg_repository.py
    - src/db/migrations.py
    - tests/conftest.py

key-decisions:
  - "project_id FK is nullable on tasks -- existing tasks with NULL project_id work unchanged"
  - "ProjectRepository follows same pool-based pattern as TaskRepository"

patterns-established:
  - "Nullable FK pattern: new FK columns default NULL for backward compatibility"
  - "Conftest teardown order: child tables before parent tables (tasks before projects)"

requirements-completed: [DB-01, DB-02, DB-03]

# Metrics
duration: 6min
completed: 2026-03-13
---

# Phase 12 Plan 01: DB Foundation Summary

**Projects table with CRUD repository, nullable task FK, and 6 integration tests using asyncpg**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-13T18:33:48Z
- **Completed:** 2026-03-13T18:39:26Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Projects table created with 7 columns (id, name, slug, path, description, created_at, last_used_at) with UNIQUE constraints on name, slug, path
- Nullable project_id FK on tasks table -- existing tasks unaffected
- ProjectRepository with 5 CRUD methods (insert, get, list_all, delete, update_last_used)
- 6 new integration tests all passing; 5 existing pg_repository tests unchanged

## Task Commits

Each task was committed atomically:

1. **Task 1: Schema DDL, dataclasses, migration wiring, and conftest teardown**
   - `08dbe45` (test: failing tests for schema)
   - `5d50ca4` (feat: projects table, Project dataclass, task project_id FK)
2. **Task 2: ProjectRepository CRUD and integration tests**
   - `dd83a61` (test: failing CRUD tests for ProjectRepository)
   - `70acdde` (feat: implement ProjectRepository with 5 CRUD methods)

_Note: TDD tasks have RED and GREEN commits._

## Files Created/Modified
- `src/db/pg_schema.py` - Added PROJECTS_DDL, ALTER_TASKS_PROJECT_FK, Project dataclass, Task.project_id field
- `src/db/pg_repository.py` - Added ProjectRepository class, updated TaskRepository.get/list_all for project_id
- `src/db/migrations.py` - Added PROJECTS_DDL and ALTER_TASKS_PROJECT_FK to apply_schema()
- `tests/conftest.py` - Added DELETE FROM projects in teardown (after tasks)
- `tests/test_project_repository.py` - 6 integration tests (3 schema + 3 CRUD)

## Decisions Made
- project_id FK is nullable on tasks -- backward compatible with existing data
- ProjectRepository follows identical pool-based pattern as TaskRepository for consistency

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Projects table and repository ready for Phase 13 (project templates) and Phase 14 (context assembly)
- Both phases can start in parallel since they only depend on Phase 12

---
*Phase: 12-db-foundation*
*Completed: 2026-03-13*
