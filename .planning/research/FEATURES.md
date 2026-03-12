# Feature Research

**Domain:** AI agent workflow web platform (v2.0 TUI-to-web migration)
**Researched:** 2026-03-12
**Confidence:** HIGH (core patterns well-documented across industry)

## Context

This research covers the NEW web-specific features for v2.0. The existing v1.0 TUI features (3-agent pipeline, AI orchestrator, streaming, session persistence, git auto-commit, token tracking) are already validated and ~70% of core modules are reusable. This document focuses on: REST API, WebSocket streaming, task parallelism, approval gates, GitHub integration, and Docker deployment.

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist in a web-based agent console. Missing these = product feels broken.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Task list with status indicators | Every web dashboard shows running/completed/failed at a glance. This is the home screen. | LOW | REST endpoint returning task list from PostgreSQL. Status enum: `queued`, `running`, `awaiting_approval`, `completed`, `failed`, `cancelled`. Adapt v1.0 session persistence logic. |
| Real-time streaming output | v1.0 already streams Claude CLI output; removing this in the web version would be a regression. Users will not wait for a task to finish to see output. | MEDIUM | WebSocket per-task channel. FastAPI `WebSocket` endpoint + `ConnectionManager` class tracking connections per `task_id`. Existing `stream_claude` generator yields dicts -- pipe these into WebSocket JSON frames. |
| Task creation with prompt input | The core interaction: type a prompt, choose a mode, launch a task. | LOW | REST POST endpoint. Alpine.js form with textarea + mode selector (supervised/autonomous). |
| Task detail view with full log | Click a task, see everything that happened -- each agent step, output, timing. | LOW | REST GET endpoint returning all steps/logs. Render step-by-step with agent labels (Plan/Execute/Review). Store in PostgreSQL `task_steps` table. |
| Cross-device persistence | The entire reason for moving to web. Start task on laptop, check result on phone. | LOW | PostgreSQL handles this automatically. No special feature needed beyond correct data modeling. All task state in DB, not in-process memory. |
| Basic auth protection | A web-accessible agent console without auth is a security incident. The VPS is public. | LOW | FastAPI `HTTPBasic` dependency. Single user/password from env vars. Apply to all REST routes and WebSocket upgrade handshake. |
| Task cancellation | Users must be able to stop a runaway agent. Without this, the only option is SSH + kill. | MEDIUM | Send SIGTERM to Claude CLI subprocess. Set task status to `cancelled`. Clean up asyncio task. Release semaphore slot. Save partial output to DB. |
| Error display with context | When a task fails, show why -- without requiring SSH to read server logs. | LOW | Store error messages and tracebacks in `task_steps` table. Display in UI with the failing agent step highlighted. Existing retry logic (3 attempts, exponential backoff) already captures errors. |
| Docker deployment | The platform must be deployable on Coolify with zero manual server setup. | MEDIUM | Dockerfile with Python + Claude CLI. Docker Compose for local dev. Coolify deployment via git push. Volume mounts for workspace repos. Environment variables for auth, DB connection, GitHub tokens. |

### Differentiators (Competitive Advantage)

