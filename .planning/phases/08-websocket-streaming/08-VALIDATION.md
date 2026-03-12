---
phase: 8
slug: websocket-streaming
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio |
| **Config file** | pyproject.toml (existing) |
| **Quick run command** | `python -m pytest tests/test_websocket.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_websocket.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | STRM-01 | unit | `python -m pytest tests/test_websocket.py::test_connection_manager_lifecycle -x` | ❌ W0 | ⬜ pending |
| 08-01-02 | 01 | 1 | STRM-01 | integration | `python -m pytest tests/test_websocket.py::test_ws_connect_with_auth -x` | ❌ W0 | ⬜ pending |
| 08-01-03 | 01 | 1 | STRM-01 | integration | `python -m pytest tests/test_websocket.py::test_ws_rejects_invalid_auth -x` | ❌ W0 | ⬜ pending |
| 08-01-04 | 01 | 1 | STRM-01 | integration | `python -m pytest tests/test_websocket.py::test_ws_receives_chunks -x` | ❌ W0 | ⬜ pending |
| 08-01-05 | 01 | 1 | STRM-01 | unit | `python -m pytest tests/test_websocket.py::test_heartbeat_sends_ping -x` | ❌ W0 | ⬜ pending |
| 08-01-06 | 01 | 1 | STRM-01 | integration | `python -m pytest tests/test_websocket.py::test_disconnect_cleanup -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_websocket.py` — stubs for STRM-01 (all sub-requirements: auth, streaming, heartbeat, disconnect)
- [ ] Starlette `TestClient` used for WebSocket testing (httpx AsyncClient does NOT support WebSocket)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Traefik proxy keepalive | STRM-01 | Requires real Traefik proxy (Phase 11 Docker deployment) | Deploy behind Traefik, connect WebSocket, wait 60s+ with no output, verify connection survives |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
