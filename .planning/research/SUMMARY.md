# Project Research Summary

**Project:** AI Agent Console v2.1 — Project Router
**Domain:** AI agent workflow web platform — multi-project management with template scaffolding
**Researched:** 2026-03-13
**Confidence:** HIGH

## Executive Summary

This milestone adds a Project Router to an existing, deployed FastAPI + Alpine.js AI agent console. The v2.0 platform is validated and stable; v2.1 builds on top of it with zero net-new pip dependencies (only making PyYAML explicit) and no architectural rewrites. The correct approach is incremental: extend the existing repository pattern, service injection pattern, and async subprocess pattern from v2.0 rather than introducing new abstractions. The core deliverable is a four-state Alpine.js SPA that replaces server-rendered Jinja2 pages, backed by a `projects` table, a `ProjectService`, and a context assembly pipeline that enriches every Claude prompt with project-specific knowledge (CLAUDE.md, planning docs, git log, task history).

The recommended build sequence is strictly dependency-ordered: DB migration first, then repository layer, then service layer, then API endpoints, then SPA. The phase suggestion engine and template system are differentiators that meaningfully improve the tool beyond v2.0 — they should be included in the core milestone, not deferred. The n8n webhook implementation is correctly deferred to v2.2+; only the no-op placeholder hook points ship in v2.1.

The most significant risks are operational rather than architectural. The `project_id` FK column must be nullable to preserve backward compatibility with existing tasks and tests. The `src/templates/` directory repurposing must follow a strict sub-step order to avoid a window where neither the old nor new UI functions. Git subprocess calls must include a `asyncio.wait_for` timeout and explicit user identity flags to prevent Docker container hangs. Context assembly must enforce a `MAX_CONTEXT_CHARS` cap to prevent prompt inflation from doubling cost on large projects.

---

## Key Findings

### Recommended Stack

The v2.1 stack requires exactly one new explicit dependency: `pyyaml>=6.0` added to `pyproject.toml` (already system-installed, just not declared). All other capabilities use what is already in the codebase. Jinja2 >= 3.1 (already installed) handles `.j2` scaffolding via a separate `Environment(undefined=StrictUndefined, loader=FileSystemLoader(...))` instance — never share the scaffolding environment with the old HTML template environment. Alpine.js CDN tag should be pinned from `@3` (floating) to `@3.15.8` (current stable) for production reliability. The `Alpine.store()` global state pattern is preferred over a root `x-data` god-object because the four-view SPA requires cross-component shared state (selected project, task ID, WebSocket reference).

**Core technologies:**
- PyYAML 6.0.2: `registry.yaml` read/write — safe_load/safe_dump, machine-managed file, no comment preservation needed
- Jinja2 3.1 (existing): `.j2` scaffolding render — separate `Environment(StrictUndefined)`, not reusing the HTML instance
- asyncio.create_subprocess_exec (existing): git init + commit + log — established codebase pattern, no GitPython
- pathlib.Path (stdlib): `~/projects/` filesystem scan — no watchdog, scan on demand
- Alpine.js 3.15.8 + Alpine.store: 4-state SPA — `x-show` for view switching, `x-if` explicitly avoided (kills WebSocket connections on transition)
- asyncpg + PostgreSQL 16 (existing): new `projects` table + `tasks.project_id` nullable FK

### Expected Features

The full feature scope is defined by `docs/project-router-spec.md` (808 lines) and is not inferred — confidence is HIGH. The distinction between P1 (required for milestone completion) and P2 (add after core is stable) is explicit.

**Must have (P1 — table stakes):**
- DB migration: `projects` table + `tasks.project_id` nullable FK — prerequisite for everything
- `ProjectRepository`: CRUD for projects (get, list, insert, delete, update_last_used)
- `GET /projects` with filesystem scan and auto-register — project list with stack detection
- `POST /projects` with blank template — minimum viable project creation
- `DELETE /projects/{id}` — DB-only removal, filesystem untouched
- Enhanced `assemble_full_context()` — CLAUDE.md (2000 chars) + `.planning/` docs (500 chars each) + git log (10 commits) + 5 recent tasks
- `GET /projects/{id}/context` + `GET /projects/{id}/suggested-phase` — context and phase endpoints
- `project_id` on `POST /tasks` (optional with fallback) — wires project to task
- 4 builtin templates with `.claude/` config bundled: blank, fastapi-pg, telegram-bot, cli-tool
- `GET /templates` — template list from registry.yaml
- SPA frontend: all 4 states (select, create, prompt, running) in `static/index.html`
- `emit_event()` no-op placeholder at lifecycle points — n8n prep