Features that set this apart from "just run Claude CLI in a terminal."

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Hybrid autonomy modes (supervised/autonomous per-task) | The killer feature. Devin runs fully autonomous (you find out it went sideways after 30 minutes). Claude Code CLI is fully supervised (approve every tool call). This platform lets you choose per-task. "Update the README" runs autonomous; "refactor the auth system" pauses for approval. Matches the "supervised autonomy" pattern recognized as industry best practice in 2026. | MEDIUM | `asyncio.Event` per approval gate. In supervised mode, after each pipeline stage (Plan/Execute/Review), set task status to `awaiting_approval` and `await event.wait()`. REST endpoint or WebSocket message calls `event.set()`. In autonomous mode, events are pre-set (never block). Store mode choice in task record. |
| Late-join WebSocket replay | Open a task on your phone that has been running for 10 minutes and immediately see all prior output -- not a blank "connected, waiting..." screen. Industry-validated pattern: circular buffer per task. Discord uses this at scale with pre-allocated ring buffers. | MEDIUM | Bounded `collections.deque(maxlen=500)` per active task in memory. On WebSocket connect, burst-send entire buffer, then switch to live streaming. Also send current task status + step info for UI hydration. Clear buffer on task completion (full logs are in PostgreSQL). |
| Approval gate UI with step context | When a task pauses, show WHAT it wants to do next -- the plan output, the proposed code changes -- so you make an informed approve/reject decision. Not a bare "continue?" prompt. | LOW | The pipeline already produces structured handoffs between agents. Display the last agent's output alongside approve/reject buttons. WebSocket pushes `awaiting_approval` event with the handoff payload. |
| GitHub integration (clone, commit, push, PR) | Tasks that produce code should commit and PR without manual git commands. Sweep.dev and GitHub Agentic Workflows set this expectation for AI coding tools in 2026. | HIGH | GitPython for repo operations (clone to workspace volume, commit, push). GitHub PAT for authentication (stored in env var). PR creation via GitHub REST API or `gh` CLI subprocess. Security: validate repo URLs against allowlist, sandbox workspace paths, never accept tokens from user input. This is the most complex feature -- repo lifecycle management, branch strategy, conflict detection, auth token management. |
| Token/cost tracking dashboard | Already built in v1.0 but trapped in TUI. Surfacing per-task and aggregate cost in a web view is genuinely useful vs. raw CLI output. | LOW | Existing token tracking logic ports directly. REST endpoint for cost summary. Alpine.js table: per-task cost, per-day aggregate, running total. |
| Task parallelism with queue visualization | Run 2 tasks concurrently (semaphore-limited by VPS RAM), queue additional ones. Show queue position in UI. Most AI agent tools run one task at a time. | MEDIUM | `asyncio.Semaphore(2)` gates task execution. `asyncio.Queue` for pending tasks. WebSocket broadcasts queue position changes. UI shows: running (up to 2), queued (with position number), completed history. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems for this specific project.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Multi-user / team features | "Other devs should use it too" | Massively increases complexity: per-user task isolation, RBAC, workspace separation, concurrent git conflicts, upgrade from Basic Auth to OAuth/JWT. Single-user is a constraint, not a bug -- keeps the system simple and the VPS resource budget manageable (5GB RAM margin for everything). | Keep single-user. If team access needed, deploy separate instances per developer. |
| Message broker (Celery/Redis/RabbitMQ) | "You need a proper queue" | Overkill for 2-3 concurrent tasks on a single VPS. Adds another service to manage in Coolify, memory overhead (~100MB for Redis), and deployment complexity. asyncio primitives handle this workload perfectly for single-user. | `asyncio.Queue` + `asyncio.Semaphore`. In-process, zero-dependency, sufficient for single-user with max 2 concurrent tasks. |
| React/Vue/Svelte frontend | "You need a proper frontend framework" | Build step, node_modules, bundler config, HMR setup -- all for a single-user dashboard that displays task lists and log streams. The UI has maybe 5 views total. | Alpine.js (inline in HTML, no build step) + Pico CSS (classless styling). Ship HTML files directly from FastAPI static mount. |
| WebSocket for everything (replace REST) | "Just use WebSocket for all communication" | WebSocket is stateful, harder to debug/cache/test. REST is better for CRUD (create task, list tasks, get detail). Mixing concerns makes both harder to maintain. | Hybrid: REST for CRUD operations, WebSocket exclusively for streaming output and real-time events (approval requests, status changes, queue updates). |
| Automatic merge conflict resolution | "The system should handle merge conflicts" | Merge conflicts require human judgment about code intent. Auto-resolution produces broken code silently. | Create branches, commit, push, open PRs. Let the human resolve conflicts through normal PR review. If needed, AI agents can attempt resolution as a separate task -- but never auto-merge to main. |
| SSE instead of WebSocket | "SSE is simpler for streaming" | SSE is unidirectional (server to client only). This platform needs bidirectional communication: client sends approval decisions, cancellation signals, and mode changes during streaming. Using SSE would require a separate REST channel for client-to-server messages, splitting the real-time connection into two protocols. | WebSocket for all real-time communication. The bidirectional requirement (approval gates, cancel, mode switch) makes WebSocket the correct choice despite slightly higher implementation cost. |
| Plugin/extension system for custom agents | "Let users add their own agents via web UI" | v1.0 already has a config-driven agent registry. A web-based plugin system (upload code, hot-reload, sandboxing) is a massive security and complexity surface for a single-user tool. | Keep config-driven agent registry from v1.0. Add new agents by editing config and redeploying. |
| Real-time collaborative prompt editing | "Like Google Docs for prompts" | CRDT/OT complexity for zero concurrent users. Single-user system. The prompt is typed once and submitted. | Simple textarea with draft auto-save to localStorage. |

