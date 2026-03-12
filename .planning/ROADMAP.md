# Roadmap: AI Agent Workflow Console

## Milestones

- ✅ **v1.0 MVP** — Phases 1-5 (shipped 2026-03-12)
- 🚧 **v2.0 Web Platform** — Phases 6-11 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-5) — SHIPPED 2026-03-12</summary>

- [x] Phase 1: Foundation (3/3 plans) — completed 2026-03-12
- [x] Phase 2: Agent Pipeline (4/4 plans) — completed 2026-03-12
- [x] Phase 3: TUI Shell (4/4 plans) — completed 2026-03-12
- [x] Phase 4: Orchestrator Intelligence (2/2 plans) — completed 2026-03-12
- [x] Phase 5: Polish (3/3 plans) — completed 2026-03-12

Full details: `.planning/milestones/v1.0-ROADMAP.md`

</details>

### v2.0 Web Platform

- [ ] **Phase 6: Database and Server Foundation** - PostgreSQL persistence, FastAPI shell, orchestrator decoupled from TUI via TaskContext Protocol
- [ ] **Phase 7: Task Engine and API** - TaskManager with concurrency control, REST endpoints, HTTP Basic Auth
- [ ] **Phase 8: WebSocket Streaming** - Real-time Claude CLI output streamed to browser via WebSocket
- [ ] **Phase 9: Approval Gates** - Supervised mode with per-task autonomy selection and approval/reject flow
- [ ] **Phase 10: Dashboard Frontend** - Alpine.js browser UI consuming all REST and WebSocket APIs
- [ ] **Phase 11: Docker Deployment** - Containerized application deployed on Coolify with Traefik proxy

## Phase Details

### Phase 6: Database and Server Foundation
**Goal**: Application boots as a FastAPI server connected to PostgreSQL, with the orchestrator decoupled from TUI and ready to accept any UI frontend
**Depends on**: Phase 5 (v1.0 complete)
**Requirements**: INFR-01
**Success Criteria** (what must be TRUE):
  1. FastAPI server starts and responds to a health-check endpoint
  2. Task data (tasks, agent_outputs, agent_usage, orchestrator_decisions) persists in PostgreSQL across server restarts
  3. Orchestrator accepts a TaskContext Protocol instead of AgentConsoleApp, enabling web-driven execution
  4. Connection pool is lifespan-managed (created on startup, closed on shutdown)
**Plans**: TBD

Plans:
- [ ] 06-01: PostgreSQL schema and asyncpg repository layer
- [ ] 06-02: FastAPI app factory, lifespan, health endpoint, and TaskContext Protocol with orchestrator refactor

### Phase 7: Task Engine and API
**Goal**: Users can create, list, cancel, and run tasks through authenticated REST endpoints with up to 2 tasks running concurrently
**Depends on**: Phase 6
**Requirements**: TASK-01, TASK-02, TASK-03, INFR-02
**Success Criteria** (what must be TRUE):
  1. User can create a task via POST with a prompt and mode selection (supervised or autonomous)
  2. User can list all tasks with status indicators (queued/running/awaiting_approval/completed/failed/cancelled)
  3. User can cancel a running task and its Claude CLI subprocess is terminated cleanly
  4. Two tasks can execute concurrently; a third task queues until a slot opens
  5. All endpoints reject unauthenticated requests with 401
**Plans**: TBD

Plans:
- [ ] 07-01: TaskManager service with asyncio.Semaphore concurrency and task lifecycle
- [ ] 07-02: REST endpoints (POST /tasks, GET /tasks, GET /tasks/{id}, POST /tasks/{id}/cancel) with HTTP Basic Auth

### Phase 8: WebSocket Streaming
**Goal**: Users see real-time Claude CLI output in their browser as agents execute
**Depends on**: Phase 7
**Requirements**: STRM-01
**Success Criteria** (what must be TRUE):
  1. Browser receives streaming Claude CLI text chunks via WebSocket while a task runs
  2. WebSocket connection authenticates before streaming begins
  3. Connection survives long-running tasks (heartbeat prevents proxy timeout)
  4. Disconnecting and reconnecting does not crash the server or leak resources
**Plans**: TBD

Plans:
- [ ] 08-01: ConnectionManager, WebSocket endpoint, heartbeat, and disconnect handling

### Phase 9: Approval Gates
**Goal**: Users can pause agent execution at each stage in supervised mode and approve or reject the next action with full context
**Depends on**: Phase 8
**Requirements**: TASK-04
**Success Criteria** (what must be TRUE):
  1. In supervised mode, task execution pauses before each agent action and sends an approval_required event via WebSocket
  2. User can approve or reject via REST endpoint, and execution resumes or stops accordingly
  3. Approval request includes context about what the agent wants to do next
  4. In autonomous mode, tasks run without pausing
**Plans**: TBD

Plans:
- [ ] 09-01: ApprovalGate service with asyncio.Event, approval REST endpoints, and WebSocket event integration

### Phase 10: Dashboard Frontend
**Goal**: Users can manage all tasks from a browser-based dashboard accessible from any device
**Depends on**: Phase 9
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04
**Success Criteria** (what must be TRUE):
  1. User sees a task list page with status indicators for all tasks
  2. User can click a task to view its detailed agent output log with step labels
  3. User can create a new task with a prompt input field and mode selector (supervised/autonomous)
  4. User can approve or reject pending actions from the task detail view
  5. Dashboard is accessible from any device with a browser at the configured URL
**Plans**: TBD

Plans:
- [ ] 10-01: Jinja2 templates, Alpine.js components, and Pico CSS layout for task list and creation
- [ ] 10-02: Task detail view with streaming log, step labels, and approval UI

### Phase 11: Docker Deployment
**Goal**: Application runs as a Docker container on Coolify, accessible at console.amcsystem.uk behind Traefik
**Depends on**: Phase 10
**Requirements**: INFR-03
**Success Criteria** (what must be TRUE):
  1. Application builds and runs as a Docker container with Claude CLI available inside
  2. Container deploys on Coolify with auto-deploy from GitHub push
  3. Dashboard is accessible at console.amcsystem.uk via HTTPS through Traefik proxy
  4. WebSocket connections survive long tasks (Traefik timeouts configured, Gzip disabled)
**Plans**: TBD

Plans:
- [ ] 11-01: Dockerfile, volume mounts for Claude CLI auth, Coolify configuration, and Traefik proxy settings

## Progress

**Execution Order:**
Phases execute in numeric order: 6 -> 7 -> 8 -> 9 -> 10 -> 11

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.0 | 3/3 | Complete | 2026-03-12 |
| 2. Agent Pipeline | v1.0 | 4/4 | Complete | 2026-03-12 |
| 3. TUI Shell | v1.0 | 4/4 | Complete | 2026-03-12 |
| 4. Orchestrator Intelligence | v1.0 | 2/2 | Complete | 2026-03-12 |
| 5. Polish | v1.0 | 3/3 | Complete | 2026-03-12 |
| 6. Database and Server Foundation | v2.0 | 0/2 | Not started | - |
| 7. Task Engine and API | v2.0 | 0/2 | Not started | - |
| 8. WebSocket Streaming | v2.0 | 0/1 | Not started | - |
| 9. Approval Gates | v2.0 | 0/1 | Not started | - |
| 10. Dashboard Frontend | v2.0 | 0/2 | Not started | - |
| 11. Docker Deployment | v2.0 | 0/1 | Not started | - |
