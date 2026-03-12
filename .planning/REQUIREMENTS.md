# Requirements: AI Agent Workflow Console

**Defined:** 2026-03-12
**Core Value:** The orchestrator must reliably coordinate agents through iterative cycles -- taking a rough idea and producing complete, usable code output with zero manual agent management. Tasks persist and stream across devices.

## v2.0 Requirements

Requirements for web platform release. Each maps to roadmap phases.

### Dashboard

- [ ] **DASH-01**: User can view list of all tasks with status indicators (queued/running/awaiting_approval/completed/failed/cancelled)
- [ ] **DASH-02**: User can view detailed agent output log for any task with step labels
- [ ] **DASH-03**: User can create a new task with prompt input and mode selection
- [ ] **DASH-04**: User can access tasks from any device via browser

### Streaming

- [ ] **STRM-01**: User sees real-time Claude CLI output streamed via WebSocket during task execution

### Task Management

- [ ] **TASK-01**: User can cancel a running task with subprocess cleanup
- [ ] **TASK-02**: User can run up to 2 tasks concurrently
- [ ] **TASK-03**: User can choose supervised or autonomous mode per task
- [ ] **TASK-04**: User can approve or reject agent actions via approval gate UI with context

### Infrastructure

- [ ] **INFR-01**: Task data persists in PostgreSQL (tasks, outputs, usage, decisions)
- [ ] **INFR-02**: All endpoints require HTTP Basic Auth
- [ ] **INFR-03**: Application deploys as Docker container on Coolify with Traefik proxy

## Future Requirements

Deferred to v2.1+. Tracked but not in current roadmap.

### Streaming Enhancements (v2.1)

- **STRM-02**: Late-join WebSocket replay shows buffered context when connecting to running task
- **STRM-03**: Token usage and estimated cost per task displayed in dashboard

### GitHub Integration (v2.2)

- **GIT-01**: User can clone a GitHub repo into workspace from dashboard
- **GIT-02**: User can commit and push generated code to GitHub
- **GIT-03**: User can create a pull request from dashboard

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Multi-user / team features | Single-user with basic auth sufficient |
| Multi-model support (OpenAI, Gemini) | Claude CLI only by design |
| React/Vue/Svelte frontend | Alpine.js sufficient for single-user, no build step |
| Message queues (Celery/Redis/RabbitMQ) | asyncio semaphore sufficient for 2-task concurrency |
| TUI maintenance | v2.0 replaces TUI with web interface |
| Mobile-responsive polish | Desktop-first, functional on mobile but not optimized |
| Task templates / saved prompts | Nice-to-have, defer to v2.2+ |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DASH-01 | — | Pending |
| DASH-02 | — | Pending |
| DASH-03 | — | Pending |
| DASH-04 | — | Pending |
| STRM-01 | — | Pending |
| TASK-01 | — | Pending |
| TASK-02 | — | Pending |
| TASK-03 | — | Pending |
| TASK-04 | — | Pending |
| INFR-01 | — | Pending |
| INFR-02 | — | Pending |
| INFR-03 | — | Pending |

**Coverage:**
- v2.0 requirements: 12 total
- Mapped to phases: 0
- Unmapped: 12

---
*Requirements defined: 2026-03-12*
*Last updated: 2026-03-12 after initial definition*
