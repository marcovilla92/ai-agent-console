---
phase: 5
slug: polish
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ with pytest-asyncio 0.23+ |
| **Config file** | pyproject.toml |
| **Quick run command** | `python -m pytest tests/ -x --timeout=10` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x --timeout=10`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | TUI-05 | unit | `python -m pytest tests/test_panel_resize.py -x` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | TUI-05 | unit | `python -m pytest tests/test_panel_resize.py -x` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 1 | INFR-06 | unit | `python -m pytest tests/test_autocommit.py -x` | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 1 | INFR-06 | unit | `python -m pytest tests/test_autocommit.py -x` | ❌ W0 | ⬜ pending |
| 05-03-01 | 03 | 1 | INFR-07 | unit | `python -m pytest tests/test_usage_tracking.py -x` | ❌ W0 | ⬜ pending |
| 05-03-02 | 03 | 1 | INFR-07 | unit | `python -m pytest tests/test_usage_tracking.py -x` | ❌ W0 | ⬜ pending |
| 05-04-01 | 04 | 2 | INFR-08 | unit | `python -m pytest tests/test_session_browser.py -x` | ❌ W0 | ⬜ pending |
| 05-04-02 | 04 | 2 | INFR-08 | unit | `python -m pytest tests/test_session_browser.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_panel_resize.py` — stubs for TUI-05 resize and collapse
- [ ] `tests/test_autocommit.py` — stubs for INFR-06 git auto-commit
- [ ] `tests/test_usage_tracking.py` — stubs for INFR-07 token/cost parsing and display
- [ ] `tests/test_session_browser.py` — stubs for INFR-08 session list and resume

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual panel resize feedback | TUI-05 | Requires visual confirmation of grid changes | Resize panel with keyboard, verify visual change |
| Session resume UI flow | INFR-08 | End-to-end flow with modal interaction | Open session browser, select session, verify panels load |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