## Feature Dependencies

```
[PostgreSQL Persistence]
    |-- required by --> [Task List / Detail Views]
    |-- required by --> [Task Creation]
    |-- required by --> [Token/Cost Dashboard]
    |-- required by --> [Cross-device Access]

[WebSocket Streaming]
    |-- required by --> [Late-Join Replay Buffer]
    |-- required by --> [Approval Gate UI]
    |-- required by --> [Real-time Status Updates]
    |-- required by --> [Queue Position Updates]

[Basic Auth]
    |-- required by --> [All REST endpoints]
    |-- required by --> [WebSocket upgrade handshake]

[Task Runner (asyncio)]
    |-- required by --> [Hybrid Autonomy (supervised/autonomous)]
    |-- required by --> [Task Parallelism + Queue]
    |-- required by --> [Task Cancellation]

[Hybrid Autonomy]
    |-- requires --> [WebSocket Streaming] (push approval requests to browser)
    |-- requires --> [Task Runner] (asyncio.Event gates in pipeline)

[GitHub Integration]
    |-- requires --> [Task Runner] (git ops execute as task steps)
    |-- requires --> [PostgreSQL] (store repo metadata, PR links)
    |-- enhances --> [Task Detail View] (show commit hashes, PR links)

[Late-Join Replay]
    |-- requires --> [WebSocket Streaming]
    |-- enhances --> [Cross-device Access] (open phone, see full history)

[Task Parallelism]
    |-- requires --> [Task Runner]
    |-- requires --> [PostgreSQL] (persist queue state across restarts)
    |-- enhances --> [Task List] (queue position display)

[Docker Deployment]
    |-- requires --> [PostgreSQL] (external service connection)
    |-- requires --> [All features complete] (deploy what works)
```

### Dependency Notes

- **PostgreSQL is foundational.** Every read/write feature depends on it. Must be the first thing wired up. The existing Coolify-managed PostgreSQL 16 instance is ready.
- **WebSocket streaming enables the differentiators.** Late-join replay, approval gate UI, and queue updates all depend on WebSocket infrastructure. Get this right early.
- **Hybrid autonomy requires both WebSocket and Task Runner.** The approval flow needs WebSocket to push gate notifications and REST/WebSocket to receive approve/reject. The task runner needs `asyncio.Event` to pause/resume. These must be built together.
- **GitHub integration is independent and complex.** It enhances the platform but blocks nothing else. Build it last -- highest complexity, most security surface, and the platform is fully usable without it.
- **Docker deployment wraps everything.** It depends on features being done but is simple to add incrementally (Dockerfile early, refine as features land).

## MVP Definition

### Launch With (v2.0 Core)

Minimum viable web platform -- what replaces the TUI and validates web-based agent management.

