# Requirements: AI Agent Workflow Console

**Defined:** 2026-03-13
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

## v2.1 Requirements

Requirements for Project Router milestone. Each maps to roadmap phases.

### Database & Infrastructure

- [ ] **DB-01**: Projects table created with id, name, slug, path, description, created_at, last_used_at
- [ ] **DB-02**: Tasks table gains nullable project_id FK referencing projects
- [ ] **DB-03**: ProjectRepository provides get, list, insert, delete, update_last_used

### Project Management

- [ ] **PROJ-01**: User can list all projects (GET /projects) with auto-scan of ~/projects/
- [ ] **PROJ-02**: User can create a new project from a template (POST /projects) with folder scaffolding + git init
- [ ] **PROJ-03**: User can delete a project record (DELETE /projects/{id}) without removing filesystem
- [ ] **PROJ-04**: System auto-registers untracked folders found in ~/projects/ with ON CONFLICT safety
- [ ] **PROJ-05**: Project list shows detected stack and last_used_at

### Template System

- [ ] **TMPL-01**: 4 builtin templates available: blank, fastapi-pg, telegram-bot, cli-tool
- [ ] **TMPL-02**: Each builtin template includes CLAUDE.md, .claude/ agents+commands, and source scaffolding
- [ ] **TMPL-03**: User can list templates (GET /templates) from registry.yaml
- [ ] **TMPL-04**: User can view template detail with file list (GET /templates/{id})
- [ ] **TMPL-05**: User can create custom template with inline files (POST /templates)
- [ ] **TMPL-06**: User can update custom template metadata and files (PUT /templates/{id})
- [ ] **TMPL-07**: User can delete custom template (DELETE /templates/{id})
- [ ] **TMPL-08**: Builtin templates are protected from modification/deletion (403 Forbidden)

### Context Assembly

- [ ] **CTX-01**: assemble_full_context() returns workspace + CLAUDE.md (2000 chars) + .planning/ docs (500 chars each) + git log (10 commits) + 5 recent tasks
- [ ] **CTX-02**: User can view assembled context (GET /projects/{id}/context)
- [ ] **CTX-03**: Phase suggestion engine parses STATE.md/ROADMAP.md to suggest next phase
- [ ] **CTX-04**: User can view suggested phase (GET /projects/{id}/suggested-phase)

### Task Integration

- [ ] **TASK-11**: TaskCreate accepts optional project_id, falls back to settings.project_path
- [ ] **TASK-12**: Task creation prepends assembled project context to prompt
- [ ] **TASK-13**: Task creation updates project last_used_at

### Event System

- [ ] **EVT-01**: emit_event() no-op placeholder called at project.created, project.deleted, task.started, task.completed, task.failed, phase.suggested

### Frontend SPA

- [ ] **SPA-01**: Single index.html replaces all Jinja2 server-rendered pages
- [ ] **SPA-02**: Project selection view with list, stack badges, and "New Project" button
- [ ] **SPA-03**: Project creation view with name, description, and template picker
- [ ] **SPA-04**: Prompt view with phase suggestion, context preview, and prompt textarea
- [ ] **SPA-05**: Running view with WebSocket streaming output (reuses existing WS logic)
- [ ] **SPA-06**: Alpine.store for cross-view state, x-show for view switching (preserves WebSocket)

## v2.2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Webhooks

- **HOOK-01**: emit_event() sends HTTP POST to configured n8n webhook URL
- **HOOK-02**: User can configure webhook URL and enabled events in settings

### GitHub Integration

- **GH-01**: User can clone a GitHub repo as a new project
- **GH-02**: User can push changes and create PRs from the console

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multi-user / team features | Single-user with basic auth by design |
| Multi-model support (OpenAI, Gemini) | Claude CLI only |
| Auto-detect project from prompt | Manual selection is explicit and predictable |
| Template sharing/export | Single-user, no need for distribution |
| Real-time filesystem watching | Scan-on-demand is sufficient for single user |
| n8n webhook HTTP implementation | Only hook points in v2.1, full impl in v2.2 |
| Mobile-responsive polish | Desktop-first, functional on mobile but not optimized |

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

### v2.1 (Active)

| Requirement | Phase | Status |
|-------------|-------|--------|
| DB-01 | Phase 12 | Pending |
| DB-02 | Phase 12 | Pending |
| DB-03 | Phase 12 | Pending |
| TMPL-01 | Phase 13 | Pending |
| TMPL-02 | Phase 13 | Pending |
| TMPL-03 | Phase 13 | Pending |
| TMPL-04 | Phase 13 | Pending |
| TMPL-05 | Phase 13 | Pending |
| TMPL-06 | Phase 13 | Pending |
| TMPL-07 | Phase 13 | Pending |
| TMPL-08 | Phase 13 | Pending |
| CTX-01 | Phase 14 | Pending |
| CTX-02 | Phase 14 | Pending |
| CTX-03 | Phase 14 | Pending |
| CTX-04 | Phase 14 | Pending |
| PROJ-01 | Phase 15 | Pending |
| PROJ-02 | Phase 15 | Pending |
| PROJ-03 | Phase 15 | Pending |
| PROJ-04 | Phase 15 | Pending |
| PROJ-05 | Phase 15 | Pending |
| EVT-01 | Phase 15 | Pending |
| TASK-11 | Phase 16 | Pending |
| TASK-12 | Phase 16 | Pending |
| TASK-13 | Phase 16 | Pending |
| SPA-01 | Phase 17 | Pending |
| SPA-02 | Phase 17 | Pending |
| SPA-03 | Phase 17 | Pending |
| SPA-04 | Phase 17 | Pending |
| SPA-05 | Phase 17 | Pending |
| SPA-06 | Phase 17 | Pending |

**Coverage:**
- v2.1 requirements: 30 total
- Mapped to phases: 30/30
- Unmapped: 0

---
*Requirements defined: 2026-03-13*
*Last updated: 2026-03-13 after roadmap creation*
