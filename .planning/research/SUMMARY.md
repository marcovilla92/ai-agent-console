# Project Research Summary

**Project:** AI Agent Workflow Console v2.0 Web Platform
**Domain:** Web-based AI agent orchestration (TUI-to-web migration)
**Researched:** 2026-03-12
**Confidence:** HIGH

## Executive Summary

The v2.0 migration transforms a validated TUI-based AI agent console into a persistent web platform using FastAPI, asyncpg, Alpine.js, and Pico CSS. The existing v1.0 codebase is well-structured: approximately 70% of core modules (agents, runner, parser, context, pipeline) are directly reusable with zero changes. The migration is primarily a UI layer swap (Textual to FastAPI + Alpine.js) and a database swap (aiosqlite to asyncpg), plus new web-specific components for WebSocket streaming, task lifecycle management, and approval gates. The recommended stack is mature, well-documented, and requires zero build tooling on the frontend -- a deliberate constraint that keeps deployment simple on the Coolify/Traefik VPS.

The recommended architecture centers on four new components: TaskManager (asyncio.Semaphore-based concurrency), ConnectionManager (WebSocket fan-out with late-join replay buffer), ApprovalGate (asyncio.Event pause/resume for supervised mode), and a TaskContext Protocol that decouples the orchestrator from any specific UI. This Protocol is the key architectural decision -- it replaces the current hard dependency on `AgentConsoleApp` with an abstract interface, making the orchestrator testable and reusable across TUI, web, and future interfaces. The build order follows a strict dependency chain: database first, then orchestrator decoupling, then task management, then WebSocket streaming, then approval gates, then frontend, then Docker packaging.

The most dangerous risks are operational, not architectural. Zombie Claude CLI subprocesses can exhaust VPS RAM and OOM-kill shared Coolify services (n8n, Evolution API). WebSocket connections silently die behind Traefik's default 60-second timeout. Claude CLI auth requires mounting two specific files read-write in Docker, and losing either breaks the entire system. asyncpg uses `$1` parameter syntax instead of aiosqlite's `?`, and the migration will crash at runtime if any queries are ported without syntax changes. Every one of these pitfalls has a documented prevention strategy, but they must be addressed in the correct phase -- not retrofitted.

## Key Findings

### Recommended Stack

The stack is zero-build-step by design. FastAPI (>=0.115) provides async-native HTTP and WebSocket support with Pydantic validation. asyncpg (>=0.30) connects directly to the existing Coolify-managed PostgreSQL 16 instance at 5x the speed of psycopg3, with built-in connection pooling. Alpine.js 3.x and Pico CSS 2.x are loaded from CDN, eliminating all frontend tooling. uvicorn with `[standard]` extras provides uvloop performance. The Docker image uses `python:3.12-slim` with Node.js 20 installed for Claude CLI (npm global package).

**Core technologies:**
- **FastAPI 0.135.1:** Web framework -- async-native, first-class WebSocket, Pydantic built-in
- **asyncpg 0.31.0:** PostgreSQL driver -- 5x faster than psycopg3 async, binary protocol, built-in pool
- **Alpine.js 3.15.1:** Client-side reactivity -- 17KB, no build step, CDN delivery
- **Pico CSS 2.1.1:** Semantic styling -- dark mode built-in, zero classes needed, CDN delivery
- **uvicorn 0.41.0:** ASGI server -- uvloop + httptools via `[standard]` extras
- **Jinja2 3.1.4+:** Server-side templates -- renders page shell, Alpine.js handles dynamic updates

**Critical exclusions:** No SQLAlchemy/Alembic (raw SQL sufficient for ~10 tables), no Celery/Redis (asyncio primitives handle 2-task concurrency), no React/Vue/Svelte (build step violates constraints), no Socket.IO (unnecessary protocol layer for single-node). Remove aiosqlite and Textual from dependencies.

### Expected Features

**Must have (table stakes -- P1 launch):**
- Task list with status indicators (queued/running/awaiting_approval/completed/failed/cancelled)
- Real-time WebSocket streaming of Claude CLI output per task
- Task creation with prompt input and mode selection (supervised/autonomous)
- Task detail view with full agent step log
- Cross-device persistence via PostgreSQL
- HTTP Basic Auth on all endpoints and WebSocket handshake
- Task cancellation with subprocess cleanup
- Docker deployment on Coolify

**Should have (differentiators -- P1 launch):**
- Hybrid autonomy modes per task -- the killer feature; no competitor offers per-task autonomy selection
- Approval gate UI showing what the agent wants to do next (not a bare "continue?" prompt)