**Should have (P2 — add after P1 is stable):**
- Custom template CRUD (`POST/PUT/DELETE /templates`) — user-defined project scaffolding
- Phase-filtered context — narrow context to one phase's docs and relevant commits
- `project_id` made required (not optional) on TaskCreate — cleanup once frontend always sends it

**Defer to v2.2+:**
- n8n webhook HTTP implementation (retry, auth, URL management)
- GitHub integration (clone, PR creation)
- Template sharing/export

**Explicit anti-features (do not build):**
- Auto-detect project from prompt text — ambiguous, error-prone, spec explicitly rejects this
- Client-side routing (history API) — Alpine.js is not a router; 4-view wizard needs none
- Context size auto-tuning — VPS RAM constraint requires hard limits
- Paginatable project list — single-user scale, `scandir` is fast enough

### Architecture Approach

The v2.1 architecture is an additive integration onto v2.0 with a clear component map: 2 new files (ProjectService, events.py), 2 new routers (projects.py, templates.py), 1 new frontend file (static/index.html), modifications to 8 existing files, and deletion of 4 files (3 HTML templates + views.py). The existing patterns are extended, not replaced. `ProjectService` follows the same `app.state` injection pattern as `TaskManager`. `ProjectRepository` follows the same asyncpg class pattern as `TaskRepository`. The SPA serving switches from Jinja2 routes to `StaticFiles` + `FileResponse` on `GET /`. The filesystem (`~/projects/`) is the source of truth for project discovery; the DB is the index.

**Major components:**
1. `ProjectService` (`pipeline/project_service.py`) — create/list/scan/context/delete; owns business logic; injected via `app.state`
2. `ProjectRepository` (`db/pg_repository.py` addition) — all SQL for projects table; same pattern as TaskRepository
3. `assemble_full_context()` (`context/assembler.py` addition) — 5-source async aggregator with hard character limits
4. `suggest_next_phase()` (`context/assembler.py` addition) — markdown heuristic parser for STATE.md + ROADMAP.md + phases dir
5. Template engine (`pipeline/project.py` additions) — Jinja2 FileSystemLoader + shutil for `.j2` + static file scaffolding
6. SPA (`static/index.html`) — Alpine.js 4-state wizard; `x-show` view switching; WebSocket reuse for running view
7. `emit_event()` (`pipeline/events.py`) — no-op stub called at 6 lifecycle points; no network calls in v2.1

**Build order (dependency-correct):**
DB schema → DB repository → template files → context assembler → scaffold functions → events stub → ProjectService → projects + templates routers → tasks.py modification → app.py wiring → SPA → tests

### Critical Pitfalls

1. **DB migration backward compatibility** — `project_id` MUST be nullable. Mark `Optional[int] = None` in both the `Task` dataclass and `TaskCreate` Pydantic model. Update `conftest.py` teardown to `DELETE FROM projects` AFTER `DELETE FROM tasks` (FK order). Run `pytest tests/ -x` immediately after adding the migration — before writing any other code — as the phase gate.

2. **`src/templates/` repurposing breaks the live server** — Follow the exact sub-step order: (1) add `static/index.html` SPA, (2) update `app.py` to serve it, (3) smoke test `GET /` returns 200, (4) only then delete old HTML templates, (5) only then repurpose the directory. Deleting HTML files before the SPA is serving causes `TemplateNotFound` crashes with no fallback.

3. **Git subprocess hangs in Docker** — `git` must be in the Dockerfile (`RUN apt-get install -y --no-install-recommends git`). All git subprocess calls must be wrapped with `asyncio.wait_for(..., timeout=30.0)`. Pass `-c commit.gpgsign=false -c user.name=Agent -c user.email=agent@localhost` to `git commit` to prevent GPG hangs and identity errors in a clean container.

