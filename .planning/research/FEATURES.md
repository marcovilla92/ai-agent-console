# Feature Research

**Domain:** AI agent workflow web platform — v2.1 Project Router milestone
**Researched:** 2026-03-13
**Confidence:** HIGH (spec fully defined in docs/project-router-spec.md; existing codebase inspected; patterns verified)

## Context

This research covers ONLY the new features being added in v2.1 Project Router. The v2.0 features
(task CRUD, WebSocket streaming, approval gates, hybrid autonomy, parallelism, Docker deployment)
are already shipped and validated. The existing codebase provides the following integration points
this milestone builds on:

- `src/pipeline/project.py` — `create_project()` and `sanitize_project_name()` already exist
- `src/context/assembler.py` — `assemble_workspace_context()` already exists (file scan + stack detection)
- `src/server/routers/tasks.py` — `TaskCreate` currently takes only `prompt` + `mode`, no `project_id`
- `src/db/pg_schema.py` — `tasks` table exists, no `project_id` column yet
- `src/server/routers/views.py` — Jinja2 template routes serve current HTML pages (to be replaced)
- `templates/` directory — currently holds Jinja2 HTML templates for server-rendered views

The `templates/` directory is being repurposed from Jinja2 HTML templates to project scaffolding
templates. The SPA approach eliminates server-rendered pages and the Jinja2 template engine role
in views.py, freeing that namespace.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features needed for the Project Router to function at all. Missing any of these makes the milestone
incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Project list with scan and auto-register | Users expect `~/projects/` folders to show up without manual DB entry. This is the entry point to every task. Missing = can't start using the feature. | LOW | `GET /projects` scans filesystem, reconciles with DB. Untracked folders auto-registered with basic metadata. Existing `assemble_workspace_context()` stack detection reused for the `stack` field in the response. |
| Project creation with blank template | The minimum viable "new project" flow: name → folder → git init → DB record. No template complexity. | LOW | `POST /projects` with `template: "blank"`. Reuses existing `create_project()` from `src/pipeline/project.py`. Adds: CLAUDE.md creation, `.planning/README.md`, git init + first commit, DB insert. |
| Project deletion (DB-only, preserve filesystem) | Users need to remove stale DB entries. NOT deleting the actual folder is an explicit safety design decision in the spec. | LOW | `DELETE /projects/{id}` removes DB record only. Filesystem untouched. Return 200 with confirmation. |
| `project_id` required on task creation | Every task must know which project it runs in. Without this, context enrichment is impossible. This is the core contract change of v2.1. | LOW | Add `project_id: int` to `TaskCreate` model. Lookup project in DB, resolve path, assemble context, prepend to prompt. Update `last_used_at` timestamp after submit. |
| Project context assembly | When a project is selected, load its full context so Claude gets oriented before the prompt. No context = v2.0 behavior (no improvement). | MEDIUM | `GET /projects/{id}/context` calls enhanced `assemble_full_context()`: workspace scan (existing) + CLAUDE.md (new, 2000 char limit) + `.planning/` docs (new, 500 char each) + git log (new, last 10 commits) + task history (new, last 5 tasks from DB). All limits are explicit to prevent prompt bloat on VPS-constrained RAM. |
| Template list endpoint | Frontend needs to know what templates are available to populate the "create project" form. | LOW | `GET /templates` reads `templates/registry.yaml` and returns list. Builtin flag distinguishes protected templates from user-created ones. |
| SPA frontend: project select view | The UI must show the project list as the landing state. Current Jinja2 views go away. | MEDIUM | Alpine.js `x-show` view switching pattern (state: `select` / `create` / `prompt` / `running`). `GET /projects` call on load. Project cards with name, stack, last-used timestamp. "+ New Project" button transitions to `create` state. |
| SPA frontend: prompt view with project context | After project selection, user sees phase suggestion + context summary + prompt textarea. This is the primary task-creation UX. | MEDIUM | Transition to `prompt` state. `GET /projects/{id}/suggested-phase` and `GET /projects/{id}/context` fetched on project click. Phase suggestion displayed prominently. Context shown in collapsible section. Submit calls `POST /tasks` with `project_id`. |
| SPA frontend: task running view | The existing streaming view needs to integrate into the SPA flow (currently a separate Jinja2-rendered page). | LOW | Transition to `running` state on task submit. WebSocket connection reuses existing `/ws/{task_id}` endpoint. Output stream rendering already works — port from `task_detail.html` into the SPA. |

