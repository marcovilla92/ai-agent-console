# Roadmap: AI Agent Workflow Console

## Milestones

- ✅ **v1.0 MVP** -- Phases 1-5 (shipped 2026-03-12)
- ✅ **v2.0 Web Platform** -- Phases 6-11 (shipped 2026-03-13)
- 🚧 **v2.1 Project Router** -- Phases 12-17 (in progress)

## Phases

<details>
<summary>v1.0 MVP (Phases 1-5) -- SHIPPED 2026-03-12</summary>

- [x] Phase 1: Foundation (3/3 plans) -- completed 2026-03-12
- [x] Phase 2: Agent Pipeline (4/4 plans) -- completed 2026-03-12
- [x] Phase 3: TUI Shell (4/4 plans) -- completed 2026-03-12
- [x] Phase 4: Orchestrator Intelligence (2/2 plans) -- completed 2026-03-12
- [x] Phase 5: Polish (3/3 plans) -- completed 2026-03-12

Full details: `.planning/milestones/v1.0-ROADMAP.md`

</details>

<details>
<summary>v2.0 Web Platform (Phases 6-11) -- SHIPPED 2026-03-13</summary>

- [x] Phase 6: Database and Server Foundation (2/2 plans) -- completed 2026-03-12
- [x] Phase 7: Task Engine and API (2/2 plans) -- completed 2026-03-12
- [x] Phase 8: WebSocket Streaming (1/1 plans) -- completed 2026-03-12
- [x] Phase 9: Approval Gates (1/1 plans) -- completed 2026-03-12
- [x] Phase 10: Dashboard Frontend (3/3 plans) -- completed 2026-03-13
- [x] Phase 11: Docker Deployment (1/1 plans) -- completed 2026-03-13

</details>

### v2.1 Project Router

- [x] **Phase 12: DB Foundation** - Projects table, tasks.project_id nullable FK, ProjectRepository CRUD (completed 2026-03-13)
- [x] **Phase 13: Template System** - 4 builtin templates, registry.yaml, template CRUD API endpoints (completed 2026-03-13)
- [ ] **Phase 14: Context Assembly** - Full context aggregator, phase suggestion engine, context/phase API endpoints
- [ ] **Phase 15: Project Service and API** - ProjectService with scaffold engine, events stub, project CRUD endpoints with auto-scan
- [ ] **Phase 16: Task-Project Integration** - project_id on task creation, context prepend to prompt, last_used_at update
- [ ] **Phase 17: SPA Frontend** - Alpine.js single-page app replacing Jinja2 templates with 4-state wizard

## Phase Details

### Phase 12: DB Foundation
**Goal**: Projects exist as a database entity and tasks can optionally belong to a project, with all existing tasks and tests unbroken
**Depends on**: Phase 11 (v2.0 complete)
**Requirements**: DB-01, DB-02, DB-03
**Success Criteria** (what must be TRUE):
  1. Projects table exists in PostgreSQL with id, name, slug, path, description, created_at, last_used_at columns
  2. Tasks table has a nullable project_id FK column -- existing tasks with NULL project_id continue to work
  3. ProjectRepository can insert, get, list, delete, and update_last_used for project records
  4. All existing tests pass unchanged (conftest teardown order updated for FK constraint)
**Plans**: 1 plan
Plans:
- [ ] 12-01-PLAN.md -- Schema DDL, Project dataclass, ProjectRepository CRUD, migration wiring, tests

### Phase 13: Template System
**Goal**: Users can browse, inspect, create, update, and delete project templates, with 4 builtin templates ready for scaffolding
**Depends on**: Phase 12
**Requirements**: TMPL-01, TMPL-02, TMPL-03, TMPL-04, TMPL-05, TMPL-06, TMPL-07, TMPL-08
**Success Criteria** (what must be TRUE):
  1. Four builtin templates (blank, fastapi-pg, telegram-bot, cli-tool) exist on disk with CLAUDE.md, .claude/ config, and source scaffolding files
  2. GET /templates returns the full template list from registry.yaml with metadata
  3. GET /templates/{id} returns template detail including file manifest
  4. User can create, update, and delete custom templates via POST/PUT/DELETE /templates endpoints
  5. Builtin templates reject modification and deletion with 403 Forbidden
**Plans**: 2 plans
Plans:
- [ ] 13-01-PLAN.md -- Builtin templates on disk, registry.yaml, GET /templates endpoints, Dockerfile update
- [ ] 13-02-PLAN.md -- Custom template CRUD (POST/PUT/DELETE), builtin protection (403), path traversal safety

### Phase 14: Context Assembly
**Goal**: The system can assemble rich project context from multiple sources and suggest the next development phase
**Depends on**: Phase 12
**Requirements**: CTX-01, CTX-02, CTX-03, CTX-04
**Success Criteria** (what must be TRUE):
  1. assemble_full_context() returns combined output from 5 sources: workspace summary, CLAUDE.md (2000 char limit), .planning/ docs (500 char each), git log (10 commits), and 5 recent tasks
  2. Total assembled context respects MAX_CONTEXT_CHARS cap (6000 chars) to prevent prompt inflation
  3. GET /projects/{id}/context returns the assembled context for a given project
  4. suggest_next_phase() parses STATE.md and ROADMAP.md to identify the current phase and next action
  5. GET /projects/{id}/suggested-phase returns the phase suggestion with name and description