4. **Context size explosion** — Two context assembly call sites (task creation router + existing pipeline agents) cause workspace context to appear twice in every prompt. Define one authoritative call site: inject at `TaskManager.submit()` time; remove the redundant call from pipeline agents. Enforce `MAX_CONTEXT_CHARS = 6000` in `assemble_full_context()` with a unit test assertion.

5. **Jinja2 SSTI in custom templates** — Never call `jinja2.Environment().from_string(user_input)`. Custom template content from `POST /templates` must be stored verbatim or rendered in `SandboxedEnvironment` with Jinja2 >= 3.1.6. Canonicalize all file paths with `.resolve().is_relative_to(base)` before any write to prevent path traversal.

6. **Concurrent scan race on `GET /projects`** — The scan-and-auto-register pattern produces `UniqueViolationError` on simultaneous requests. Use `INSERT INTO projects (...) ON CONFLICT (slug) DO NOTHING` unconditionally — not as an afterthought.

---

## Implications for Roadmap

Based on the combined research, the dependency graph from FEATURES.md and the build order from ARCHITECTURE.md strongly suggest an 8-phase structure:

### Phase 1: DB Foundation
**Rationale:** Every other component depends on `projects` table and `tasks.project_id` FK. This is the unconditional prerequisite — the spec, architecture, and pitfalls research all converge on "DB migration is the absolute first step."
**Delivers:** `projects` table DDL; `ALTER TABLE tasks ADD COLUMN project_id INTEGER REFERENCES projects(id)` (nullable); `Project` dataclass; `ProjectRepository` class with 6 methods; updated `conftest.py` teardown order.
**Addresses:** Project list (requires DB), project_id on tasks (requires DB), all context features (require project lookup)
**Avoids:** Pitfall 2 (NULL/NOT NULL migration) and Pitfall 8 (breaking existing tests) — `pytest tests/ -x` is the phase gate.

### Phase 2: Template Filesystem Setup
**Rationale:** `ProjectService.create_new_project()` reads from `src/templates/` at creation time. Template content must exist before the service layer is built, or the service cannot be tested end-to-end.
**Delivers:** `templates/registry.yaml`; 4 builtin template directories (blank, fastapi-pg, telegram-bot, cli-tool) each with `.j2` files, static files, and `.claude/` agent + command configs; `GET /templates` endpoint (simple YAML read).
**Uses:** PyYAML safe_load/dump; Jinja2 FileSystemLoader pattern
**Avoids:** YAML registry drift — directory is source of truth, registry is the index; `GET /templates` must validate directory exists for each entry.

### Phase 3: Context Assembly
**Rationale:** `ProjectService.get_project_context()` delegates to `assemble_full_context()`. Building this before the service layer allows isolated testing of context assembly and enforces the MAX_CONTEXT_CHARS discipline before any prompt enrichment goes live.
**Delivers:** `assemble_full_context()` async function (5 sources with hard character limits); `suggest_next_phase()` markdown parser; `get_recent_git_log()` async subprocess helper; `get_recent_tasks()` DB query.
**Avoids:** Pitfall 5 (context size explosion) — size assertion unit test is the phase gate; `rglob` on node_modules — apply existing EXCLUDE_DIRS filter from `assemble_workspace_context`.

### Phase 4: ProjectService + Scaffold Engine
**Rationale:** With DB repository (Phase 1), templates (Phase 2), and context assembler (Phase 3) in place, the service layer can be built and fully tested end-to-end. This is the integration keystone.
**Delivers:** `pipeline/project_service.py` (`ProjectService` class); scaffold functions in `pipeline/project.py` (render_template_files, git_init_and_commit, slugify); `pipeline/events.py` (emit_event no-op); `get_project_service()` dependency in `dependencies.py`.
**Avoids:** Pitfall 4 (git subprocess hang) — `asyncio.wait_for` timeout, git identity flags, Dockerfile `git` install verified here.

### Phase 5: Project + Template API Endpoints
**Rationale:** With ProjectService complete, the HTTP layer is straightforward wrapping. Both new routers land together because they share no dependencies on each other and are both needed before the SPA can function.
**Delivers:** `server/routers/projects.py` (5 endpoints: CRUD + context + suggested-phase); `server/routers/templates.py` (GET + P2 custom CRUD); `server/app.py` ProjectService wiring.
**Avoids:** Pitfall 3 (concurrent scan race) — `ON CONFLICT DO NOTHING` in ProjectRepository.create().