### Differentiators (Competitive Advantage)

Features that make this a meaningfully better tool than the v2.0 baseline.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Template system with Claude Code config bundled | Not just file scaffolding — the template includes `.claude/agents/`, `.claude/commands/`, and `CLAUDE.md` so Claude knows how to work with the project from prompt 1. No other scaffold tool does this. Cookiecutter and Yeoman scaffold code; this scaffolds the AI's working knowledge. | MEDIUM | Templates live in `templates/{id}/` with `registry.yaml` index. Files with `.j2` extension rendered via Jinja2 with 5 variables (`name`, `slug`, `description`, `date`, `author`). Static files copied as-is. 4 builtin templates: `blank`, `fastapi-pg`, `telegram-bot`, `cli-tool`. Each includes `.claude/` directory with domain-specific agents and commands. |
| Phase suggestion engine | When you open an existing project, the system reads `.planning/STATE.md` and `ROADMAP.md` and tells you what to work on next. Reduces the mental overhead of "where did I leave off?" after switching between projects. | MEDIUM | `GET /projects/{id}/suggested-phase` parses markdown: (1) look for "Current Phase" heading in STATE.md, (2) look for "Next Phase" in STATE.md, (3) scan ROADMAP.md for first phase not marked COMPLETE, (4) scan `.planning/phases/` for first directory missing `SUMMARY.md`. Returns `{ phase_id, phase_name, status, reason }` plus full phase list. Falls back gracefully when `.planning/` doesn't exist. |
| Phase-filtered context | When a phase is selected, context is narrowed to that phase's planning docs and relevant git commits. Avoids sending an entire project's history to Claude when only one phase's context matters. | MEDIUM | Context filter applied in `assemble_full_context()` when `phase_id` is provided: include `.planning/phases/{phase_id}/` docs, filter git log for commits prefixed with that phase ID, keep general context (CLAUDE.md, workspace) unchanged. |
| Custom template CRUD | Users can define their own templates via API. POST inline file contents, PUT to update, DELETE to remove. Builtin templates are protected (403 on mutation attempts). | MEDIUM | `POST/PUT/DELETE /templates` endpoints. Files stored in `templates/{id}/` on filesystem. Registry updated in `registry.yaml`. Validation: builtin flag prevents mutation of the 4 core templates. File count in response confirms storage. |
| n8n webhook hook points | Infrastructure for future automation without any implementation cost today. The `emit_event()` function is a no-op placeholder but is called at every meaningful lifecycle point. | LOW | `ProjectEvent` enum + `emit_event()` async stub in `src/pipeline/events.py`. Called at: project created, project deleted, task started, task completed, task failed, phase suggested. Config keys `n8n_webhook_url` and `n8n_events_enabled` pre-registered in `Settings` (empty = disabled). Zero runtime impact when unimplemented. |
| SPA frontend: project creation with template picker | A visual template chooser is a significant UX upgrade over raw API calls. Shows template name, description, and whether it's builtin or custom. | LOW | `create` state in Alpine.js. `GET /templates` populates a card grid or radio list. Form: name field + description field + template selection. `POST /projects` on submit. Transition to `prompt` state on success. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem like natural extensions but should be explicitly excluded from v2.1 scope.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Auto-detect project from prompt text | "The system should figure out which project I mean from my prompt" | Ambiguous when prompt could apply to multiple projects. Silent wrong-project selection causes task to run in the wrong codebase. Design spec explicitly chose manual selection for predictability. | Explicit project selection in UI. The project select view is the first step in the flow, not an optional step. |
| Template template variables beyond the 5 defined | "I want `{{ db_name }}`, `{{ port }}`, `{{ author_email }}`" | Turns template creation into a form-builder problem. The 5 variables (`name`, `slug`, `description`, `date`, `author`) are sufficient for all 4 builtin templates and cover the common bootstrapping data. More variables require a variable discovery API and a dynamic form in the frontend. | Use the 5 defined variables. For project-specific config that varies, write it into the CLAUDE.md as instructions ("Replace `your-db-name` with your actual DB name"). |
| Git clone from remote URL in template | "Templates should be fetchable from GitHub" | Network dependency during project creation. GitHub rate limits. Security surface (malicious templates). Binary files in git history. | Store templates on the local filesystem inside the Docker container. Builtin templates ship with the image. Custom templates created via API are stored in the container's `templates/` volume. |
| Context size auto-tuning | "Let Claude decide how much context to include" | Unpredictable RAM usage on a VPS with 7.6GB total RAM and 2 concurrent Claude CLI processes. One oversized context prompt could exhaust memory mid-run. | Hard character limits per source: 2000 for CLAUDE.md, 500 per planning doc, 10 git commits, 5 recent tasks. These are spec-defined constants, not configurable. |
| n8n webhook implementation in v2.1 | "Since we're adding hook points, why not implement them?" | Requires testing against a live n8n instance, webhook URL management, retry logic for failed deliveries, authentication between services. All out of scope per the project spec. | `emit_event()` is a documented no-op. The hook points are the deliverable. Implementation is a separate v2.2+ milestone. |
| Project archiving / soft delete | "Projects shouldn't fully disappear, just be hidden" | Adds a third project state (active / archived / deleted) to the DB, the API, and the UI. The current two-state model (in DB = registered, not in DB = untracked) matches how the filesystem works. | `DELETE /projects/{id}` removes the DB record. The folder still exists on disk. Re-listing via `GET /projects` with the scan-and-register behavior will re-add it automatically if the folder is still there. |
| Client-side routing (history API, hash routing) | "The SPA should have real URLs for each view" | Alpine.js is not a routing framework. History API management (back button behavior, direct URL access) in vanilla Alpine.js requires significant hand-rolled code that is fragile and hard to test. The 4-view flow is linear and sequential, not a general navigation graph. | `x-show` view state machine with `Alpine.store('view', 'select')`. No URL changes. Back navigation implemented as an explicit "Back" button that sets state to the previous view. |
| Paginatable project list | "What if someone has hundreds of projects?" | VPS single-user context: `~/projects/` with hundreds of projects is not a realistic scenario. Adding pagination to the project list API and UI adds complexity that will never be exercised. | Return all projects in one `GET /projects` response. Filesystem scan is fast for single-user scale. If the list grows unwieldy, a search/filter box in Alpine.js is far simpler than API pagination. |

