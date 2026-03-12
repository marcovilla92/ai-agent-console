---
phase: 04
slug: orchestrator-intelligence
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x with pytest-asyncio |
| **Config file** | pyproject.toml |
| **Quick run command** | `pytest tests/test_orchestrator*.py -x -v` |
| **Full suite command** | `pytest tests/ -x -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_orchestrator*.py -x -v`
- **After every plan wave:** Run `pytest tests/ -x -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | ORCH-01 | unit | `pytest tests/test_orchestrator.py -x -v` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | ORCH-01 | unit | `pytest tests/test_orchestrator.py -x -v` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | ORCH-02 | unit | `pytest tests/test_orchestrator.py -x -v` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 1 | ORCH-03 | unit | `pytest tests/test_orchestrator.py -x -v` | ❌ W0 | ⬜ pending |
| 04-03-01 | 03 | 2 | ORCH-04 | unit | `pytest tests/test_orchestrator.py -x -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_orchestrator.py` — stubs for ORCH-01, ORCH-02, ORCH-03, ORCH-04
- [ ] `tests/conftest.py` — shared fixtures (already exists from Phase 1)

*Existing pytest infrastructure covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| User sees confirmation modal before re-routing | ORCH-02 | Textual ModalScreen requires live terminal | Launch app, trigger BACK TO PLAN review, verify modal appears with Enter/Escape |
| Orchestrator reasoning visible in status bar | ORCH-04 | Visual text rendering in TUI | Launch app, run full cycle, check status bar shows reasoning |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
