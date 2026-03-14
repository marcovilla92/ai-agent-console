---
phase: 26
slug: agent-loader-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 26 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ with pytest-asyncio |
| **Config file** | `pytest.ini` (exists, `asyncio_mode = auto`) |
| **Quick run command** | `python -m pytest tests/test_agent_loader.py tests/test_agent_config.py -x` |
| **Full suite command** | `python -m pytest tests/ -x` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_agent_loader.py tests/test_agent_config.py -x`
- **After every plan wave:** Run `python -m pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 26-01-01 | 01 | 1 | AGLD-01 | unit | `python -m pytest tests/test_agent_loader.py::test_discover_agents_from_directory -x` | ❌ W0 | ⬜ pending |
| 26-01-02 | 01 | 1 | AGLD-01 | unit | `python -m pytest tests/test_agent_loader.py::test_discover_no_agents_dir -x` | ❌ W0 | ⬜ pending |
| 26-01-03 | 01 | 1 | AGLD-02 | unit | `python -m pytest tests/test_agent_loader.py::test_parse_with_frontmatter -x` | ❌ W0 | ⬜ pending |
| 26-01-04 | 01 | 1 | AGLD-02 | unit | `python -m pytest tests/test_agent_loader.py::test_parse_without_frontmatter -x` | ❌ W0 | ⬜ pending |
| 26-01-05 | 01 | 1 | AGLD-02 | unit | `python -m pytest tests/test_agent_loader.py::test_skip_broken_files -x` | ❌ W0 | ⬜ pending |
| 26-02-01 | 02 | 1 | AGLD-03 | unit | `python -m pytest tests/test_agent_config.py::test_project_registry_is_isolated -x` | ❌ W0 | ⬜ pending |
| 26-02-02 | 02 | 1 | AGLD-03 | unit | `python -m pytest tests/test_agent_config.py::test_default_registry_unchanged -x` | ❌ W0 | ⬜ pending |
| 26-02-03 | 02 | 1 | AGLD-04 | unit | `python -m pytest tests/test_agent_config.py::test_core_agents_protected -x` | ❌ W0 | ⬜ pending |
| 26-02-04 | 02 | 1 | AGLD-04 | unit | `python -m pytest tests/test_agent_config.py::test_core_override_logs_warning -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_agent_loader.py` — new file covering AGLD-01, AGLD-02
- [ ] `tests/test_agent_config.py` — add tests for AGLD-03, AGLD-04
- [ ] `python-frontmatter==1.1.0` added to `requirements.txt`

*Existing test infrastructure (pytest, conftest) covers all phase requirements.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