---

## Feature Dependencies

```
[Project DB Table + ProjectRepository]
    |-- required by --> [Project CRUD API]
    |-- required by --> [project_id on TaskCreate]
    |-- required by --> [Context Assembly endpoint]
    |-- required by --> [Phase Suggestion endpoint]

[Template Filesystem + registry.yaml]
    |-- required by --> [GET /templates]
    |-- required by --> [POST /projects (with template)]
    |-- required by --> [Template CRUD API]

[Project CRUD API]
    |-- required by --> [SPA: project select view]
    |-- required by --> [SPA: project create view]
    |-- required by --> [project_id on TaskCreate]

[Enhanced Context Assembler (assemble_full_context)]
    |-- requires --> [Project DB Table] (for recent_tasks lookup)
    |-- requires --> [existing assemble_workspace_context] (already exists)
    |-- required by --> [GET /projects/{id}/context]
    |-- required by --> [project_id on TaskCreate] (context prepended to prompt)

[Phase Suggestion Engine]
    |-- requires --> [Project DB Table] (get project path)
    |-- required by --> [SPA: prompt view] (display suggestion)
    |-- enhances --> [Context Assembly] (phase-filtered context variant)

[project_id on TaskCreate (tasks.py change)]
    |-- requires --> [Project DB Table]
    |-- requires --> [Enhanced Context Assembler]
    |-- requires --> [Project CRUD API] (project must exist before task references it)
    |-- affects --> [existing task tests] (all test task creation must provide project_id)

[SPA frontend (static/index.html)]
    |-- requires --> [Project CRUD API]
    |-- requires --> [Template list endpoint]
    |-- requires --> [Phase Suggestion endpoint]
    |-- requires --> [Context Assembly endpoint]
    |-- requires --> [project_id on TaskCreate]
    |-- requires --> [existing /ws WebSocket endpoint] (already exists)
    |-- replaces --> [src/server/routers/views.py Jinja2 routes]
    |-- replaces --> [templates/task_list.html, templates/task_detail.html]

[n8n event hook points]
    |-- requires --> [Project CRUD API] (project.created, project.deleted hooks)
    |-- requires --> [project_id on TaskCreate] (task.started hook)
    |-- no blocking dependencies on other v2.1 features]

[DB Migration: projects table + tasks.project_id column]
    |-- required by --> [everything DB-related above]
    |-- must run FIRST before any service code uses new schema]
```