- [ ] PostgreSQL persistence (tasks, steps, logs, tokens) -- foundation for everything
- [ ] REST API for task CRUD (create, list, get detail, cancel) -- basic operations
- [ ] Task runner with asyncio pipeline execution -- reuses v1.0 pipeline core (~70% of modules)
- [ ] WebSocket streaming of Claude CLI output per task -- core UX, replaces TUI streaming
- [ ] Basic Auth on all endpoints -- security baseline for public VPS
- [ ] Alpine.js dashboard: task list, task detail with streaming log, task creation form -- the UI
- [ ] Hybrid autonomy: supervised (approval gates) and autonomous modes per task -- the differentiator
- [ ] Docker deployment on Coolify -- ship it to console.amcsystem.uk

### Add After Core Works (v2.1)

Features to add once the core platform is stable and used daily.

- [ ] Late-join WebSocket replay buffer -- needed once cross-device usage reveals "connected, no output" pain
- [ ] Task parallelism with queue visualization -- needed once single-task bottleneck becomes frustrating
- [ ] Token/cost tracking dashboard view -- data exists from v1.0, just needs a web UI
- [ ] Rich approval gate context (show plan details alongside approve/reject) -- enhance basic approval UX

### Add When Core Is Solid (v2.2+)

Features that require the platform to be reliable before adding complexity.

- [ ] GitHub integration (clone, commit, push, PR creation) -- highest complexity, build on stable foundation
- [ ] Mobile-responsive layout polish -- once desktop version works well
- [ ] Task templates / saved prompts -- once common patterns emerge from usage

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| PostgreSQL persistence | HIGH | MEDIUM | P1 |
| REST API (task CRUD) | HIGH | LOW | P1 |
| Task runner (asyncio pipeline) | HIGH | MEDIUM | P1 |
| WebSocket streaming | HIGH | MEDIUM | P1 |
| Basic Auth | HIGH | LOW | P1 |
| Alpine.js dashboard | HIGH | MEDIUM | P1 |
| Hybrid autonomy modes | HIGH | MEDIUM | P1 |
| Docker/Coolify deployment | HIGH | LOW | P1 |
| Task cancellation | MEDIUM | MEDIUM | P1 |
| Late-join replay buffer | MEDIUM | LOW | P2 |
| Task parallelism + queue | MEDIUM | MEDIUM | P2 |
| Token/cost dashboard | MEDIUM | LOW | P2 |
| Rich approval gate context | MEDIUM | LOW | P2 |
| GitHub integration | HIGH | HIGH | P3 |
| Mobile-responsive polish | LOW | LOW | P3 |
| Task templates | LOW | LOW | P3 |

**Priority key:**
- P1: Must have for launch (replaces TUI, validates web platform concept)
- P2: Should have, add once core is stable (enhances daily use)
- P3: Nice to have, build on solid foundation (high complexity or polish)

## Competitor Feature Analysis

| Feature | Devin | Claude Code (CLI) | Sweep.dev | GitHub Agentic Workflows | This Platform |
|---------|-------|-------------------|-----------|--------------------------|---------------|
| Interface | Web chat (Slack-like) | Terminal | GitHub Issues | GitHub Actions YAML | Web dashboard |
| Execution visibility | Cloud IDE view | Terminal streaming | PR diff only | Action logs | WebSocket streaming with agent step labels |
| Autonomy control | Fully autonomous | Fully supervised (each tool call) | Fully autonomous | YAML-defined | Hybrid: choose per task |
| Approval gates | None (auto-runs) | Every tool call | None | Read-only default, "safe outputs" for writes | Per pipeline stage (Plan/Execute/Review) |
| Multi-task | One at a time | One terminal session | Parallel PRs | Parallel workflows | 2 concurrent + queue |
| Cross-device | Yes (web) | No (local terminal) | Yes (GitHub) | Yes (GitHub) | Yes (web dashboard) |
| Git integration | Built-in | Built-in (native) | Native GitHub App | Native GitHub | Clone/commit/push/PR via GitPython |
| Cost visibility | $500/mo flat fee | Hidden | Free tier + paid | GitHub Actions minutes | Per-task token/cost breakdown |
| Self-hosted | No (SaaS only) | N/A (runs locally) | No (SaaS) | No (GitHub hosted) | Yes (Docker on any VPS) |
| Late-join replay | Yes (persistent UI) | N/A (local terminal) | N/A (async PRs) | N/A (async runs) | Yes (WebSocket replay buffer) |

