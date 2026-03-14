# Requirements: AI Agent Workflow Console

**Defined:** 2026-03-14
**Core Value:** The orchestrator must reliably coordinate agents through iterative cycles -- taking a rough idea and producing complete, usable code output with zero manual agent management. Tasks persist and stream across devices.

## v2.0 Requirements (Complete)

All v2.0 requirements shipped and verified.

### Dashboard

- [x] **DASH-01**: User can view list of all tasks with status indicators
- [x] **DASH-02**: User can view detailed agent output log for any task
- [x] **DASH-03**: User can create a new task with prompt input and mode selection
- [x] **DASH-04**: User can access tasks from any device via browser

### Streaming

- [x] **STRM-01**: User sees real-time Claude CLI output streamed via WebSocket

### Task Management

- [x] **TASK-01**: User can cancel a running task with subprocess cleanup
- [x] **TASK-02**: User can run up to 2 tasks concurrently
- [x] **TASK-03**: User can choose supervised or autonomous mode per task
- [x] **TASK-04**: User can approve or reject agent actions via approval gate UI

### Infrastructure

- [x] **INFR-01**: Task data persists in PostgreSQL
- [x] **INFR-02**: All endpoints require HTTP Basic Auth
- [x] **INFR-03**: Application deploys as Docker container on Coolify

## v2.1 Requirements (Complete)

All v2.1 requirements shipped and verified.

### Database & Infrastructure

- [x] **DB-01**: Projects table created with id, name, slug, path, description, created_at, last_used_at
- [x] **DB-02**: Tasks table gains nullable project_id FK referencing projects
- [x] **DB-03**: ProjectRepository provides get, list, insert, delete, update_last_used

### Project Management

- [x] **PROJ-01**: User can list all projects (GET /projects) with auto-scan of ~/projects/
- [x] **PROJ-02**: User can create a new project from a template (POST /projects) with folder scaffolding + git init
- [x] **PROJ-03**: User can delete a project record (DELETE /projects/{id}) without removing filesystem
- [x] **PROJ-04**: System auto-registers untracked folders found in ~/projects/ with ON CONFLICT safety
- [x] **PROJ-05**: Project list shows detected stack and last_used_at

### Template System

- [x] **TMPL-01**: 4 builtin templates available: blank, fastapi-pg, telegram-bot, cli-tool
- [x] **TMPL-02**: Each builtin template includes CLAUDE.md, .claude/ agents+commands, and source scaffolding
- [x] **TMPL-03**: User can list templates (GET /templates) from registry.yaml
- [x] **TMPL-04**: User can view template detail with file list (GET /templates/{id})
- [x] **TMPL-05**: User can create custom template with inline files (POST /templates)
- [x] **TMPL-06**: User can update custom template metadata and files (PUT /templates/{id})
- [x] **TMPL-07**: User can delete custom template (DELETE /templates/{id})
- [x] **TMPL-08**: Builtin templates are protected from modification/deletion (403 Forbidden)

### Context Assembly

- [x] **CTX-01**: assemble_full_context() returns workspace + CLAUDE.md (2000 chars) + .planning/ docs (500 chars each) + git log (10 commits) + 5 recent tasks
- [x] **CTX-02**: User can view assembled context (GET /projects/{id}/context)
- [x] **CTX-03**: Phase suggestion engine parses STATE.md/ROADMAP.md to suggest next phase
- [x] **CTX-04**: User can view suggested phase (GET /projects/{id}/suggested-phase)

### Task Integration

- [x] **TASK-11**: TaskCreate accepts optional project_id, falls back to settings.project_path
- [x] **TASK-12**: Task creation prepends assembled project context to prompt
- [x] **TASK-13**: Task creation updates project last_used_at

### Event System

- [x] **EVT-01**: emit_event() no-op placeholder called at project.created, project.deleted, task.started, task.completed, task.failed, phase.suggested

### Frontend SPA