### Dependency Notes

- **DB migration is the absolute first step.** The `projects` table and `ALTER TABLE tasks ADD COLUMN project_id` must exist before any service code can run. Existing tests use the tasks table; the migration must be additive and non-breaking (column is nullable or has default so existing tasks don't fail).

- **`templates/` directory naming conflict.** Currently `templates/` holds Jinja2 HTML files (`task_list.html`, `task_detail.html`) rendered by `views.py`. The SPA milestone repurposes this directory for project scaffolding templates. The transition must either (a) move HTML templates to a new location before adding project templates, or (b) add project templates as subdirectories (`templates/blank/`, `templates/fastapi-pg/`) which coexist with HTML files until views.py is replaced. Option (b) is lower risk — subdirectories don't collide with flat `.html` files.

- **`project_id` required vs optional on TaskCreate.** Making it immediately required breaks all existing tests and any client using the current API. The safe migration path: make it optional in the Pydantic model with `None` default, fall back to `settings.project_path` when absent (current behavior), add required validation once the frontend always sends it.

- **SPA replaces views.py but WebSocket endpoint is unchanged.** The existing `/ws/{task_id}` WebSocket endpoint and `ConnectionManager` are unchanged. The SPA just connects to the same endpoint. No changes to streaming infrastructure.

- **Phase suggestion requires `.planning/` docs to exist.** Projects created with `blank` template only have `.planning/README.md` — no STATE.md or ROADMAP.md. Phase suggestion must fail gracefully and return `null` suggestion rather than 500 errors.

---

## MVP Definition

### Launch With (v2.1 core)

The minimum scope that delivers multi-project support end-to-end.

- [ ] DB migration: `projects` table + `tasks.project_id` nullable FK — without this nothing works
- [ ] `ProjectRepository` (get, list, insert, delete, update_last_used) — DB layer
- [ ] `GET /projects` with filesystem scan and auto-register — project list
- [ ] `POST /projects` with `blank` template only — project creation minimum viable
- [ ] `DELETE /projects/{id}` — project removal
- [ ] Enhanced `assemble_full_context()` — CLAUDE.md + planning docs + git log + task history
- [ ] `GET /projects/{id}/context` — context endpoint
- [ ] `GET /projects/{id}/suggested-phase` — phase parsing
- [ ] `project_id` on `POST /tasks` (optional with fallback) — wires project to task
- [ ] 4 builtin templates with `.claude/` config bundled — `blank`, `fastapi-pg`, `telegram-bot`, `cli-tool`
- [ ] `GET /templates` — template list
- [ ] SPA frontend: all 4 states (`select`, `create`, `prompt`, `running`) in `static/index.html`
- [ ] `emit_event()` no-op placeholder at correct lifecycle points — n8n prep

### Add After Core Works (v2.1 enhanced)

- [ ] `POST /templates` custom template creation — add once builtin templates are validated
- [ ] `PUT /templates/{id}` custom template update — add alongside POST
- [ ] `DELETE /templates/{id}` custom template removal — add alongside PUT/POST
- [ ] Phase-filtered context (filter context by selected phase) — add after basic context works
- [ ] `project_id` made required on TaskCreate (after frontend always sends it) — cleanup

### Defer to v2.2+

- [ ] n8n webhook actual implementation (HTTP calls, retry, auth) — separate milestone
- [ ] GitHub integration (clone, PR creation) — was already deferred from v2.0
- [ ] Template sharing / export — only useful with multiple users or teams

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| DB migration (projects + project_id) | HIGH | LOW | P1 |
| ProjectRepository | HIGH | LOW | P1 |
| GET /projects (scan + list) | HIGH | LOW | P1 |
| POST /projects (blank template) | HIGH | LOW | P1 |
| Enhanced assemble_full_context() | HIGH | MEDIUM | P1 |
| GET /projects/{id}/context | HIGH | LOW | P1 |
| GET /projects/{id}/suggested-phase | HIGH | MEDIUM | P1 |
| project_id on POST /tasks | HIGH | LOW | P1 |
| 4 builtin templates with .claude/ config | HIGH | MEDIUM | P1 |
| GET /templates | HIGH | LOW | P1 |
| SPA frontend (4 states) | HIGH | HIGH | P1 |
| emit_event() placeholder | LOW | LOW | P1 |
| DELETE /projects/{id} | MEDIUM | LOW | P1 |
| POST /templates (custom) | MEDIUM | MEDIUM | P2 |
| PUT /templates/{id} | MEDIUM | LOW | P2 |
| DELETE /templates/{id} | MEDIUM | LOW | P2 |
| Phase-filtered context | MEDIUM | MEDIUM | P2 |
| project_id required (not optional) | LOW | LOW | P2 |
| n8n webhook implementation | LOW | HIGH | P3 |

**Priority key:**
- P1: Required for v2.1 milestone completion
- P2: Enhances v2.1, add in same milestone after P1 is stable
- P3: Explicitly out of scope for v2.1

---

## How Each Feature Relates to Existing Code

| New Feature | Extends | Replaces | New File |
|------------|---------|----------|----------|
| Project DB table | `src/db/pg_schema.py` | — | — |
| ProjectRepository | `src/db/pg_repository.py` | — | — |
| DB migration | `src/db/migrations.py` | — | — |
| assemble_full_context() | `src/context/assembler.py` | — | — |
| suggest_next_phase() | `src/context/assembler.py` | — | — |
| create_new_project() with template | `src/pipeline/project.py` | — | `src/pipeline/project_service.py` |
| ProjectService | — | — | `src/pipeline/project_service.py` |
| emit_event() / ProjectEvent | — | — | `src/pipeline/events.py` |
| /projects router | — | — | `src/server/routers/projects.py` |
| /templates router | — | — | `src/server/routers/templates.py` |
| project_id on TaskCreate | `src/server/routers/tasks.py` | — | — |
| app.py wiring | `src/server/app.py` | — | — |
| n8n config keys | `src/server/config.py` | — | — |
| get_project_service() dep | `src/server/dependencies.py` | — | — |
| Template registry | — | — | `templates/registry.yaml` |
| Builtin templates | — | `templates/task_list.html` etc. | `templates/blank/`, `templates/fastapi-pg/`, etc. |
| SPA index.html | — | `src/server/routers/views.py` (Jinja2 routes) | `static/index.html` |

---

## Complexity Assessment by Feature Area

| Area | Complexity | Reason |
|------|------------|--------|
| DB schema + migration | LOW | Additive changes to existing schema. Single new table, one ALTER. |
| ProjectRepository | LOW | Standard asyncpg CRUD, same patterns as existing AgentOutputRepository. |
| assemble_full_context() | MEDIUM | 5 sources to aggregate, each with their own I/O (filesystem, subprocess for git, DB query). Character limits add truncation logic. |
| suggest_next_phase() | MEDIUM | Parsing markdown without a schema is inherently fragile. Multiple fallback strategies needed for graceful degradation (STATE.md absent, no phases directory, no ROADMAP.md). |
| Template engine (builtin) | MEDIUM | Jinja2 rendering is well-understood. The complexity is authoring the 4 template contents with `.claude/` agent and command files that are actually useful. |
| Template CRUD API | MEDIUM | File I/O for creating/updating template directories + YAML mutation for registry. Error handling for invalid file paths and registry corruption. |
| project_id wiring into tasks | LOW | Small model change and a few lines in the handler. The complexity is in migration compatibility (existing tasks have no project_id). |
| SPA frontend (Alpine.js) | HIGH | 4 distinct views with state transitions, 6+ API calls, WebSocket integration, and no build step. Alpine.js `x-show` + `Alpine.store` handles multi-view cleanly but requires careful state management. The `running` view re-implements existing streaming output UI in the new SPA context. |
| n8n hook points (no-op) | LOW | A stub function and enum definition. No network calls. |

---

## Sources

- `docs/project-router-spec.md` (808 lines) — primary spec, HIGH confidence, authoritative for this project
- `src/pipeline/project.py` — existing scaffolding primitives (create_project, sanitize_project_name)
- `src/context/assembler.py` — existing context assembly (assemble_workspace_context)
- `src/server/routers/tasks.py` — existing TaskCreate model (project_id integration point)
- `src/db/pg_schema.py` — existing DB schema (tasks table to be extended)
- Alpine.js x-show tab/view patterns — MEDIUM confidence (multiple sources confirm, pattern is idiomatic)
- Jinja2 FileSystemLoader + Environment rendering — HIGH confidence (official Jinja2 docs pattern)
- FastAPI StaticFiles mount for SPA serving — HIGH confidence (FastAPI official docs pattern)

---
*Feature research for: AI agent workflow web platform — v2.1 Project Router*
*Researched: 2026-03-13*
