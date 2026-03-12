---
phase: 9
slug: approval-gates
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | pyproject.toml / pytest section |
| **Quick run command** | `cd /home/ubuntu/projects/ai-agent-console && python -m pytest tests/test_task_manager.py tests/test_task_endpoints.py -x -q` |
| **Full suite command** | `cd /home/ubuntu/projects/ai-agent-console && python -m pytest tests/ -x -q` |
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
| 09-01-01 | 01 | 1 | TASK-04a | unit | `python -m pytest tests/test_task_manager.py::test_supervised_pauses_at_reroute -x` | ❌ W0 | ⬜ pending |
| 09-01-02 | 01 | 1 | TASK-04b | integration | `python -m pytest tests/test_task_endpoints.py::test_approve_resumes_task -x` | ❌ W0 | ⬜ pending |
| 09-01-03 | 01 | 1 | TASK-04c | integration | `python -m pytest tests/test_task_endpoints.py::test_reject_stops_task -x` | ❌ W0 | ⬜ pending |
| 09-01-04 | 01 | 1 | TASK-04d | unit | `python -m pytest tests/test_task_manager.py::test_approval_includes_context -x` | ❌ W0 | ⬜ pending |
| 09-01-05 | 01 | 1 | TASK-04e | unit | `python -m pytest tests/test_task_manager.py::test_autonomous_no_pause -x` | ❌ W0 | ⬜ pending |
| 09-01-06 | 01 | 1 | TASK-04f | unit | `python -m pytest tests/test_task_manager.py::test_cancel_while_awaiting -x` | ❌ W0 | ⬜ pending |
| 09-01-07 | 01 | 1 | TASK-04g | integration | `python -m pytest tests/test_task_endpoints.py::test_approve_not_awaiting -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_task_manager.py` — add approval gate unit tests (supervised pause, autonomous skip, cancel while awaiting, approval context)
- [ ] `tests/test_task_endpoints.py` — add approval REST endpoint integration tests (approve, reject, not-awaiting error)
- [ ] No new framework install needed — pytest + pytest-asyncio already configured

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| WebSocket approval_required event renders in browser | TASK-04a | Requires live WS client | 1. Start server 2. Connect WS 3. Create supervised task 4. Verify approval_required event received |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