**Defer to v2.1:**
- Late-join WebSocket replay buffer (needed once cross-device pain is felt)
- Task parallelism with queue visualization
- Token/cost tracking dashboard view
- Rich approval gate context

**Defer to v2.2+:**
- GitHub integration (clone, commit, push, PR) -- highest complexity, most security surface
- Mobile-responsive polish
- Task templates / saved prompts

### Architecture Approach

The architecture is a layered system: browser (Alpine.js + Pico CSS) communicates via REST for CRUD and WebSocket for streaming/events to a FastAPI server. The server contains four new service components (TaskManager, ConnectionManager, ApprovalGate, TaskContext) that mediate between the web layer and the reused v1.0 core (orchestrator, agents, runner, parser, context). Data flows through asyncpg to the existing PostgreSQL 16 instance. The orchestrator is decoupled from the UI via a TaskContext Protocol -- the single most important refactor in the migration.

**Major components:**
1. **TaskManager** -- task lifecycle (create/run/cancel), asyncio.Semaphore(2) concurrency control, graceful shutdown
2. **ConnectionManager** -- WebSocket connection tracking per task_id, broadcast fan-out, late-join replay via deque(maxlen=500)
3. **ApprovalGate** -- asyncio.Event per task for supervised mode pause/resume, zero-polling approval flow
4. **TaskContext Protocol** -- abstract interface replacing AgentConsoleApp dependency, enables orchestrator to work with any UI
5. **asyncpg pool** -- lifespan-managed connection pool (min=2, max=5), replaces single aiosqlite connection
6. **PostgreSQL schema** -- tasks, agent_outputs, agent_usage, orchestrator_decisions tables with proper indexes

### Critical Pitfalls

1. **Zombie Claude CLI subprocesses** -- Each subprocess uses 200-500MB RAM. If WebSocket disconnects without cleanup, zombies accumulate and OOM-kill shared VPS services. Prevention: try/finally with proc.terminate()/kill() around every stream_claude call, TaskManager registry for shutdown, Docker mem_limit of 3g.

