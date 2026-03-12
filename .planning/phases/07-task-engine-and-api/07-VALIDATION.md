---
phase: 7
slug: task-engine-and-api
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ with pytest-asyncio 0.23+ |
| **Config file** | pyproject.toml `[project.optional-dependencies] dev` |
| **Quick run command** | `python -m pytest tests/test_task_manager.py tests/test_task_endpoints.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_task_manager.py tests/test_task_endpoints.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | TASK-01 | unit | `python -m pytest tests/test_task_manager.py::test_cancel_task -x` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | TASK-02 | unit | `python -m pytest tests/test_task_manager.py::test_semaphore_concurrency -x` | ❌ W0 | ⬜ pending |
| 07-01-03 | 01 | 1 | TASK-03 | unit | `python -m pytest tests/test_task_manager.py::test_mode_selection -x` | ❌ W0 | ⬜ pending |
| 07-02-01 | 02 | 1 | INFR-02 | integration | `python -m pytest tests/test_task_endpoints.py::test_auth_required -x` | ❌ W0 | ⬜ pending |
| 07-02-02 | 02 | 1 | TASK-01 | integration | `python -m pytest tests/test_task_endpoints.py::test_cancel_endpoint -x` | ❌ W0 | ⬜ pending |
| 07-02-03 | 02 | 1 | TASK-02 | integration | `python -m pytest tests/test_task_endpoints.py::test_create_and_list -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_task_manager.py` — stubs for TASK-01, TASK-02, TASK-03 (unit tests with mocked orchestrator)
- [ ] `tests/test_task_endpoints.py` — stubs for INFR-02, TASK-01 cancel endpoint, TASK-02 create/list (integration tests with ASGI transport)
- [ ] Schema migration test for new columns (status, mode, prompt)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Claude CLI subprocess actually terminates | TASK-01 | Requires real subprocess spawn | Start a task, cancel it, verify no orphan process via `ps aux` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
