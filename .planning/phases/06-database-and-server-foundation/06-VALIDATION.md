---
phase: 6
slug: database-and-server-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.23.x |
| **Config file** | `pyproject.toml` (existing `[tool.pytest.asyncio]` section expected) |
| **Quick run command** | `python -m pytest tests/test_pg_repository.py tests/test_server.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_pg_repository.py tests/test_server.py tests/test_protocol.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | INFR-01a | integration | `python -m pytest tests/test_pg_repository.py::test_schema_creates_tables -x` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | INFR-01b | integration | `python -m pytest tests/test_pg_repository.py::test_task_crud -x` | ❌ W0 | ⬜ pending |
| 06-01-03 | 01 | 1 | INFR-01c | integration | `python -m pytest tests/test_pg_repository.py::test_agent_output_persistence -x` | ❌ W0 | ⬜ pending |
| 06-01-04 | 01 | 1 | INFR-01d | integration | `python -m pytest tests/test_pg_repository.py::test_usage_persistence -x` | ❌ W0 | ⬜ pending |
| 06-01-05 | 01 | 1 | INFR-01e | integration | `python -m pytest tests/test_pg_repository.py::test_decision_persistence -x` | ❌ W0 | ⬜ pending |
| 06-02-01 | 02 | 1 | SC-01 | integration | `python -m pytest tests/test_server.py::test_health_endpoint -x` | ❌ W0 | ⬜ pending |
| 06-02-02 | 02 | 1 | SC-02 | integration | `python -m pytest tests/test_server.py::test_health_db_check -x` | ❌ W0 | ⬜ pending |
| 06-02-03 | 02 | 1 | SC-03 | integration | `python -m pytest tests/test_server.py::test_lifespan_pool -x` | ❌ W0 | ⬜ pending |
| 06-02-04 | 02 | 1 | SC-04 | unit | `python -m pytest tests/test_protocol.py::test_taskcontext_protocol -x` | ❌ W0 | ⬜ pending |
| 06-02-05 | 02 | 1 | SC-05 | unit | `python -m pytest tests/test_orchestrator.py::test_orchestrator_uses_protocol -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_pg_repository.py` — stubs for INFR-01a through INFR-01e
- [ ] `tests/test_server.py` — stubs for SC-01, SC-02, SC-03
- [ ] `tests/test_protocol.py` — stubs for SC-04, SC-05
- [ ] `tests/conftest.py` update — add `pg_pool` fixture (test database or mock pool)
- [ ] Framework install: `pip install fastapi uvicorn asyncpg pydantic-settings httpx pytest-asyncio`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| PostgreSQL data survives server restart | INFR-01 | Requires actual process restart | 1. Insert data via API 2. Stop/start server 3. Query data exists |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