### Phase 6: Task-Project Integration
**Rationale:** `project_id` on `POST /tasks` is a breaking change to the existing API contract. It must come after project infrastructure (Phases 1-5) is stable so the FK lookups and context enrichment are reliable when wired into task creation.
**Delivers:** `project_id: Optional[int] = None` on `TaskCreate`; prompt enrichment in `create_task()` (context prepend); `update_last_used()` call after task submit; `TaskManager.submit()` stores project_id on task row.
**Avoids:** Pitfall 8 (breaking existing tests) — Optional[int] = None preserves backward compat; `pytest tests/ -x` as phase gate.

### Phase 7: SPA Frontend
**Rationale:** The SPA depends on all API endpoints (Phases 2-6) existing. Building it last means every `fetch()` call has a real endpoint to hit. The Jinja2 template repurposing must follow the strict sub-step order to avoid a broken-server window.
**Delivers:** `static/index.html` Alpine.js SPA (4 states: select, create, prompt, running); removal of `views.py`; removal of old HTML templates; `StaticFiles` mount + root `FileResponse` in `app.py`.
**Avoids:** Pitfall 7 (templates/ repurposing breaks server) — strict sub-step order with smoke test gate; Pitfall 6 (Alpine.js WebSocket leak) — `Alpine.store` for global state, `beforeunload` WebSocket cleanup.

### Phase 8: Integration Tests + Validation
**Rationale:** End-to-end verification that all phases work together, including failure modes that require Docker container testing and browser devtools inspection.
**Delivers:** Integration tests covering: concurrent `GET /projects` (no race), `POST /projects` inside Docker container, context size assertion on ai-agent-console project (large codebase), legacy tasks visible after migration, SPA smoke test.
**Addresses:** All 8 items from PITFALLS.md "Looks Done But Isn't" checklist.

### Phase Ordering Rationale

- Phases 1-3 establish the data and logic foundations before any service or HTTP code is written — this prevents the circular dependency trap where service code is written before the DB exists.
- Phase 4 (ProjectService) is the integration keystone — it combines all three foundation layers. Building it fourth means it can be properly tested without mocking.
- Phase 5 (API endpoints) before Phase 6 (task integration) because the task handler needs to look up projects via the repository, and those endpoints need to exist before end-to-end task flows can be tested.
- Phase 7 (SPA) last because it has the most external dependencies (all API endpoints) and the most fragile migration step (directory repurposing). Doing it last minimizes the blast radius of the Jinja2 template transition.
- Phase 8 (validation) is a discrete phase, not an afterthought, because the pitfalls research identified 8 specific "looks done but isn't" failure modes requiring deliberate verification steps.

### Research Flags

Phases with well-documented patterns (skip `/gsd:research-phase`):
- **Phase 1 (DB Foundation):** Standard asyncpg repository pattern, idempotent ALTER TABLE — identical to existing TaskRepository; no unknowns.
- **Phase 3 (Context Assembly):** All I/O is stdlib + asyncpg; character limit logic is trivial; existing `assemble_workspace_context()` is the template.
- **Phase 5 (API Endpoints):** FastAPI router wiring follows the existing tasks.py pattern exactly; no new patterns introduced.
- **Phase 6 (Task-Project Integration):** Small model change + FK lookup; patterns established; the pitfall (Optional vs required) is documented and the fix is known.
- **Phase 8 (Validation):** Checklist-driven; no design decisions needed.

