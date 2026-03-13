---
phase: 11
slug: docker-deployment
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-13
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ with pytest-asyncio |
| **Config file** | `pytest.ini` |
| **Quick run command** | `docker build -t agent-console .` |
| **Full suite command** | `docker build -t agent-console . && docker run --rm agent-console claude --version` |
| **Estimated runtime** | ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `docker build -t agent-console .`
- **After every plan wave:** Run `docker build -t agent-console . && docker run --rm -p 8001:8000 agent-console & sleep 5 && curl localhost:8001/health`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 90 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | INFR-03a | smoke | `docker build -t agent-console .` | No -- Wave 0 | ⬜ pending |
| 11-01-02 | 01 | 1 | INFR-03b | smoke | `docker run --rm -p 8001:8000 agent-console & sleep 5 && curl localhost:8001/health` | No -- Wave 0 | ⬜ pending |
| 11-01-03 | 01 | 1 | INFR-03c | smoke | `docker run --rm agent-console claude --version` | No -- Wave 0 | ⬜ pending |
| 11-01-04 | 01 | 1 | INFR-03d | manual-only | Verify in Coolify UI after push | N/A | ⬜ pending |
| 11-01-05 | 01 | 1 | INFR-03e | manual-only | `curl -s https://console.amcsystem.uk/health` | N/A | ⬜ pending |
| 11-01-06 | 01 | 1 | INFR-03f | manual-only | Connect WS, run task, verify no disconnect | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `Dockerfile` — the primary deliverable
- [ ] `.dockerignore` — exclude dev files from build context
- [ ] Coolify application configuration (manual via UI, documented in plan)

*Wave 0 creates artifacts needed before automated verification can begin.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Coolify auto-deploy from GitHub | INFR-03d | Requires Coolify UI interaction | Push to GitHub, verify Coolify triggers build |
| HTTPS access at console.amcsystem.uk | INFR-03e | Requires live DNS + Traefik + TLS | `curl -s https://console.amcsystem.uk/health` after deploy |
| WebSocket survives long tasks | INFR-03f | Requires live WS connection over time | Connect WS client, start long task, verify no disconnect after 60s |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
