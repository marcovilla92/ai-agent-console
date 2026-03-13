# Phase 12: DB Foundation - Research

**Researched:** 2026-03-13
**Domain:** PostgreSQL schema migration + asyncpg repository pattern
**Confidence:** HIGH

## Summary

Phase 12 is the unconditional prerequisite for all v2.1 work. Its scope is narrow and well-defined: add a `projects` table, add a nullable `project_id` FK column to `tasks`, add a `ProjectRepository` class, and update the test teardown order so FK constraints don't cause failures. Every pattern needed already exists in the codebase — `TaskRepository` is the direct template.

The existing migration system uses idempotent SQL (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`) executed at startup via `apply_schema()`. Phase 12 follows this exact pattern. No migration tooling (Alembic, Flyway) is used or needed. The `pg_pool` fixture in `conftest.py` is the test harness; it needs one change: `DELETE FROM tasks` must come before `DELETE FROM projects` in teardown to respect the FK constraint.

The primary risk is backward compatibility: existing tasks (and their tests) must continue to work with `project_id = NULL`. This is guaranteed by making the column nullable with no DEFAULT, and by marking `project_id` as `Optional[int] = None` in both the `Task` dataclass and `TaskCreate` Pydantic model. Run `pytest tests/ -x` immediately after the migration step — before writing any other code — as the first verification gate.

**Primary recommendation:** Copy the `TaskRepository` pattern verbatim into `ProjectRepository`, add the two SQL blocks to `pg_schema.py`, wire them through `migrations.py`, update conftest teardown, then write the repository tests.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DB-01 | Projects table with id, name, slug, path, description, created_at, last_used_at | `CREATE TABLE IF NOT EXISTS projects` DDL; exact column types documented in spec |
| DB-02 | Tasks table gains nullable project_id FK referencing projects | `ALTER TABLE tasks ADD COLUMN IF NOT EXISTS project_id INTEGER REFERENCES projects(id)` — no DEFAULT, nullable |
| DB-03 | ProjectRepository provides get, list, insert, delete, update_last_used | Direct asyncpg pattern from `TaskRepository`; 5 methods; same pool injection pattern |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncpg | 0.29+ (existing) | All DB operations via Pool | Already in use; no change needed |
| PostgreSQL 16 | 16 (existing) | SERIAL PK, TIMESTAMPTZ, FK constraints | Already deployed on Coolify |
| pytest-asyncio | 0.24 (existing) | Async test execution | Already configured in pytest.ini |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dataclasses (stdlib) | Python 3.12 | Project dataclass | Same pattern as Task dataclass |
| datetime / timezone (stdlib) | Python 3.12 | Timestamp fields | Same as existing Task fields |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw ALTER TABLE IF NOT EXISTS | Alembic migrations | Alembic adds dependency + config overhead; idempotent raw SQL matches existing codebase pattern |
| SERIAL PRIMARY KEY | UUID | SERIAL is used for tasks; consistency wins |

**Installation:**

No new packages required. All dependencies already present in the running Docker container.

## Architecture Patterns

### Recommended Project Structure

No new files/directories beyond the DB layer:

```
src/
├── db/
│   ├── pg_schema.py        # Add: PROJECTS_DDL, ALTER_TASKS_PROJECT_FK, Project dataclass
│   ├── pg_repository.py    # Add: ProjectRepository class
│   └── migrations.py       # Update: call both new SQL blocks in apply_schema()
tests/
├── conftest.py             # Update: teardown order (tasks before projects)
└── test_project_repository.py   # New: ProjectRepository integration tests
```

### Pattern 1: Idempotent DDL via pg_schema.py

**What:** New SQL constants follow existing `PG_SCHEMA_SQL` / `ALTER_TASKS_SQL` pattern — simple string constants, no ORM, no migration framework.
**When to use:** Always for this project. Schema is applied at app startup via `apply_schema()`.

```python
# Source: existing src/db/pg_schema.py pattern
PROJECTS_DDL = """
CREATE TABLE IF NOT EXISTS projects (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    slug          TEXT NOT NULL UNIQUE,
    path          TEXT NOT NULL UNIQUE,
    description   TEXT DEFAULT '',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at  TIMESTAMPTZ
);
"""

ALTER_TASKS_PROJECT_FK = """
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS project_id INTEGER REFERENCES projects(id);
"""
```

### Pattern 2: asyncpg Repository Class

**What:** Repository class takes `asyncpg.Pool` in `__init__`, uses `pool.fetchrow`, `pool.fetch`, `pool.fetchval`, `pool.execute`. No connection management in method bodies — pool handles it.
**When to use:** All DB operations in this project.

```python
# Source: existing src/db/pg_repository.py — TaskRepository pattern
class ProjectRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def insert(self, project: Project) -> int:
        return await self._pool.fetchval(
            "INSERT INTO projects (name, slug, path, description, created_at) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING id",
            project.name, project.slug, project.path,
            project.description, project.created_at,
        )

    async def get(self, project_id: int) -> Optional[Project]:
        row = await self._pool.fetchrow(
            "SELECT id, name, slug, path, description, created_at, last_used_at "
            "FROM projects WHERE id = $1", project_id
        )
        return _row_to_project(row) if row else None

    async def list_all(self) -> list[Project]:
        rows = await self._pool.fetch(
            "SELECT id, name, slug, path, description, created_at, last_used_at "
            "FROM projects ORDER BY last_used_at DESC NULLS LAST, created_at DESC"
        )
        return [_row_to_project(r) for r in rows]

    async def delete(self, project_id: int) -> None:
        await self._pool.execute("DELETE FROM projects WHERE id = $1", project_id)

    async def update_last_used(self, project_id: int) -> None:
        await self._pool.execute(
            "UPDATE projects SET last_used_at = NOW() WHERE id = $1", project_id
        )
```

### Pattern 3: Task dataclass backward-compatible FK

**What:** Add `project_id: Optional[int] = None` as the last field of the `Task` dataclass, after existing optional fields. All existing code that constructs `Task(...)` without `project_id` continues to work.
**When to use:** Any time adding a nullable FK to an existing dataclass.

```python
# Source: existing src/db/pg_schema.py — Task dataclass
@dataclass
class Task:
    name: str
    project_path: str
    created_at: datetime
    id: Optional[int] = None
    status: str = "queued"
    mode: str = "autonomous"
    prompt: str = ""
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    project_id: Optional[int] = None   # NEW — must be last optional field
```

### Pattern 4: conftest.py teardown FK order

**What:** The `pg_pool` fixture teardown deletes in reverse FK dependency order. With `tasks.project_id REFERENCES projects(id)`, tasks must be deleted before projects.
**When to use:** Any time a new FK is added that the test fixture teardown must respect.

```python
# Source: existing tests/conftest.py pg_pool fixture — teardown block
async with pool.acquire() as conn:
    await conn.execute("DELETE FROM orchestrator_decisions")
    await conn.execute("DELETE FROM agent_usage")
    await conn.execute("DELETE FROM agent_outputs")
    await conn.execute("DELETE FROM tasks")          # must precede projects
    await conn.execute("DELETE FROM projects")       # NEW — after tasks
```

### Anti-Patterns to Avoid

- **NOT NULL on project_id:** Never add `NOT NULL` to the `project_id` column. Existing rows in production have no project and must remain valid.
- **DEFAULT value on project_id:** Do not add `DEFAULT 0` or any default. The correct default is NULL (no project). A non-null default would break the semantic "task without project."
- **Forgetting to update TaskRepository.create():** The `INSERT INTO tasks` statement in `TaskRepository.create()` does not need to change — omitted columns default to NULL. Do NOT add `project_id` to the INSERT unless Phase 16 logic requires it.
- **Forgetting to update TaskRepository.get() and list_all():** These SELECT statements should include `project_id` in the column list and map it to the `Task` dataclass, so the field is populated on retrieval.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Idempotent schema migration | Custom migration tracker table | `ADD COLUMN IF NOT EXISTS` (PostgreSQL 9.6+) | Already used in codebase; zero overhead |
| Async DB connection management | Manual acquire/release | asyncpg Pool auto-management | Pool handles connection lifecycle; already proven |
| Slugification | Custom regex | Simple `name.lower().replace(" ", "-")` stub | Slug generation is Phase 15 (ProjectService). Phase 12 only needs the column to exist. |

**Key insight:** Phase 12 delivers the schema and repository only. No service logic, no slug generation, no filesystem scanning — that is Phase 15's job. Keep Phase 12 minimal.

## Common Pitfalls

### Pitfall 1: FK Violation in Test Teardown

**What goes wrong:** `DELETE FROM tasks` succeeds, then `DELETE FROM projects` fails with FK violation if teardown runs in wrong order — but the real failure mode is the reverse: if `DELETE FROM projects` runs before `DELETE FROM tasks`, PostgreSQL raises `ERROR: update or delete on table "projects" violates foreign key constraint`.
**Why it happens:** `tasks.project_id REFERENCES projects(id)` — deleting a referenced project row fails if tasks still point to it.
**How to avoid:** Update the `pg_pool` fixture teardown to delete `tasks` before `projects`. The conftest already has the correct comment "Clean up in reverse FK order" — just add `DELETE FROM projects` after `DELETE FROM tasks`.
**Warning signs:** Tests pass individually but fail in suites; `ForeignKeyViolationError` in pytest output.

### Pitfall 2: project_id Not Returned by SELECT in TaskRepository

**What goes wrong:** `TaskRepository.get()` and `list_all()` SELECT column lists do not include `project_id`. The `Task` dataclass has the field but it is always `None` even for tasks that have a project.
**Why it happens:** The SELECT column list is hardcoded as a string literal; adding a column to the table does not automatically add it to the query.
**How to avoid:** Update the SELECT statement in both `get()` and `list_all()` to include `project_id`. Also update the `Task(...)` constructor call in the mapping block to pass `project_id=row["project_id"]`.
**Warning signs:** Tests for task-project linkage (Phase 16) show `project_id=None` even after explicit assignment.

### Pitfall 3: Migration Order — projects DDL Must Precede tasks ALTER

**What goes wrong:** `ALTER TABLE tasks ADD COLUMN project_id REFERENCES projects(id)` fails with `ERROR: relation "projects" does not exist` if run before the `CREATE TABLE projects` DDL.
**Why it happens:** FK reference target must exist before the FK column is created.
**How to avoid:** In `apply_schema()`, always execute the `projects` DDL before the `ALTER TABLE tasks` FK statement.
**Warning signs:** Application fails to start; error in `apply_schema()` startup log.

### Pitfall 4: Unique Constraints on slug and path

**What goes wrong:** `INSERT INTO projects` with a duplicate `slug` or `path` raises `UniqueViolationError`. Phase 15 (auto-scan) will hit this on repeat `GET /projects` calls.
**Why it happens:** The spec DDL defines `slug TEXT NOT NULL UNIQUE` and `path TEXT NOT NULL UNIQUE`.
**How to avoid:** Phase 12 only needs to add the constraints. Phase 15 handles `ON CONFLICT DO NOTHING`. Document this in the repository method's docstring so Phase 15 knows to use `ON CONFLICT`.
**Warning signs:** 500 errors on `GET /projects` when the same folder is re-scanned.

## Code Examples

Verified patterns from official sources:

### Project Dataclass (from spec)

```python
# Source: docs/project-router-spec.md — Schema Database section
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Project:
    name: str
    slug: str
    path: str
    created_at: datetime
    id: Optional[int] = None
    description: str = ""
    last_used_at: Optional[datetime] = None
```

### apply_schema() updated call order

```python
# Source: existing src/db/migrations.py pattern
from src.db.pg_schema import PG_SCHEMA_SQL, ALTER_TASKS_SQL, PROJECTS_DDL, ALTER_TASKS_PROJECT_FK

async def apply_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(PG_SCHEMA_SQL)          # existing tables
        await conn.execute(ALTER_TASKS_SQL)         # existing task columns
        await conn.execute(PROJECTS_DDL)            # NEW: projects table
        await conn.execute(ALTER_TASKS_PROJECT_FK)  # NEW: tasks.project_id FK
```

### ProjectRepository test pattern (mirrors test_pg_repository.py)

```python
# Source: existing tests/test_pg_repository.py pattern
async def test_project_crud(pg_pool):
    repo = ProjectRepository(pg_pool)
    now = datetime.now(timezone.utc)
    project = Project(name="Test Project", slug="test-project",
                      path="/tmp/test-project", created_at=now)
    project_id = await repo.insert(project)
    assert isinstance(project_id, int)

    fetched = await repo.get(project_id)
    assert fetched is not None
    assert fetched.slug == "test-project"
    assert fetched.last_used_at is None

    await repo.update_last_used(project_id)
    fetched = await repo.get(project_id)
    assert fetched.last_used_at is not None

    all_projects = await repo.list_all()
    assert any(p.id == project_id for p in all_projects)

    await repo.delete(project_id)
    assert await repo.get(project_id) is None
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Alembic for migrations | Idempotent raw SQL via apply_schema() | v2.0 (Phase 6) | Simpler, no migration state table needed for single-dev project |
| aiosqlite (v1.0) | asyncpg + PostgreSQL (v2.0+) | Phase 6 | asyncpg is the standard for this codebase |

**No deprecated patterns in scope for Phase 12.**

## Open Questions

1. **Should TaskRepository.create() accept project_id now or in Phase 16?**
   - What we know: Phase 16 adds `project_id` to `TaskCreate` Pydantic model. Phase 12 only needs the column in the DB.
   - What's unclear: Whether Phase 16 is simpler if TaskRepository already accepts project_id.
   - Recommendation: Add `project_id: Optional[int] = None` parameter to `TaskRepository.create()` now (insert it if not None). This makes the Phase 16 change a one-liner in the router, not a repository change.

2. **Get-or-create pattern for project_id on Task retrieval?**
   - What we know: `TaskRepository.get()` and `list_all()` must select `project_id`. Existing tests do not assert on `project_id`.
   - Recommendation: Add `project_id` to all SELECT statements in TaskRepository. Existing tests will still pass because `project_id=None` matches the new `Optional[int] = None` default.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2 + pytest-asyncio 0.24.0 |
| Config file | `pytest.ini` (rootdir) |
| Quick run command | `python3 -m pytest tests/test_project_repository.py tests/test_pg_repository.py tests/test_task_schema_migration.py -x` |
| Full suite command | `python3 -m pytest tests/ -x` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DB-01 | projects table exists with correct columns | integration | `python3 -m pytest tests/test_project_repository.py::test_projects_table_exists -x` | Wave 0 |
| DB-01 | projects table has correct column types | integration | `python3 -m pytest tests/test_project_repository.py::test_project_crud -x` | Wave 0 |
| DB-02 | tasks.project_id column exists and is nullable | integration | `python3 -m pytest tests/test_project_repository.py::test_tasks_project_id_nullable -x` | Wave 0 |
| DB-02 | existing tasks with NULL project_id still work | integration | `python3 -m pytest tests/test_pg_repository.py tests/test_task_schema_migration.py -x` | exists |
| DB-03 | ProjectRepository.insert returns int id | integration | `python3 -m pytest tests/test_project_repository.py::test_project_crud -x` | Wave 0 |
| DB-03 | ProjectRepository.get returns Project or None | integration | `python3 -m pytest tests/test_project_repository.py::test_project_crud -x` | Wave 0 |
| DB-03 | ProjectRepository.list_all returns list | integration | `python3 -m pytest tests/test_project_repository.py::test_project_crud -x` | Wave 0 |
| DB-03 | ProjectRepository.delete removes record | integration | `python3 -m pytest tests/test_project_repository.py::test_project_crud -x` | Wave 0 |
| DB-03 | ProjectRepository.update_last_used sets timestamp | integration | `python3 -m pytest tests/test_project_repository.py::test_update_last_used -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `python3 -m pytest tests/test_project_repository.py tests/test_pg_repository.py -x`
- **Per wave merge:** `python3 -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_project_repository.py` — covers DB-01, DB-02, DB-03 (does not exist yet; must be created in Wave 0 of this phase)

Existing infrastructure (`conftest.py` `pg_pool` fixture, `pytest.ini`, `pytest-asyncio`) is sufficient — no framework changes needed. The only gap is the new test file.

## Sources

### Primary (HIGH confidence)

- `src/db/pg_schema.py` — exact DDL pattern and dataclass structure in use
- `src/db/pg_repository.py` — exact asyncpg repository pattern in use (TaskRepository)
- `src/db/migrations.py` — exact apply_schema() wiring pattern
- `tests/conftest.py` — pg_pool fixture and teardown pattern
- `tests/test_pg_repository.py` — integration test pattern for repositories
- `docs/project-router-spec.md` — authoritative DDL for projects table (lines 124-139)
- `.planning/research/SUMMARY.md` — verified pitfalls and build order

### Secondary (MEDIUM confidence)

- PostgreSQL docs: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` — idempotent since PostgreSQL 9.6
- asyncpg docs: Pool.fetchval, Pool.fetchrow, Pool.fetch, Pool.execute — confirmed pool-level method signatures match codebase usage

### Tertiary (LOW confidence)

- None for this phase — everything verified against the live codebase.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new libraries; exact codebase patterns verified by reading source files
- Architecture: HIGH — direct copy of TaskRepository pattern; DDL from spec; migrations from existing apply_schema
- Pitfalls: HIGH — FK teardown order and nullable FK are both documented in STATE.md Blockers/Concerns and verified against existing conftest.py

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (stable domain — asyncpg and PostgreSQL patterns do not change rapidly)
