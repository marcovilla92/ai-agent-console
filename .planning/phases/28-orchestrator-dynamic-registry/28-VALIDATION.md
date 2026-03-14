---
phase: 28
slug: orchestrator-dynamic-registry
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 28 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio |
| **Config file** | `pytest.ini` (exists, `asyncio_mode = auto`) |
| **Quick run command** | `python -m pytest tests/test_orchestrator.py tests/test_pipeline_extension.py tests/test_agent_config.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~8 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_orchestrator.py tests/test_pipeline_extension.py tests/test_agent_config.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 8 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 28-01-01 | 01 | 1 | ORCH-01 | unit | `python -m pytest tests/test_runner_inline.py -x` | ❌ W0 | ⬜ pending |
| 28-01-02 | 01 | 1 | ORCH-01, CMLD-03 | unit | `python -m pytest tests/test_orchestrator.py tests/test_pipeline_extension.py -x` | ❌ W0 | ⬜ pending |
| 28-02-01 | 02 | 2 | ORCH-02, ORCH-03 | unit | `python -m pytest tests/test_orchestrator.py -x` | ❌ W0 | ⬜ pending |
| 28-02-02 | 02 | 2 | ORCH-02 | unit | `python -m pytest tests/test_orchestrator.py tests/test_agent_config.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_runner_inline.py` — tests for --system-prompt flag support
- [ ] `tests/test_orchestrator.py::TestDynamicSchema` — schema enum includes project agents
- [ ] `tests/test_orchestrator.py::TestOrchestrateWithRegistry` — pipeline accepts registry param
- [ ] `tests/test_orchestrator.py::TestProjectAgentRouting` — routing to project agent with inline prompt
- [ ] `tests/test_orchestrator.py::TestCommandRouting` — commands as routing targets

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
- [ ] Feedback latency < 8s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
