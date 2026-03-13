---
phase: 13
slug: template-system
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-13
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `python -m pytest tests/test_template_router.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_template_router.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 1 | TMPL-01, TMPL-02 | integration | `pytest tests/test_template_router.py -x` | ❌ W0 | ⬜ pending |
| 13-01-02 | 01 | 1 | TMPL-03, TMPL-04 | unit | `pytest tests/test_template_router.py::test_list_templates -x` | ❌ W0 | ⬜ pending |
| 13-02-01 | 02 | 1 | TMPL-05, TMPL-06, TMPL-07 | unit | `pytest tests/test_template_router.py::test_custom_crud -x` | ❌ W0 | ⬜ pending |
| 13-02-02 | 02 | 1 | TMPL-08 | unit | `pytest tests/test_template_router.py::test_builtin_protection -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_template_router.py` — template API endpoint tests
- [ ] Template fixtures using tmp_path for isolation

*Existing pytest infrastructure covers all phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Template file content quality | TMPL-02 | Prose/config authoring | Review CLAUDE.md.j2 and .claude/ files in each template |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