Phases that may benefit from targeted research during planning:
- **Phase 2 (Template Filesystem):** The content of the 4 builtin templates — specifically the `.claude/agents/` and `.claude/commands/` files — requires domain judgment about what makes a useful Claude Code agent config for each stack. The file layout is known; the content quality is a craft question that may benefit from reviewing Claude Code's own documentation on sub-agents and slash commands.
- **Phase 4 (ProjectService / Git):** The `asyncio.wait_for` + subprocess timeout pattern has a known cpython issue (#125502 / #139373) for cancelled subprocesses. If the 30s timeout fires in production, cleanup behavior needs verification on the specific Python 3.12 version in use.
- **Phase 7 (SPA Frontend):** The Alpine.js `x-show` + WebSocket + `beforeunload` pattern is documented, but the interaction between `x-show` DOM preservation and WebSocket lifetime under rapid state transitions should be verified empirically during development.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All recommendations based on existing codebase analysis and official docs. Net-new dependency (PyYAML) already system-installed and confirmed. Alpine.js version pinned from release history. Zero speculative recommendations. |
| Features | HIGH | Primary source is the 808-line `docs/project-router-spec.md` — a complete, authoritative design document for this exact project. P1/P2/P3 prioritization is spec-defined, not inferred. |
| Architecture | HIGH | Direct codebase inspection of all modified files. Build order derived from real dependency graph. Integration boundaries verified against actual code signatures in the existing codebase. |
| Pitfalls | HIGH | 8 critical pitfalls with specific error messages, CVE references (CVE-2025-27516), and cpython issue numbers. Prevention strategies are concrete and testable. Phase-to-pitfall mapping is explicit. |

**Overall confidence: HIGH**

### Gaps to Address

- **Template content quality:** The `.claude/agents/` and `.claude/commands/` files inside the 4 builtin templates need to be authored — the architecture defines the file locations, but the actual agent prompts and command instructions require domain knowledge about each stack. This is a content authoring task, not a technical research gap. Address during Phase 2 planning.

- **`project_id` nullable for existing tasks:** The research recommends keeping `project_id` nullable permanently (not just during transition). Existing tasks in the deployed DB will always have `project_id = NULL`. Verify that the `GET /tasks` response shape and any existing frontend code handles a nullable integer field correctly before Phase 6.

- **Python subprocess behavior under cancellation:** The asyncio subprocess cancellation bug (cpython #125502) affects `asyncio.run()` with cancelled subprocesses. Confirm the exact Python version in the Docker container and whether it is affected before git subprocess calls land in production.

- **`settings.project_path` deprecation scope:** PITFALLS.md notes that after adding multi-project support, residual `settings.project_path` usages become incorrect fallbacks. An audit of all call sites is needed before Phase 6 is considered complete. This is not tracked in the spec explicitly.

---

## Sources

### Primary (HIGH confidence)
- `docs/project-router-spec.md` (808 lines) — complete API, DB, and UX specification for v2.1
- Existing codebase: `src/server/app.py`, `src/server/routers/tasks.py`, `src/db/pg_repository.py`, `src/db/pg_schema.py`, `src/db/migrations.py`, `src/context/assembler.py`, `src/pipeline/project.py`, `src/engine/manager.py`, `tests/conftest.py`
- Python asyncio subprocess docs: https://docs.python.org/3/library/asyncio-subprocess.html
- Jinja2 3.1 docs: https://jinja.palletsprojects.com/en/3.1.x/api/ — Environment, FileSystemLoader, StrictUndefined
- Alpine.js store docs: https://alpinejs.dev/essentials/state
- PyYAML 6.0.2 PyPI: https://pypi.org/project/PyYAML/
- PostgreSQL ALTER TABLE docs: https://www.postgresql.org/docs/current/sql-altertable.html

### Secondary (MEDIUM confidence)
- Alpine.js x-show SPA patterns — multiple community sources confirm DOM preservation behavior vs x-if
- PyYAML vs ruamel.yaml comparison — comment preservation tradeoff confirmed across multiple sources
- Alpine.js reactivity and DOM lifecycle issues — MindfulChase blog
- cpython issue #125502 — asyncio subprocess hang on cancellation
- cpython issue #139373 — asyncio Process.communicate() unsafe to cancel
- Alpine.js pitfalls discussion — alpinejs/alpine #749

### Tertiary (LOW confidence — verify during implementation)
- CVE-2025-27516: Jinja2 sandbox bypass via `|attr` filter prior to v3.1.6 — relevant only if custom template rendering uses SandboxedEnvironment; builtin-only rendering with FileSystemLoader is not affected by this CVE
- Database race conditions — Doyensec blog 2024 — concurrent INSERT patterns

---
*Research completed: 2026-03-13*
*Ready for roadmap: yes*
