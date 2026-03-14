---
phase: 23
slug: core-output
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 23 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio |
| **Config file** | `pytest.ini` |
| **Quick run command** | `cd /home/ubuntu/projects/ai-agent-console && python -m pytest tests/test_file_writer.py tests/test_reroute.py tests/test_section_filter.py -x -q` |
| **Full suite command** | `cd /home/ubuntu/projects/ai-agent-console && python -m pytest tests/ -x -q --ignore=tests/test_pg_repository.py --ignore=tests/test_task_manager.py --ignore=tests/test_server.py --ignore=tests/test_websocket.py` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run quick run command
- **After every plan wave:** Run full suite command
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 23-01-01 | 01 | 1 | FWRT-01 | unit | `python -m pytest tests/test_file_writer.py -x -k "parse_code_blocks"` | ❌ W0 | ⬜ pending |
| 23-01-02 | 01 | 1 | FWRT-02 | unit | `python -m pytest tests/test_file_writer.py -x -k "write_files"` | ❌ W0 | ⬜ pending |
| 23-01-03 | 01 | 1 | FWRT-03 | unit | `python -m pytest tests/test_file_writer.py -x -k "mkdir"` | ❌ W0 | ⬜ pending |
| 23-01-04 | 01 | 1 | FWRT-04 | unit | `python -m pytest tests/test_file_writer.py -x -k "report"` | ❌ W0 | ⬜ pending |
| 23-01-05 | 01 | 1 | FWRT-05 | unit | `python -m pytest tests/test_file_writer.py -x -k "zero_file"` | ❌ W0 | ⬜ pending |
| 23-01-06 | 01 | 1 | FWRT-06 | unit | `python -m pytest tests/test_file_writer.py -x -k "prompt_format"` | ❌ W0 | ⬜ pending |
| 23-02-01 | 02 | 1 | CTX-07 | unit | `python -m pytest tests/test_reroute.py -x -k "targeted"` | ❌ W0 | ⬜ pending |
| 23-02-02 | 02 | 1 | CTX-08 | unit | `python -m pytest tests/test_section_filter.py -x -k "routing_sections"` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_file_writer.py` — tests for code block parsing, file writing, directory creation, report, zero-file warning
- [ ] `tests/test_reroute.py` — tests for targeted re-route prompt building
- [ ] `tests/test_section_filter.py` — tests for ROUTING_SECTIONS filtering
- [ ] No new framework install needed — pytest + pytest-asyncio already configured

*Existing infrastructure covers framework requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Execute agent outputs code blocks with file path annotations | FWRT-06 | Requires running actual Claude CLI with system prompt | Create a task, verify CODE section has `lang # path/to/file` format |
| Auto-commit includes file writer output | FWRT-04 | Requires full pipeline run with git | Run a task, check git log for committed files |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