- [x] **SPA-01**: Single index.html replaces all Jinja2 server-rendered pages
- [x] **SPA-02**: Project selection view with list, stack badges, and "New Project" button
- [x] **SPA-03**: Project creation view with name, description, and template picker
- [x] **SPA-04**: Prompt view with phase suggestion, context preview, and prompt textarea
- [x] **SPA-05**: Running view with WebSocket streaming output (reuses existing WS logic)
- [x] **SPA-06**: Alpine.store for cross-view state, x-show for view switching (preserves WebSocket)

## v2.2 Requirements (Complete)

All v2.2 requirements shipped and verified.

### Design System

- [x] **DS-01**: Tailwind CSS replaces Pico CSS as the design framework (CDN, no build step)
- [x] **DS-02**: Clean light theme with consistent color palette, typography, and spacing
- [x] **DS-03**: Reusable component styles (buttons, cards, badges, inputs, modals) via Tailwind utility classes
- [x] **DS-04**: Loading spinners and skeleton states for all async operations
- [x] **DS-05**: Smooth transitions between views (fade/slide)

### Layout & Navigation

- [x] **NAV-01**: Fixed sidebar on the left with navigation links: Projects, Templates, Tasks
- [x] **NAV-02**: Sidebar shows app logo/name at top and collapses to icon-only on tablet
- [x] **NAV-03**: Sidebar collapses to hamburger menu on mobile (phone)
- [x] **NAV-04**: Active page highlighted in sidebar
- [x] **NAV-05**: Main content area fills remaining viewport width

### Responsive Design

- [x] **RES-01**: Desktop layout: fixed sidebar + full content area (>1024px)
- [x] **RES-02**: Tablet layout: collapsed icon sidebar + full content area (768-1024px)
- [x] **RES-03**: Mobile layout: hidden sidebar with hamburger toggle, full-width content (<768px)
- [x] **RES-04**: KPI cards stack vertically on mobile, grid on desktop/tablet
- [x] **RES-05**: Task list and forms are touch-friendly on mobile (min 44px tap targets)

### Project Dashboard

- [x] **PROJ-10**: Project list page shows all projects as cards in a responsive grid
- [x] **PROJ-11**: Each project card shows name, description, stack badges, last activity time
- [x] **PROJ-12**: Clicking a project opens its dashboard with KPI cards and task list
- [x] **PROJ-13**: KPI cards show: total tasks, running, completed, failed counts
- [x] **PROJ-14**: Task list is expandable — clicking a task row reveals full agent output
- [x] **PROJ-15**: Task rows show status badge, prompt preview, timestamp, duration
- [x] **PROJ-16**: "New Task" button prominent in project dashboard header

### Template Management

- [x] **TMPL-10**: Template page shows templates as cards in a grid layout
- [x] **TMPL-11**: Each template card shows name, description, stack info, builtin/custom badge
- [x] **TMPL-12**: Template detail view shows file list and metadata

### Task Flow

- [x] **TASK-20**: Task creation form: project selector, prompt textarea, mode toggle, submit
- [x] **TASK-21**: Running task view: status indicator, live streaming output, cancel button
- [x] **TASK-22**: Approval gate UI: clear action card with approve/reject/continue buttons
- [x] **TASK-23**: Completed task view: final status, full output, "back" and "new task" actions
- [x] **TASK-24**: Global tasks page showing all tasks across projects with filtering by status

## v2.3 Requirements

Requirements for Orchestration Improvements milestone. Each maps to roadmap phases.

### Bug Fixes

- [x] **FIX-01**: All agents (plan, execute, review) receive their system prompt files during web execution via `stream_output()`
- [x] **FIX-02**: Orchestrator decision calls receive `orchestrator_system.txt` via `--system-prompt-file` flag

### File Writing

- [ ] **FWRT-01**: EXECUTE agent output CODE section is parsed to extract code blocks with file paths
- [ ] **FWRT-02**: Extracted files are written to disk under the project's workspace path
- [ ] **FWRT-03**: Directory structure is created automatically when writing files
- [ ] **FWRT-04**: File writer reports the list of written files (used by auto-commit)
- [ ] **FWRT-05**: Zero-file extraction from non-empty CODE section triggers a warning, not silent success
- [ ] **FWRT-06**: Execute system prompt enforces strict code block format with file path annotations