2. **WebSocket death behind Traefik** -- Traefik's default 60-second timeout kills long-running connections. Coolify's Gzip compression breaks WebSocket streaming (confirmed bug #4002). Prevention: set readTimeout/writeTimeout/idleTimeout to 30m in Coolify proxy settings, disable Gzip, implement 15-second server heartbeat, run concurrent receive_text() for disconnect detection.

3. **Claude CLI auth in Docker** -- Requires TWO files (`~/.claude/` directory AND `~/.claude.json`), both read-write. Using Claude on host can delete container credentials. Prevention: mount both paths, verify in entrypoint script, set CLAUDE_CONFIG_DIR, keep credentials exclusive to container.

4. **asyncpg pool exhaustion** -- Holding connections during long subprocess waits (current aiosqlite pattern) will drain the 5-connection pool with 2 concurrent tasks. Prevention: acquire/write/release pattern around each DB operation, never hold connections across subprocess calls.

5. **asyncio task lifecycle mismatch** -- Background tasks survive FastAPI shutdown, causing 30-second hangs and inconsistent DB state. Prevention: TaskManager tracks all tasks, calls cancel() in lifespan teardown, startup reconciliation marks stale "running" records as "interrupted".

## Implications for Roadmap

Based on research, the suggested phase structure follows the dependency graph from ARCHITECTURE.md with pitfall prevention integrated at each layer.

### Phase 1: Database Foundation
**Rationale:** Every feature depends on PostgreSQL persistence. The repository rewrite touches agents/base.py (db parameter type change), making this a prerequisite for all subsequent work.
**Delivers:** asyncpg connection pool, PostgreSQL schema (tasks, agent_outputs, agent_usage, orchestrator_decisions), repository module rewritten with `$1` parameterized queries, lifespan-managed pool lifecycle.
**Addresses:** Cross-device persistence, task status tracking.
**Avoids:** asyncpg pool exhaustion (acquire/release pattern from day one), aiosqlite syntax carryover (`?` to `$1`).

### Phase 2: FastAPI Shell and Orchestrator Decoupling
**Rationale:** The server must boot and connect to the database before any features can be built. The orchestrator must be decoupled from Textual before the TaskManager can call it.
**Delivers:** FastAPI app factory with lifespan, health endpoint, TaskContext Protocol, orchestrator refactored to accept TaskContext instead of AgentConsoleApp.
**Addresses:** Web accessibility foundation, testable orchestrator.
**Avoids:** Tight coupling between orchestrator and web layer (anti-pattern from ARCHITECTURE.md).

### Phase 3: Task Manager and REST API
**Rationale:** Task creation and lifecycle management depend on both the database (phase 1) and the decoupled orchestrator (phase 2). REST endpoints are needed before WebSocket because task creation is a REST operation.
**Delivers:** TaskManager with Semaphore(2), REST endpoints (POST /tasks, GET /tasks, GET /tasks/{id}, POST /tasks/{id}/cancel), HTTP Basic Auth, task queuing and execution.
**Addresses:** Task creation, task listing, task cancellation, basic auth.
**Avoids:** asyncio task lifecycle mismatch (TaskManager tracks all tasks, handles shutdown), zombie subprocesses (try/finally cleanup in task execution).

### Phase 4: WebSocket Streaming
**Rationale:** WebSocket infrastructure depends on TaskManager (phase 3) for knowing which tasks are active. This is the core UX -- streaming Claude CLI output to the browser in real-time.
**Delivers:** ConnectionManager, WebSocket endpoint per task, late-join replay buffer (deque), chunk batching (50ms/1KB flush), heartbeat (15s ping), disconnect detection via concurrent receive_text().
**Addresses:** Real-time streaming output, late-join replay, cross-device live viewing.
**Avoids:** WebSocket message buffer overflow (batching), zombie subprocesses on disconnect (cleanup in finally block), silent connection death (heartbeat + disconnect watcher).

### Phase 5: Approval Gates and Supervised Mode
**Rationale:** Approval gates require both WebSocket (phase 4, for pushing approval_required events) and TaskManager (phase 3, for pausing pipeline execution). This is the differentiator feature.
**Delivers:** ApprovalGate with asyncio.Event, supervised/autonomous mode selection per task, approval/reject REST endpoints, approval request display with agent context.
**Addresses:** Hybrid autonomy (the killer feature), approval gate UI.
**Avoids:** Polling for approval status (event-driven via WebSocket push).

### Phase 6: Alpine.js Frontend
**Rationale:** All backend APIs exist by this point. Building the frontend last avoids rework as APIs evolve. The UI consumes REST for CRUD and WebSocket for streaming.
**Delivers:** Dashboard (task list with status), task detail view (streaming log + step labels), task creation form (prompt + mode selector), approval UI (approve/reject with context), Jinja2 templates + Alpine.js components, Pico CSS styling.
**Addresses:** All UI-facing features from the table stakes list.
**Avoids:** Building UI against unstable APIs (frontend last principle).

### Phase 7: Docker and Coolify Deployment
**Rationale:** Packaging and deployment come after the application works locally. Docker configuration addresses the majority of operational pitfalls (Claude CLI auth, network isolation, memory limits).
**Delivers:** Dockerfile (python:3.12-slim + Node.js 20), volume mounts for Claude CLI auth and workspaces, Coolify configuration, Traefik timeout settings (30m), Gzip disabled, Docker memory limit (3g), entrypoint script for auth verification.
**Addresses:** Docker deployment, production readiness.
**Avoids:** Claude CLI auth loss (two-file mount), Docker network isolation (shared Coolify network), Traefik timeout kills (30m settings), OOM cascading to other services (mem_limit).

### Phase 8: GitHub Integration (v2.2)
**Rationale:** Highest complexity feature that blocks nothing else. The platform is fully usable without it. Build on a stable, deployed foundation.
**Delivers:** Repo cloning to workspace volumes, branch management, commit/push, PR creation via GitHub API.
**Addresses:** GitHub integration feature.
**Avoids:** Premature complexity in core platform.

### Phase Ordering Rationale

- **Database first** because the repository rewrite changes the db parameter type in agents/base.py, affecting all modules that touch persistence.
- **Orchestrator decoupling before TaskManager** because TaskManager calls the orchestrator -- the orchestrator must accept TaskContext before it can be wrapped in a managed task.
- **WebSocket before ApprovalGate** because approval events are delivered via WebSocket -- the ConnectionManager must exist before approval_required messages can be broadcast.
- **Frontend after all APIs** because it consumes every endpoint. Building it earlier means constant rework as APIs evolve during phases 3-5.
- **Docker after local validation** because it is packaging, not architecture. Containerization bugs (auth, networking, Traefik) are easier to debug when the application is already known to work.
- **GitHub integration last** because it is independent, high-complexity, and the platform delivers full value without it.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4 (WebSocket Streaming):** Complex interaction between subprocess lifecycle, backpressure handling, and disconnect detection. Multiple confirmed bugs in Coolify/Traefik affect this phase. Needs phase-level research.
- **Phase 7 (Docker/Coolify Deployment):** Claude CLI auth in containers has multiple documented failure modes. Traefik proxy configuration is Coolify-version-dependent. Needs phase-level research to verify current Coolify settings.
- **Phase 8 (GitHub Integration):** Repo lifecycle management, branch strategy, auth token handling, security sandboxing. Highest complexity. Needs dedicated research.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Database Foundation):** asyncpg pool + PostgreSQL DDL is extremely well-documented. Standard pattern.
- **Phase 2 (FastAPI Shell):** FastAPI lifespan + health endpoint is boilerplate. Protocol pattern is standard Python.
- **Phase 3 (Task Manager + REST):** asyncio.Semaphore and REST CRUD are well-documented patterns. HTTP Basic Auth is built into FastAPI.
- **Phase 5 (Approval Gates):** asyncio.Event is a standard primitive. The pattern is documented in ARCHITECTURE.md with working code.
- **Phase 6 (Frontend):** Alpine.js + Pico CSS are simple, well-documented. No build step complexity.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified on PyPI/GitHub. FastAPI + asyncpg + Alpine.js is a proven combination. No exotic dependencies. |
| Features | HIGH | Feature landscape well-mapped against competitors. Hybrid autonomy validated as differentiated. Clear P1/P2/P3 prioritization. Anti-features correctly identified. |
| Architecture | HIGH | Four core patterns (TaskManager, ConnectionManager, ApprovalGate, TaskContext) have working code examples. Build order follows verified dependency graph. v1.0 module reuse map is accurate. |
| Pitfalls | HIGH | All critical pitfalls traced to specific GitHub issues with confirmed status. Coolify/Traefik issues (#4002, #5358) verified against official bug trackers. Claude CLI Docker auth issues documented in multiple sources. |

**Overall confidence:** HIGH

### Gaps to Address

- **Claude CLI version pinning in Docker:** The Dockerfile installs `@anthropic-ai/claude-code` globally but does not pin a version. Claude CLI updates could introduce breaking changes. Pin to a known-good version during phase 7 planning.
- **PostgreSQL connection string for Coolify networking:** The exact hostname for the Coolify-managed PostgreSQL instance needs to be confirmed from the Coolify dashboard during phase 1. It may be a service name like `postgresql-xxxx` or a Docker network IP.
- **Traefik configuration method in Coolify 4.0:** The proxy timeout settings may need to be applied via Coolify dashboard, docker-compose labels, or server-level config depending on the current Coolify interface. Verify during phase 7.
- **WebSocket reconnection strategy:** Research covers disconnect detection but not automatic client-side reconnection with state recovery. Address during phase 4 or 6 planning -- Alpine.js reconnect logic with exponential backoff and replay-from-last-event.
- **Startup reconciliation for stale task state:** The pattern is described (mark "running" as "interrupted" on boot) but the exact SQL and timing within the lifespan handler need to be designed during phase 2.

## Sources

### Primary (HIGH confidence)
- FastAPI PyPI (v0.135.1), asyncpg PyPI (v0.31.0), uvicorn PyPI (v0.41.0) -- version verification
- FastAPI WebSocket docs, FastAPI Templates docs -- integration patterns
- asyncpg official docs -- connection pool patterns
- Claude Code Docker Auth (GitHub #1736), Claude Code Dev Containers docs -- Docker auth requirements
- Coolify WebSocket/Gzip Bug (GitHub #4002), Coolify Traefik Timeout (GitHub #5358) -- proxy pitfalls
- FastAPI WebSocket Disconnect (GitHub #9031) -- disconnect detection
- Docker Resource Constraints docs -- memory limits
- Python asyncio Queue docs -- concurrency primitives

### Secondary (MEDIUM confidence)
- FastAPI + asyncpg without ORM (sheshbabu.com) -- pattern validation
- Supervised Autonomy Agents (Medium, 2026) -- feature validation for hybrid autonomy
- WebSocket Replay Buffer Patterns (Substack) -- Discord case study for late-join
- Coolify Traefik Zombie State (GitHub #7744) -- recovery strategy
- AI Coding Agents Comparison (devvela.com, 2026) -- competitive landscape

---
*Research completed: 2026-03-12*
*Ready for roadmap: yes*