**Plans**: 2 plans
Plans:
- [ ] 14-01-PLAN.md -- Context assembly helpers, assemble_full_context(), suggest_next_phase() with TDD
- [ ] 14-02-PLAN.md -- Projects router (GET context, GET suggested-phase), app wiring, integration tests

### Phase 15: Project Service and API
**Goal**: Users can create projects from templates, list all projects with auto-discovered folders, and delete project records through the API
**Depends on**: Phase 12, Phase 13, Phase 14
**Requirements**: PROJ-01, PROJ-02, PROJ-03, PROJ-04, PROJ-05, EVT-01
**Success Criteria** (what must be TRUE):
  1. GET /projects returns all projects including auto-registered folders from ~/projects/ with detected stack and last_used_at
  2. POST /projects creates a new project from a selected template with folder scaffolding and git init
  3. DELETE /projects/{id} removes the project record from the database without touching the filesystem
  4. Untracked folders in ~/projects/ are auto-registered on list with ON CONFLICT safety (no race condition errors)
  5. emit_event() stub is called at project.created, project.deleted, task.started, task.completed, task.failed, phase.suggested lifecycle points (no-op, no network calls)
**Plans**: 1 plan
Plans:
- [ ] 12-01-PLAN.md -- Schema DDL, Project dataclass, ProjectRepository CRUD, migration wiring, tests

### Phase 16: Task-Project Integration
**Goal**: Task creation accepts a project context that enriches the prompt sent to Claude, linking tasks to projects
**Depends on**: Phase 15
**Requirements**: TASK-11, TASK-12, TASK-13
**Success Criteria** (what must be TRUE):
  1. POST /tasks accepts an optional project_id field -- omitting it still works (backward compatible)
  2. When project_id is provided, assembled project context is prepended to the prompt before Claude receives it
  3. Creating a task with a project_id updates that project's last_used_at timestamp
  4. Existing tasks (project_id = NULL) remain visible and functional in the task list
**Plans**: 1 plan
Plans:
- [ ] 12-01-PLAN.md -- Schema DDL, Project dataclass, ProjectRepository CRUD, migration wiring, tests

### Phase 17: SPA Frontend
**Goal**: Users interact with the console through a single-page Alpine.js app with project selection, creation, prompt composition with phase suggestions, and streaming output
**Depends on**: Phase 16
**Requirements**: SPA-01, SPA-02, SPA-03, SPA-04, SPA-05, SPA-06
**Success Criteria** (what must be TRUE):
  1. A single static/index.html replaces all Jinja2 server-rendered pages -- old HTML templates and views.py are removed
  2. Project selection view shows project list with stack badges, last_used_at, and a "New Project" button
  3. Project creation view lets user enter name, description, and pick a template -- submitting scaffolds the project
  4. Prompt view shows phase suggestion, context preview toggle, and prompt textarea -- submitting creates a task
  5. Running view streams WebSocket output reusing existing WS logic, with x-show view switching preserving the connection
**Plans**: 1 plan
Plans:
- [ ] 12-01-PLAN.md -- Schema DDL, Project dataclass, ProjectRepository CRUD, migration wiring, tests

## Progress

**Execution Order:**
Phases execute in numeric order: 12 -> 13 -> 14 -> 15 -> 16 -> 17

Note: Phases 13 and 14 can execute in parallel (both depend only on Phase 12).

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.0 | 3/3 | Complete | 2026-03-12 |
| 2. Agent Pipeline | v1.0 | 4/4 | Complete | 2026-03-12 |
| 3. TUI Shell | v1.0 | 4/4 | Complete | 2026-03-12 |
| 4. Orchestrator Intelligence | v1.0 | 2/2 | Complete | 2026-03-12 |
| 5. Polish | v1.0 | 3/3 | Complete | 2026-03-12 |
| 6. DB and Server Foundation | v2.0 | 2/2 | Complete | 2026-03-12 |
| 7. Task Engine and API | v2.0 | 2/2 | Complete | 2026-03-12 |
| 8. WebSocket Streaming | v2.0 | 1/1 | Complete | 2026-03-12 |
| 9. Approval Gates | v2.0 | 1/1 | Complete | 2026-03-12 |
| 10. Dashboard Frontend | v2.0 | 3/3 | Complete | 2026-03-13 |
| 11. Docker Deployment | v2.0 | 1/1 | Complete | 2026-03-13 |
| 12. DB Foundation | 1/1 | Complete    | 2026-03-13 | - |
| 13. Template System | 2/2 | Complete    | 2026-03-13 | - |
| 14. Context Assembly | 1/2 | In Progress|  | - |
| 15. Project Service and API | v2.1 | 0/0 | Not started | - |
| 16. Task-Project Integration | v2.1 | 0/0 | Not started | - |
| 17. SPA Frontend | v2.1 | 0/0 | Not started | - |
