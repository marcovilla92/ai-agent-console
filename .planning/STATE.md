---
gsd_state_version: 1.0
milestone: v2.1
milestone_name: Project Router
status: active
stopped_at: ""
last_updated: "2026-03-13T16:00:00.000Z"
last_activity: 2026-03-13 -- Milestone v2.1 started
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-13)

**Core value:** The orchestrator must reliably coordinate agents through iterative cycles -- taking a rough idea and producing complete, usable code output with zero manual agent management. Tasks persist and stream across devices.
**Current focus:** Defining requirements for v2.1 Project Router

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-03-13 — Milestone v2.1 started

## Performance Metrics

**Velocity:**
- Total plans completed: 1 (v2.0)
- Average duration: 5min
- Total execution time: 5min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| Phase 06 P01 | 5min | 2 tasks | 6 files |
| Phase 06 P02 | 6min | 2 tasks | 8 files |
| Phase 07 P01 | 3min | 2 tasks | 8 files |
| Phase 07 P02 | 3min | 2 tasks | 6 files |
| Phase 08 P01 | 11min | 2 tasks | 7 files |
| Phase 09 P01 | 9min | 2 tasks | 6 files |
| Phase 10 P01 | 2min | 2 tasks | 6 files |
| Phase 10 P02 | 2min | 2 tasks | 2 files |
| Phase 10 P03 | 2min | 1 tasks | 3 files |
| Phase 11 P01 | 2min | 1 tasks | 2 files |

## Accumulated Context

### Decisions

- [v1.0]: Build bottom-up (infra -> agents -> TUI -> orchestrator -> polish)
- [v1.0]: stream_claude yields dict for result events (isinstance check)
- [v2.0]: FastAPI + asyncpg + Alpine.js stack (no build step, no message broker)
- [v2.0]: Reuse ~70% of core modules (agents, runner, parser, context, pipeline)
- [v2.0]: asyncio.Semaphore(2) for concurrent task limit (RAM constraint)
- [v2.0]: asyncio.Event for supervised approval gates
- [v2.0]: Frontend built last -- all APIs must exist before UI work begins
- [Phase 06]: Renamed sessions table to tasks for v2.0 web mental model alignment
- [Phase 06]: Used app.router.lifespan_context for test pool management instead of asgi-lifespan package
- [Phase 06]: Removed TUI modal dialog functions from orchestrator -- logic moves to TaskContext implementations
- [Phase 07]: WebTaskContext auto-approves all reroutes and halts (approval UI deferred to Phase 9)
- [Phase 07]: TaskManager creates fresh WebTaskContext inside _execute after semaphore acquired
- [Phase 07]: completed_at set via update_status workflow, not during create
- [Phase 07]: HTTP Basic Auth with secrets.compare_digest for timing-safe credential comparison
- [Phase 07]: Router-level auth dependency protects all /tasks endpoints, /health stays open
- [Phase 07]: TaskManager created in lifespan after schema migration, shutdown before pool close
- [Phase 08]: Base64 query token auth for WebSocket (browsers cannot set WS headers)
- [Phase 08]: ConnectionManager auto-prunes dead sockets on broadcast
- [Phase 08]: Heartbeat ping every 25s keeps reverse proxy connections alive
- [Phase 08]: connection_manager=None preserves backward compatibility for non-web contexts
- [Phase 09]: asyncio.Event for approval gate pause/resume -- lightweight, no external deps
- [Phase 09]: Status transitions: running -> awaiting_approval -> running on approve
- [Phase 09]: Pydantic Literal['approve','reject','continue'] for decision validation (422 on invalid)
- [Phase 09]: 409 Conflict for approve on non-awaiting task, 404 for missing task
- [Phase 10]: Template directory resolved via Path(__file__).resolve() to avoid CWD issues
- [Phase 10]: Alpine.js x-text/x-bind preferred over {{ }} to avoid Jinja2 delimiter collision
- [Phase 10]: Task list auto-refreshes every 5s via setInterval
- [Phase 10]: Placeholder task_detail.html so /tasks/{id}/view works before Plan 02
- [Phase 10]: Used {% raw %} block around script to prevent Jinja2 interpreting JS template literals
- [Phase 10]: WebSocket token stored in sessionStorage after initial credential prompt
- [Phase 10]: Auto-reconnect after 3s delay only for active task statuses
- [Phase 10]: Outputs endpoint returns empty list (not 404) for tasks with no agent outputs
- [Phase 11]: python:3.12-slim over alpine -- Claude CLI Node.js native modules need glibc
- [Phase 11]: Pin Claude CLI to v2.1.74 for reproducible builds
- [Phase 11]: Single requirements.txt (no prod/dev split) -- acceptable for single-user project
- [Phase 11]: No HEALTHCHECK directive -- Coolify handles health checks via /health endpoint
- [Phase 11]: Non-root appuser in container -- Claude CLI refuses --dangerously-skip-permissions as root
- [Phase 11]: Reused existing PostgreSQL with dedicated agent_console database
- [Phase 11]: uvicorn[standard] for WebSocket support, jinja2 for templates

### Pending Todos

None yet.

### Blockers/Concerns

- Claude CLI auth inside Docker container needs ~/.claude volume mount
- SSH key forwarding for GitHub push from Docker container
- VPS RAM budget (~5GB margin) should be monitored under load

## Session Continuity

Last session: 2026-03-13T14:40:00.000Z
Stopped at: Phase 11 fully deployed and E2E verified on Coolify
Resume file: None
