---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (latest stable) |
| **Config file** | `pytest.ini` or `pyproject.toml [tool.pytest.ini_options]` — Wave 0 installs |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 0 | INFR-01 | unit | `pytest tests/test_runner.py -x -q` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 0 | INFR-03 | unit | `pytest tests/test_db.py -x -q` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 0 | INFR-05 | unit | `pytest tests/test_runner.py::test_retry_behavior -x -q` | ❌ W0 | ⬜ pending |
| 1-01-04 | 01 | 0 | INFR-09 | unit | `pytest tests/test_context.py -x -q` | ❌ W0 | ⬜ pending |
| 1-02-01 | 02 | 1 | INFR-01 | integration | `pytest tests/test_runner.py -x -q` | ❌ W0 | ⬜ pending |
| 1-02-02 | 02 | 1 | INFR-01 | unit | `pytest tests/test_parser.py -x -q` | ❌ W0 | ⬜ pending |
| 1-03-01 | 03 | 1 | INFR-03 | integration | `pytest tests/test_db.py -x -q` | ❌ W0 | ⬜ pending |
| 1-03-02 | 03 | 1 | INFR-05 | unit (mock) | `pytest tests/test_runner.py::test_retry_exhausted -x -q` | ❌ W0 | ⬜ pending |
| 1-03-03 | 03 | 1 | INFR-09 | unit | `pytest tests/test_context.py::test_context_excludes -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_runner.py` — stubs for INFR-01, INFR-05
- [ ] `tests/test_db.py` — stubs for INFR-03
- [ ] `tests/test_context.py` — stubs for INFR-09
- [ ] `tests/test_parser.py` — stubs for section extraction (INFR-01 output parsing)
- [ ] `tests/conftest.py` — shared fixtures: in-memory aiosqlite DB, mock subprocess
- [ ] `pytest.ini` or `pyproject.toml` with `asyncio_mode = "auto"` for pytest-asyncio
- [ ] Framework install: `pip install pytest pytest-asyncio`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Claude CLI PATH resolves correctly in Windows subprocess | INFR-01 | Requires real Claude CLI binary on PATH; mock can't verify shutil.which resolution | Run `python -c "import shutil; print(shutil.which('claude'))"` — must return a path, not None |
| `--dangerously-skip-permissions` vs `--permission-mode plan` behavior | INFR-01 | Requires real Claude invocation to verify no interactive prompt appears | Run `claude -p --dangerously-skip-permissions "say hello"` in terminal; confirm non-interactive |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
