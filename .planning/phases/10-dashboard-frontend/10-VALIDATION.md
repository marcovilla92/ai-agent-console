---
phase: 10
slug: dashboard-frontend
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ with pytest-asyncio 0.23+ |
| **Config file** | pyproject.toml (minimal) |
| **Quick run command** | `python -m pytest tests/test_views.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_views.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | DASH-01 | integration | `python -m pytest tests/test_views.py::test_task_list_page -x` | ❌ W0 | ⬜ pending |
| 10-01-02 | 01 | 1 | DASH-03 | integration | `python -m pytest tests/test_views.py::test_create_form_present -x` | ❌ W0 | ⬜ pending |
| 10-01-03 | 01 | 1 | DASH-04 | integration | `python -m pytest tests/test_views.py::test_base_template_includes -x` | ❌ W0 | ⬜ pending |
| 10-02-01 | 02 | 1 | DASH-02 | integration | `python -m pytest tests/test_views.py::test_task_detail_page -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_views.py` — stubs for DASH-01, DASH-02, DASH-03, DASH-04
- [ ] `src/templates/` directory — must exist before templates can render
- [ ] `src/server/routers/views.py` — new router for HTML pages

*Existing test infrastructure (pytest, conftest.py) covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| WebSocket live streaming renders in browser | DASH-02 | Requires real browser + WS connection | Open task detail, start task, verify log appears in real-time |
| Responsive layout on mobile viewport | DASH-04 | CSS responsiveness needs visual check | Open dashboard on mobile device or browser dev tools at 375px width |
| Approval UI buttons trigger correct action | DASH-02 | Requires full WS + REST flow | Start supervised task, wait for approval prompt, click approve/reject |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
