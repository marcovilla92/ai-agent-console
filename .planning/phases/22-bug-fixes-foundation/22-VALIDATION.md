---
phase: 22
slug: bug-fixes-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 22 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio |
| **Config file** | `pytest.ini` |
| **Quick run command** | `cd /home/ubuntu/projects/ai-agent-console && python -m pytest tests/test_orchestrator.py tests/test_handoff.py -x -q` |
| **Full suite command** | `cd /home/ubuntu/projects/ai-agent-console && python -m pytest tests/ -x -q --ignore=tests/test_pg_repository.py --ignore=tests/test_task_manager.py --ignore=tests/test_server.py --ignore=tests/test_websocket.py` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_orchestrator.py tests/test_handoff.py -x -q`
- **After every plan wave:** Run full suite command
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 22-01-01 | 01 | 1 | FIX-01 | unit (mock) | `python -m pytest tests/test_orchestrator.py -x -k "system_prompt"` | ❌ W0 | ⬜ pending |
| 22-01-02 | 01 | 1 | FIX-02 | unit (mock) | `python -m pytest tests/test_orchestrator.py -x -k "orchestrator_prompt"` | ❌ W0 | ⬜ pending |
| 22-02-01 | 02 | 1 | CTX-05 | unit | `python -m pytest tests/test_orchestrator.py -x -k "bounded"` | ❌ W0 | ⬜ pending |
| 22-02-02 | 02 | 1 | CTX-06 | unit | `python -m pytest tests/test_orchestrator.py -x -k "pinned"` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_orchestrator.py` — add tests for bounded handoff windowing (CTX-05), pinned plan handoff (CTX-06), orchestrator system prompt path (FIX-02)
- [ ] `tests/test_orchestrator.py` or new file — add test for stream_output passing system_prompt_file (FIX-01)
- [ ] No new framework install needed — pytest + pytest-asyncio already configured

*Existing infrastructure covers framework requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Agent output follows formatting sections | FIX-01 | Requires running actual Claude CLI with system prompt | Create a task, verify output has proper section headers |
| Orchestrator decisions reference role | FIX-02 | Requires inspecting actual LLM decision reasoning | Create a task, check orchestrator decision log for role-aware language |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
