---
phase: 06-database-and-server-foundation
plan: 01
subsystem: database
tags: [asyncpg, postgresql, repository-pattern, dataclasses, migration]

# Dependency graph
requires: []
provides:
  - PostgreSQL schema with 4 tables (tasks, agent_outputs, agent_usage, orchestrator_decisions)
  - asyncpg repository classes (TaskRepository, AgentOutputRepository, OrchestratorDecisionRepository, UsageRepository)
  - Schema migration function (apply_schema)
  - PostgreSQL dataclasses with datetime fields
affects: [06-02, 07-api-endpoints, 08-websocket]

# Tech tracking
tech-stack:
  added: [asyncpg, fastapi, uvicorn, pydantic-settings, httpx, pytest-asyncio]
  patterns: [asyncpg-pool-repository, RETURNING-id-fetchval, positional-params]

key-files:
  created:
    - src/db/pg_schema.py
    - src/db/pg_repository.py
    - src/db/migrations.py
    - tests/test_pg_repository.py
    - requirements.txt
  modified:
    - tests/conftest.py

key-decisions:
  - "Renamed sessions table to tasks for v2.0 web mental model alignment"
  - "Kept session_id column name in child tables for API compatibility (rename deferred)"
  - "Used TEST_DATABASE_URL env var with n8n user on existing Coolify PostgreSQL container"

patterns-established:
  - "asyncpg repository: Pool in constructor, $1/$2 params, RETURNING id with fetchval()"
  - "pg_pool fixture: create pool, apply schema, yield, truncate in reverse FK order, close"

requirements-completed: [INFR-01]

# Metrics
duration: 5min
completed: 2026-03-12
---

# Phase 6 Plan 01: PostgreSQL Persistence Layer Summary

**asyncpg repository layer with 4 tables (tasks, agent_outputs, agent_usage, orchestrator_decisions), PostgreSQL-native types, and 5 passing integration tests**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-12T18:27:43Z
- **Completed:** 2026-03-12T18:33:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- PostgreSQL schema with SERIAL, TIMESTAMPTZ, DOUBLE PRECISION types replacing SQLite equivalents
- Four asyncpg repository classes mirroring existing aiosqlite pattern with Pool-based operations
- Five integration tests proving data persistence across separate pool.acquire() calls
- Existing 153 v1.0 aiosqlite tests remain untouched and passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Install dependencies and create PostgreSQL schema** - `05d56c4` (feat)
2. **Task 2 RED: Add failing integration tests** - `3ba9ca1` (test)
3. **Task 2 GREEN: Implement asyncpg repository classes** - `a3e0309` (feat)

## Files Created/Modified
- `src/db/pg_schema.py` - PG_SCHEMA_SQL DDL + Task, AgentOutput, AgentUsage, OrchestratorDecisionRecord dataclasses with datetime fields
- `src/db/pg_repository.py` - TaskRepository, AgentOutputRepository, OrchestratorDecisionRepository, UsageRepository using asyncpg Pool
- `src/db/migrations.py` - apply_schema(pool) function for idempotent schema creation
- `tests/test_pg_repository.py` - 5 integration tests covering schema, CRUD, and foreign-key-linked persistence
- `tests/conftest.py` - Added pg_pool fixture alongside existing db_conn fixture
- `requirements.txt` - New file with v1.0 + v2.0 dependencies

## Decisions Made
- Renamed `sessions` table to `tasks` for v2.0 web mental model (per research recommendation)
- Kept `session_id` column name in child tables for now to minimize blast radius; can be renamed in future cleanup
- Connected to existing Coolify-managed PostgreSQL 16 container (n8n user) for test database

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- pytest-asyncio 1.3.0 was installed initially (very old); upgraded to 0.24.0 for proper async fixture support
- Pre-existing missing dependencies (tenacity, textual, aiosqlite) not installed on system Python; installed to verify v1.0 test compatibility (out of scope, not committed)

## User Setup Required

None - no external service configuration required. Test database uses existing Coolify PostgreSQL container.

## Next Phase Readiness
- Repository layer ready for FastAPI server integration (plan 06-02)
- apply_schema can be called from FastAPI lifespan to create tables on startup
- pg_pool fixture available for all future integration tests

## Self-Check: PASSED

All 6 files verified present. All 3 commit hashes verified in git log.

---
*Phase: 06-database-and-server-foundation*
*Completed: 2026-03-12*