### Context Management

- [x] **CTX-05**: Handoffs are bounded to the last complete cycle (plan+execute+review) with 8000-char cap
- [x] **CTX-06**: First plan handoff is pinned (exempt from windowing) to preserve original context on re-routes
- [ ] **CTX-07**: On re-route from review, execute receives a targeted prompt with extracted ISSUES/IMPROVEMENTS instead of full handoff dump
- [ ] **CTX-08**: Orchestrator routing prompt includes only sections relevant to the last agent (ROUTING_SECTIONS map)

### Pipeline Extension

- [ ] **PIPE-01**: Orchestrator JSON schema enum is generated dynamically from AGENT_REGISTRY
- [ ] **PIPE-02**: Orchestrator system prompt agent list is generated dynamically from registry
- [ ] **PIPE-03**: Allowed routing transitions are validated per agent (invalid transitions fall back to `next_agent`)
- [ ] **PIPE-04**: Test agent exists in registry with static code review system prompt (no subprocess execution)
- [ ] **PIPE-05**: Pipeline flow is plan → execute → [file_write] → test → review

### Autonomy

- [ ] **AUTO-01**: Default execution mode is autonomous (no user confirmations)
- [ ] **AUTO-02**: In autonomous mode, low confidence (< 0.5) logs a warning but never blocks
- [ ] **AUTO-03**: In supervised mode, low confidence (< 0.5) triggers user confirmation
- [ ] **AUTO-04**: Supervised mode remains available as opt-in option

## Future Requirements

Deferred to v2.4+. Tracked but not in current roadmap.

### Webhooks

- **HOOK-01**: emit_event() sends HTTP POST to configured n8n webhook URL
- **HOOK-02**: User can configure webhook URL and enabled events in settings

### GitHub Integration

- **GH-01**: User can clone a GitHub repo as a new project
- **GH-02**: User can push changes and create PRs from the console

### Sandboxed Execution

- **SAND-01**: Test agent can execute pytest/npm test in sandboxed Docker container
- **SAND-02**: File writer uses staging area before committing to workspace

### Advanced Context

- **ACTX-01**: LLM-based handoff summarization for older cycles
- **ACTX-02**: Cross-task review memory via vector store

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multi-user / team features | Single-user with basic auth by design |
| Multi-model support (OpenAI, Gemini) | Claude CLI only |
| React/Vue/Svelte | Alpine.js + Tailwind CSS sufficient for single-user |
| Diff-based file patching | Fragile with LLM output; full rewrites + git provides same recovery |
| Subprocess test execution | Security risk on shared VPS; defer to sandboxed Docker in v2.4 |
| Multi-file atomic writes | Over-engineering; partial writes recoverable via git |
| Agent priority/weight system | Conflicts with AI-driven routing; confidence gating is sufficient |
| Configurable iteration limits | 3-iteration limit is a safety valve; targeted re-routes improve convergence |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

### v2.0 (Complete)

| Requirement | Phase | Status |
|-------------|-------|--------|
| DASH-01 | Phase 10 | Complete |
| DASH-02 | Phase 10 | Complete |
| DASH-03 | Phase 10 | Complete |
| DASH-04 | Phase 10 | Complete |
| STRM-01 | Phase 8 | Complete |
| TASK-01 | Phase 7 | Complete |
| TASK-02 | Phase 7 | Complete |
| TASK-03 | Phase 7 | Complete |
| TASK-04 | Phase 9 | Complete |
| INFR-01 | Phase 6 | Complete |
| INFR-02 | Phase 7 | Complete |
| INFR-03 | Phase 11 | Complete |

### v2.1 (Complete)