**Key competitive insight:** The hybrid autonomy mode is genuinely differentiated. No competitor in this space offers per-task autonomy selection. Devin users complain about tasks going sideways with no intervention point. Claude Code CLI users complain about approving every tool call on routine tasks. This platform sits in the middle -- and that middle ground is exactly what the "supervised autonomy" movement in 2026 advocates for.

## Sources

- [Supervised Autonomy Agents: The AI Framework for 2026](https://edge-case.medium.com/supervised-autonomy-the-ai-framework-everyone-will-be-talking-about-in-2026-fe6c1350ab76) -- MEDIUM confidence, single source but well-argued
- [Human-in-the-Loop for AI Agents: Best Practices](https://www.permit.io/blog/human-in-the-loop-for-ai-agents-best-practices-frameworks-use-cases-and-demo) -- HIGH confidence, comprehensive patterns guide
- [From HITL to HOTL: Evolving AI Agent Autonomy (2026)](https://bytebridge.medium.com/from-human-in-the-loop-to-human-on-the-loop-evolving-ai-agent-autonomy-c0ae62c3bf91) -- MEDIUM confidence
- [StackAI: Approval Workflows for Safe Automation](https://www.stackai.com/insights/human-in-the-loop-ai-agents-how-to-design-approval-workflows-for-safe-and-scalable-automation) -- HIGH confidence, practical implementation guide
- [WebSocket Replay Buffer Patterns](https://javatsc.substack.com/p/day-13-the-replay-buffer-engineering) -- MEDIUM confidence, Discord case study
- [FastAPI WebSocket Connection Management and Reconnection (2025)](https://blog.greeden.me/en/2025/10/28/weaponizing-real-time-websocket-sse-notifications-with-fastapi-connection-management-rooms-reconnection-scale-out-and-observability/) -- HIGH confidence, production patterns
- [Streaming in 2026: SSE vs WebSockets vs RSC](https://jetbi.com/blog/streaming-architecture-2026-beyond-websockets) -- HIGH confidence, current comparison with AI agent context
- [WebSockets vs SSE Comparison](https://websocket.org/comparisons/sse/) -- HIGH confidence, authoritative comparison
- [GitHub Agentic Workflows Technical Preview (2026)](https://github.blog/changelog/2026-02-13-github-agentic-workflows-are-now-in-technical-preview/) -- HIGH confidence, official GitHub blog
- [AI Coding Agents Comparison (2026)](https://devvela.com/blog/ai-coding-agents) -- MEDIUM confidence, market overview
- [asyncio-pause-resume Pattern](https://github.com/m2-farzan/asyncio-pause-resume) -- HIGH confidence, working code example
- [Python asyncio Queue Documentation](https://docs.python.org/3/library/asyncio-queue.html) -- HIGH confidence, official Python docs
- [GitPython Documentation](https://gitpython.readthedocs.io/en/stable/tutorial.html) -- HIGH confidence, official library docs
- [Using asyncio Queues for AI Task Orchestration (2026)](https://dasroot.net/posts/2026/02/using-asyncio-queues-ai-task-orchestration/) -- MEDIUM confidence, recent practical guide
- [Devin AI: Coding With Devin](https://every.to/chain-of-thought/coding-with-devin-my-new-ai-programming-agent) -- MEDIUM confidence, user experience report
- [Top 10 Devin Alternatives (2025)](https://www.codeant.ai/blogs/10-best-alternatives-to-devin-ai-for-developers-in-2025) -- MEDIUM confidence, market landscape

---
*Feature research for: AI agent workflow web platform (v2.0)*
*Researched: 2026-03-12*