| Requirement | Phase | Status |
|-------------|-------|--------|
| DB-01 | Phase 12 | Complete |
| DB-02 | Phase 12 | Complete |
| DB-03 | Phase 12 | Complete |
| TMPL-01 | Phase 13 | Complete |
| TMPL-02 | Phase 13 | Complete |
| TMPL-03 | Phase 13 | Complete |
| TMPL-04 | Phase 13 | Complete |
| TMPL-05 | Phase 13 | Complete |
| TMPL-06 | Phase 13 | Complete |
| TMPL-07 | Phase 13 | Complete |
| TMPL-08 | Phase 13 | Complete |
| CTX-01 | Phase 14 | Complete |
| CTX-02 | Phase 14 | Complete |
| CTX-03 | Phase 14 | Complete |
| CTX-04 | Phase 14 | Complete |
| PROJ-01 | Phase 15 | Complete |
| PROJ-02 | Phase 15 | Complete |
| PROJ-03 | Phase 15 | Complete |
| PROJ-04 | Phase 15 | Complete |
| PROJ-05 | Phase 15 | Complete |
| EVT-01 | Phase 15 | Complete |
| TASK-11 | Phase 16 | Complete |
| TASK-12 | Phase 16 | Complete |
| TASK-13 | Phase 16 | Complete |
| SPA-01 | Phase 17 | Complete |
| SPA-02 | Phase 17 | Complete |
| SPA-03 | Phase 17 | Complete |
| SPA-04 | Phase 17 | Complete |
| SPA-05 | Phase 17 | Complete |
| SPA-06 | Phase 17 | Complete |

### v2.2 (Complete)

| Requirement | Phase | Status |
|-------------|-------|--------|
| DS-01 | Phase 18 | Complete |
| DS-02 | Phase 18 | Complete |
| DS-03 | Phase 18 | Complete |
| DS-04 | Phase 18 | Complete |
| DS-05 | Phase 18 | Complete |
| NAV-01 | Phase 19 | Complete |
| NAV-02 | Phase 19 | Complete |
| NAV-03 | Phase 19 | Complete |
| NAV-04 | Phase 19 | Complete |
| NAV-05 | Phase 19 | Complete |
| RES-01 | Phase 19 | Complete |
| RES-02 | Phase 19 | Complete |
| RES-03 | Phase 19 | Complete |
| RES-04 | Phase 19 | Complete |
| RES-05 | Phase 19 | Complete |
| PROJ-10 | Phase 20 | Complete |
| PROJ-11 | Phase 20 | Complete |
| PROJ-12 | Phase 20 | Complete |
| PROJ-13 | Phase 20 | Complete |
| PROJ-14 | Phase 20 | Complete |
| PROJ-15 | Phase 20 | Complete |
| PROJ-16 | Phase 20 | Complete |
| TMPL-10 | Phase 20 | Complete |
| TMPL-11 | Phase 20 | Complete |
| TMPL-12 | Phase 20 | Complete |
| TASK-20 | Phase 21 | Complete |
| TASK-21 | Phase 21 | Complete |
| TASK-22 | Phase 21 | Complete |
| TASK-23 | Phase 21 | Complete |
| TASK-24 | Phase 21 | Complete |

### v2.3 (Active)

| Requirement | Phase | Status |
|-------------|-------|--------|
| FIX-01 | Phase 22 | Complete |
| FIX-02 | Phase 22 | Complete |
| CTX-05 | Phase 22 | Complete |
| CTX-06 | Phase 22 | Complete |
| FWRT-01 | Phase 23 | Pending |
| FWRT-02 | Phase 23 | Pending |
| FWRT-03 | Phase 23 | Pending |
| FWRT-04 | Phase 23 | Pending |
| FWRT-05 | Phase 23 | Pending |
| FWRT-06 | Phase 23 | Pending |
| CTX-07 | Phase 23 | Pending |
| CTX-08 | Phase 23 | Pending |
| PIPE-01 | Phase 24 | Pending |
| PIPE-02 | Phase 24 | Pending |
| PIPE-03 | Phase 24 | Pending |
| PIPE-04 | Phase 24 | Pending |
| PIPE-05 | Phase 24 | Pending |
| AUTO-01 | Phase 25 | Pending |
| AUTO-02 | Phase 25 | Pending |
| AUTO-03 | Phase 25 | Pending |
| AUTO-04 | Phase 25 | Pending |

**Coverage:**
- v2.3 requirements: 21 total
- Mapped to phases: 21
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-14*
*Last updated: 2026-03-14 after v2.3 requirements definition*
