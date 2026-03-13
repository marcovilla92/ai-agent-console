# Pitfalls Research

**Domain:** Adding Project Router (multi-project, template scaffolding, SPA frontend) to existing FastAPI + Alpine.js web app
**Researched:** 2026-03-13
**Confidence:** HIGH

---

## Critical Pitfalls

### Pitfall 1: Jinja2 Template Rendering with User-Controlled `.j2` Content (SSTI + Path Traversal)

**What goes wrong:**
The template system stores user-created templates as `.j2` files in `templates/{id}/`. When a user calls `POST /templates` they supply file content inline, and when a project is created those files are rendered with `jinja2.Environment.from_string()` or similar. If user-supplied `.j2` content is ever passed to `from_string()` and rendered server-side, it is a Remote Code Execution vector. Separately, when copying template files to the project directory, a malicious filename like `../../.ssh/authorized_keys` or `../CLAUDE.md` in the incoming JSON escapes the project directory.

**Why it happens:**
- `from_string()` executes arbitrary Python via Jinja2's object-introspection chain (`__class__.__mro__[1].__subclasses__()`) even without sandbox
- The `files` dict keys in `POST /templates` are used directly as filesystem paths without normalization
- Developers conflate "Jinja2 for HTML rendering" (safe, predefined templates) with "Jinja2 for user content" (unsafe, arbitrary templates)
- CVE-2025-27516 shows even Jinja2's SandboxedEnvironment has bypasses via the `|attr` filter prior to v3.1.6

**How to avoid:**
1. Never use `from_string()` with user-provided template content. Render only predefined, built-in `.j2` files. Custom template content should be copied verbatim (static, non-rendered) OR rendered in a `SandboxedEnvironment` after upgrading to Jinja2 >= 3.1.6.
2. Canonicalize all file paths before writing: `resolved = (project_path / filename).resolve(); assert resolved.is_relative_to(project_path)`. Reject anything that escapes the target directory.
3. Allowlist filename characters: reject filenames containing `..`, absolute paths (`/` prefix), or null bytes before any filesystem operation.
4. For builtin templates: use `Environment(loader=FileSystemLoader(builtin_templates_dir))` and call `get_template(name)` — Jinja2's FileSystemLoader does normalize paths, but still validate `name` is a simple relative path with no `..` components.

**Warning signs:**
- Any code path calling `jinja2.Environment().from_string(user_input).render(...)`
- Template file paths taken directly from user JSON without `.resolve()` check
- Test that creates a template with `"../../etc/passwd": "content"` — if this creates or overwrites a file outside the project directory, the pitfall is present

**Phase to address:**
Template system phase (creating `src/pipeline/template_service.py` and `/templates` router). Must be addressed before any user-facing template creation endpoint is exposed.

---

### Pitfall 2: DB Migration Breaks on Existing `tasks` Rows (NULL vs NOT NULL on `project_id`)

**What goes wrong:**
The spec adds `ALTER TABLE tasks ADD COLUMN IF NOT EXISTS project_id INTEGER REFERENCES projects(id)`. Existing rows have no project, so `project_id` will be `NULL`. If any subsequent migration, constraint, or application code tries to enforce `NOT NULL` on `project_id` — a Pydantic model that requires it, a query that joins `tasks` to `projects` without `IS NULL` handling, or a future `ALTER TABLE tasks ALTER COLUMN project_id SET NOT NULL` — it crashes immediately (ALTER fails with constraint violation on existing rows) or silently drops legacy tasks (JOIN excludes NULL rows).

**Why it happens:**
- The migration is additive (`IF NOT EXISTS`) but existing data is not backfilled
- `TaskCreate` currently passes `settings.project_path` — adding `project_id` to the Pydantic model without making it `Optional` breaks backwards compatibility
- Adding a new column to the `Task` dataclass without defaulting it to `None` causes `asyncpg.Record`-to-dataclass mapping to fail on existing rows
- `conftest.py`'s `pg_pool` teardown does `DELETE FROM tasks` but after adding `projects`, the FK means `DELETE FROM projects` must come after — otherwise teardown crashes

**How to avoid:**
1. Keep `project_id` permanently `NULLABLE` — tasks without a project are valid ("legacy" tasks before the router existed)
2. Mark `project_id: Optional[int] = None` in the `Task` dataclass and `TaskCreate`/`TaskResponse` Pydantic models
3. Add `project_id` to `TaskRepository.create()` and `TaskRepository.get()` queries explicitly — never rely on column order
4. In `conftest.py`'s `pg_pool` teardown, add `DELETE FROM projects` after `DELETE FROM tasks` (reverse FK order)
5. Run all existing tests immediately after adding the migration SQL to `migrations.py` — they must stay green

**Warning signs:**
- `NOT NULL` appearing anywhere near the `project_id` column in migration SQL
- `TaskCreate` model with a required `project_id` field
- Test failures in `test_task_schema_migration.py` or `test_pg_repository.py` after adding the migration
- `asyncpg.exceptions.NotNullViolationError` on any existing test that inserts a task without a project

**Phase to address:**
DB schema phase (adding `projects` table + `tasks.project_id`). Run the full existing test suite as the phase completion gate before writing any other code.

---

### Pitfall 3: Filesystem Scan Race Condition on `GET /projects` (Scan + Register on Read)

**What goes wrong:**
The spec says `GET /projects` scans `~/projects/` and auto-registers any folder not already in the DB. If two browser tabs or two concurrent API calls hit `GET /projects` simultaneously, both scans see the same unregistered folder and both try to `INSERT INTO projects ... UNIQUE slug`. The second INSERT fails with `UniqueViolationError` (slug and path are UNIQUE), returning a 500 error to the second caller.

**Why it happens:**
- Read-then-write patterns on UNIQUE constraints are not atomic without explicit locking or conflict handling
- The scan is triggered on every `GET /projects` call, maximizing the probability of concurrent collisions
- Single-user app assumption leads developers to skip concurrency analysis for GET endpoints

**How to avoid:**
1. Use `INSERT INTO projects (...) ON CONFLICT (slug) DO NOTHING` — if the slug already exists (from a concurrent insert), silently skip; the subsequent `SELECT` returns the existing row
2. Alternatively: use `INSERT INTO projects (...) ON CONFLICT (path) DO UPDATE SET last_used_at = NOW()` — upsert semantics
3. If simpler, do reconciliation only on explicit user action (`POST /projects/scan`) rather than on every `GET` — avoids the race entirely and keeps `GET /projects` as a pure DB read

**Warning signs:**
- `asyncpg.exceptions.UniqueViolationError` appearing in logs during normal browsing with multiple tabs
- `INSERT INTO projects` inside `GET /projects` without `ON CONFLICT` clause
- No test for concurrent `GET /projects` calls

**Phase to address:**
`ProjectService.list_projects()` implementation. Use `ON CONFLICT DO NOTHING` as the default and document the idempotent design.

---

### Pitfall 4: Git Subprocess Hanging Indefinitely (`git init` / `git commit` on Template Scaffolding)

**What goes wrong:**
`git init` and `git commit --allow-empty -m "Initial commit"` are invoked in `ProjectService.create_new_project()` via `asyncio.create_subprocess_exec`. If `git` is not on PATH inside the Docker container, the subprocess fails with a non-zero exit code that is silently swallowed. If `git commit` requires GPG signing (from a host `~/.gitconfig` mounted into the container), it hangs indefinitely waiting for the GPG agent. The FastAPI request never returns. The `asyncio.create_subprocess_exec` call for `git init` is a fire-and-forget with no timeout, unlike the existing `stream_claude` path which has retry logic.

**Why it happens:**
- The app's Docker image is a Python base image — `git` is not installed by default
- Host `~/.gitconfig` with `gpgsign = true` can bleed into the container if the home directory is volume-mounted
- `asyncio.create_subprocess_exec` without a timeout relies on the subprocess to self-terminate
- A known cpython issue (issue #125502) means `asyncio.run()` can hang with cancelled subprocesses

**How to avoid:**
1. Add `git` to the `Dockerfile` explicitly: `RUN apt-get install -y --no-install-recommends git`
2. Wrap all git subprocess calls with `asyncio.wait_for(..., timeout=30.0)` — kill and raise on timeout
3. Pass `-c commit.gpgsign=false` to the git commit call to prevent GPG hanging
4. Set `GIT_AUTHOR_NAME` and `GIT_AUTHOR_EMAIL` as env vars in the subprocess call — `git commit` needs them in a clean container environment
5. Write a dedicated `async def git_init(path: str) -> None` helper with timeout + error handling; never call git inline

**Warning signs:**
- `git` missing from `Dockerfile` system dependencies
- No `asyncio.wait_for` wrapping git subprocess calls
- `POST /projects` takes > 30 seconds in the Docker container
- `git` process visible in `docker exec <c> ps aux` without completing

**Phase to address:**
`ProjectService.create_new_project()` implementation. Test the entire `POST /projects` flow inside the Docker container, not just locally.

---

### Pitfall 5: Context Size Explosion Breaks Claude CLI Invocation

**What goes wrong:**
`assemble_full_context()` concatenates: workspace listing (up to 200 files), CLAUDE.md (truncated 2000 chars), up to 5 `.planning/` docs (500 chars each), git log (10 commits), and 5 recent tasks. The result is prepended to the user prompt before passing to Claude CLI. The problem is that the existing `assemble_workspace_context` is already called inside `orchestrate_pipeline` at agent invocation time. If the new `assemble_full_context` is also injected at `TaskManager.submit()` time and stored in `tasks.prompt`, both end up in the final Claude CLI invocation. The workspace context appears twice, inflating every prompt by ~2000 characters and doubling cost for context assembly.

**Why it happens:**
- Two separate call sites for context assembly (task creation vs. pipeline agent invocation) are not coordinated
- The existing `assemble_workspace_context` in `src/context/assembler.py` is called inside the pipeline — adding a second call in the router creates duplication
- Developers testing with small toy projects miss the explosion when working on large projects like `ai-agent-console` (200+ files, rich CLAUDE.md)

**How to avoid:**
1. Define a single authoritative call site: inject context at `TaskManager.submit()` time, store in `tasks.prompt`, and remove the redundant `assemble_workspace_context` call from the pipeline agents
2. Add a hard `MAX_CONTEXT_CHARS = 6000` guard in `assemble_full_context()` that truncates the combined output and logs a warning
3. Test `assemble_full_context` on the `ai-agent-console` project itself to verify size stays within bounds
4. When phase context is selected, limit `.planning/` docs to only that phase's directory, not all of `.planning/`

**Warning signs:**
- `tasks.prompt` in the DB exceeding 10000 characters for normal projects
- "=== WORKSPACE CONTEXT ===" appearing twice in agent outputs
- Cost per task increasing 2-3x after adding the context assembler
- `assemble_workspace_context` called in both the `/tasks` router AND inside pipeline agents

**Phase to address:**
Context assembler enhancement phase. Add a size assertion as a required unit test: `assert len(assemble_full_context(...)) <= MAX_CONTEXT_CHARS`.

---

### Pitfall 6: Alpine.js SPA State Stranded Between View Transitions (select → prompt → running)

**What goes wrong:**
The SPA has three states: project-select, prompt-entry, and task-running. These are managed by a `currentView` property in a top-level `x-data` component. If the user submits a task and then uses the browser back button, the browser navigates away from the single HTML page. On return, Alpine re-initializes from scratch, `currentView` resets to `select`, and all in-progress context (selected project, draft prompt) is lost. Separately, if the running task's WebSocket connection is open when the user navigates away and then back, a second WebSocket connection is opened to the same task ID, and the first is never closed — leaking connections and triggering duplicate message delivery.

**Why it happens:**
- Alpine.js has no built-in router or browser history API integration
- `x-data` state is destroyed when the DOM is replaced; there is no persistence layer by default
- WebSocket cleanup on navigation requires explicit `ws.close()` in a `beforeunload` or `pagehide` handler — this is not automatic
- Developers expect Alpine.js to behave like Vue/React with component lifecycle teardown

**How to avoid:**
1. The project-select → prompt → running flow is a three-step wizard on a single page, not three separate browser pages. Never call `window.location.href = ...` between wizard steps; only use it after task creation to navigate to the task view.
2. Store the selected project in `Alpine.store('router', {...})` (global store registered before `Alpine.start()`) rather than local `x-data` — this survives component re-renders within the same page load.
3. Add a `beforeunload` listener in `x-init` that calls `ws.close()` if a WebSocket is open.
4. On the task-running view `x-init`, check `ws && ws.readyState === WebSocket.OPEN` before opening a new connection to avoid duplicates.

**Warning signs:**
- Browser back button from task-running view navigates to a different URL instead of staying on the SPA
- Multiple WebSocket connections visible in browser devtools Network tab for the same task
- `Alpine.store` not used anywhere — all state in isolated `x-data` scopes
- Task prompt text is lost when the user clicks "back" within the wizard

**Phase to address:**
SPA frontend phase. Establish the wizard state model before writing any HTML — document that `currentView` and `selectedProject` live in `Alpine.store`, not in individual component `x-data`.

---

### Pitfall 7: Repurposing `src/templates/` for Project Scaffolding Breaks the Live Server

**What goes wrong:**
The spec notes: "Full SPA replacing Jinja2 server-rendered pages" and "templates/ for project scaffolding — Jinja2 HTML templates removed, directory repurposed." Currently `src/server/routers/views.py` points `Jinja2Templates(directory=str(TEMPLATE_DIR))` at `src/templates/`. If `task_list.html` and `task_detail.html` are deleted before the SPA is fully functional, the server crashes on startup or on first request because `Jinja2Templates` cannot find its files.

**Why it happens:**
- The same `src/templates/` path serves two purposes that need to be migrated in strict sequence
- Developers delete the old HTML files as part of "cleanup" before the replacement is wired up
- The SPA migration and the template scaffolding system overlap in the same phase, creating a window where neither the old nor the new UI works

**How to avoid:**
Do the SPA migration and the directory repurposing as two atomic sub-steps in this exact order:
1. Add new single `index.html` SPA entry point to `src/templates/`
2. Update `views.py` to serve `index.html` statically (removing `Jinja2Templates`)
3. Verify `GET /` returns 200 with Alpine.js present (smoke test)
4. Only then delete old `task_list.html`, `task_detail.html`, `base.html`
5. Only then rename/move `src/templates/` to its new scaffolding role

Never delete step-4 files before step-3 is green.

**Warning signs:**
- `src/templates/` directory contains a mix of Jinja2 HTML (`*.html`) and `.j2` scaffolding files simultaneously
- `views.py` still imports `Jinja2Templates` after the SPA transition is supposed to be complete
- Server startup logs `TemplateNotFound: task_list.html` after any directory changes

**Phase to address:**
SPA frontend phase — must explicitly order the sub-steps and use the smoke test (`GET /` returns 200) as the gate between each step.

---

### Pitfall 8: Breaking Existing Tests by Adding `project_id` to `TaskManager.submit()`

**What goes wrong:**
`TaskManager.submit()` currently has the signature `submit(prompt, mode, project_path)`. Changing this to require `project_id` breaks every caller that currently passes only `project_path`. There are test files (`test_task_manager.py`, `test_server.py`, `test_task_endpoints.py`) that call `submit()` directly or via the `/tasks` API. If `project_id` is added as a required parameter, all those tests fail immediately.

**Why it happens:**
- The v2.0 `create_task` endpoint hardcodes `settings.project_path` — adding `project_id` changes the API contract
- The task-project linking change and the DB migration happen in the same phase, so both changes land on `submit()` at once
- No existing test covers "create task with project_id" before the feature is built — a required parameter would fail on all existing tests

**How to avoid:**
1. Add `project_id: Optional[int] = None` to `TaskManager.submit()` — defaults to None for backwards compatibility
2. Update `TaskCreate` Pydantic model similarly: `project_id: Optional[int] = None`
3. Run `pytest tests/ -x` immediately after any change to the `submit()` signature
4. The new SPA-driven endpoint passes `project_id`; the old API behavior (no project) continues working with `project_id=None`

**Warning signs:**
- `TypeError: submit() missing required argument 'project_id'` in test runs
- Any test in `test_task_manager.py` or `test_task_endpoints.py` fails after adding project support
- `project_id` appears as a required (non-Optional) field in `TaskCreate`

**Phase to address:**
Task-project linking phase — immediately after adding the `project_id` column, update the `submit()` signature before writing any other code.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Store `project_path` in tasks instead of `project_id` FK | No join needed, backwards compatible | Breaks when project is renamed/moved; no referential integrity | Never — the FK is the right model |
| Skip `git init` in scaffolding to avoid subprocess risk | No hang risk | Claude CLI cannot use git tools in new projects; auto-commit phase breaks | Never — git is required for the agent workflow |
| Render ALL `.j2` files with `from_string()` including custom templates | One rendering path, simpler code | RCE if any user-supplied template contains `{{ ''.__class__ }}` | Never |
| Single hardcoded `~/projects` workspace root in `ProjectService` | Matches spec, simpler | Breaks if Docker volume mounts to a different path | Acceptable for v2.1 with env var override documented |
| Skip `ON CONFLICT` in project scan INSERT | Simpler SQL | Silent 500 errors on concurrent requests to `GET /projects` | Never — always use `ON CONFLICT DO NOTHING` for UNIQUE columns |
| Assemble context at API layer inside `create_task` endpoint | No new service layer needed | Context assembled at presentation layer, not testable in isolation; easy to duplicate in pipeline | Only if a standalone unit test for `assemble_full_context` exists |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `asyncpg` + new `projects` table | Forget to add `projects` cleanup to `conftest.py` teardown — FK violation on `DELETE FROM tasks` | Add `DELETE FROM projects` after `DELETE FROM tasks` in reverse FK order in `conftest.py` |
| Jinja2 FileSystemLoader | Using `get_template()` with user-supplied template name containing `../` — some loaders resolve this | Always validate the template name is a basename with no path separators before calling `get_template()` |
| Alpine.js `Alpine.store()` | Registering stores inside `x-data` instead of before `Alpine.start()` — store unavailable to other components | Register all stores in a `<script>` block before Alpine boots: `document.addEventListener('alpine:init', () => Alpine.store('router', {...}))` |
| `git commit` in Docker | `git commit` fails with "Please tell me who you are" — `user.email`/`user.name` not set in container | Pass `-c user.email=agent@localhost -c user.name=Agent` flags to the `git commit` command |
| `migrations.py` FK ordering | `ALTER TABLE tasks ADD COLUMN project_id REFERENCES projects(id)` runs before `projects` table exists — FK reference fails | Create the `projects` table in `PG_SCHEMA_SQL` BEFORE the `ALTER TABLE tasks` migration; order matters |
| `settings.project_path` deprecation | After adding project support, some code paths still read `settings.project_path` as a fallback — silently uses wrong directory | Audit all `settings.project_path` usages after migration; replace with explicit project lookup or keep only as a global default for legacy tasks |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| `rglob("*")` on projects with `node_modules/` or `.venv/` | `GET /projects/{id}/context` takes 2-5 seconds | Verify `EXCLUDE_DIRS` from existing `assemble_workspace_context` is applied in the new `assemble_full_context` path — it is easy to omit when writing the new function | Any project with node_modules (~100k files) |
| Assembling full context on every task creation | Cold-start latency on first task per project | Acceptable for single-user app; add a 30s in-memory cache keyed by `(project_id, mtime_of_CLAUDE.md)` if latency > 500ms | Always noticeable, rarely a blocker |
| `GET /projects` runs filesystem scan on every request | List projects endpoint slow with many projects | Read only from DB on normal `GET /projects`; trigger scan explicitly via query param `?rescan=true` | Noticeably slow at > 20 projects in `~/projects/` |
| Git log via subprocess on every context request | `GET /projects/{id}/context` always forks a process | Cache the last-10-commits in memory with a 60s TTL; invalidate on task completion | Negligible for single-user, but adds ~100ms per call due to subprocess fork |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Rendering user-supplied `.j2` content with `jinja2.Environment().from_string()` | RCE — attacker reads arbitrary files or executes commands via Python object introspection | Only render builtin templates server-side; use `SandboxedEnvironment` + Jinja2 >= 3.1.6 for any user-supplied content |
| Accepting arbitrary file paths in `POST /templates` `files` dict keys | Path traversal — overwrite `~/.ssh/authorized_keys` or app source files | Resolve each path relative to target dir and assert: `(base / key).resolve().is_relative_to(base.resolve())` |
| Scanning `~/projects/` without checking the resolved path is under `WORKSPACE_ROOT` | Symlink attack — a symlink in `~/projects/` pointing to `/etc/` causes `assemble_full_context` to read sensitive files | Resolve project path and assert it starts with `WORKSPACE_ROOT` before any file read |
| Exposing `project.path` (full filesystem path) in API response | Leaks server filesystem layout; minimal risk for single-user app behind Basic Auth | Acceptable for this use case — document the deliberate decision |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Phase suggestion uses rigid keyword matching on STATE.md | Suggestion wrong or absent for projects with non-standard STATE.md format | Use heuristic: scan all phases, find the first without `SUMMARY.md` or with status `!= complete`; return `suggestion: null` gracefully when `.planning/` does not exist |
| Project deletion via `DELETE /projects/{id}` only removes DB row | User confused why the project reappears on next scan | Show explicit UI warning: "Removes from tracking only. Folder stays on disk and will reappear on next scan." |
| Template list includes custom templates manually deleted from disk | `POST /projects` with a deleted custom template fails with cryptic 500 | On `GET /templates`, validate each template's directory exists; mark missing ones as `available: false` in the response |
| No indication that the SPA is loading project context | User clicks a project and sees a blank prompt area while context assembles | Show a loading indicator on the prompt step while `GET /projects/{id}/context` is in flight |

---

## "Looks Done But Isn't" Checklist

- [ ] **Template path traversal guard:** `POST /templates` rejects filenames containing `..` or starting with `/` — verify with test: `{"files": {"../../.ssh/test": "x"}}` returns 400 and creates no file outside the target directory
- [ ] **Legacy tasks still visible:** After adding `project_id` column, `GET /tasks` returns all pre-migration tasks (rows with `project_id = NULL`) — verify with `test_pg_repository.py`
- [ ] **Concurrent scan safety:** Two simultaneous `GET /projects` calls do not produce a 500 error — verify with an integration test using `asyncio.gather(client.get("/projects"), client.get("/projects"))`
- [ ] **Git init in Docker:** `POST /projects` succeeds inside the actual Docker container, not just locally — verify `git` is in the container's PATH after Dockerfile change
- [ ] **WebSocket cleanup:** Opening a task, using browser back to project select, then navigating to the same task again shows no duplicate WebSocket connections — verify in browser devtools Network tab
- [ ] **Old tests still pass:** Running `pytest tests/ -x` after adding `project_id` to the `tasks` schema produces zero failures — verify before writing any other code
- [ ] **Context size guard:** `assemble_full_context` on the `ai-agent-console` project (large codebase) produces output under `MAX_CONTEXT_CHARS` — verify with an explicit size assertion unit test
- [ ] **SPA serves from `/`:** After removing Jinja2 templates, `GET /` returns 200 with Alpine.js script tag present — verify with the existing `test_server.py` smoke test

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| SSTI via user template content | HIGH | Disable `POST /templates` endpoint immediately; audit DB for stored malicious templates; rotate server credentials if exposure suspected; patch with `SandboxedEnvironment` |
| `ALTER TABLE` migration fails on live DB | MEDIUM | The `IF NOT EXISTS` guard means the column was either added or not; check `\d tasks` in psql; if missing, re-run migration manually after verifying FK order |
| Concurrent scan `UniqueViolationError` | LOW | Add `ON CONFLICT DO NOTHING` to INSERT — error is non-destructive (no data lost, just a failed request to one caller) |
| Git subprocess hangs in production | MEDIUM | `docker exec <container> pkill git`; add `asyncio.wait_for` timeout to subprocess call; redeploy |
| Old tests fail after `project_id` addition | LOW | Make `project_id` Optional in Task dataclass and `submit()` signature; re-run tests |
| SPA broken after `src/templates/` repurposed | MEDIUM | `git stash` or revert the directory rename; restore the old Jinja2 HTML files; re-sequence the migration in the correct order |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Jinja2 SSTI / path traversal in user templates | Template system phase | `POST /templates` with `{"files": {"../../.ssh/test": "x"}}` returns 400; no file created outside target dir |
| NULL / NOT NULL on `project_id` migration | DB schema phase | `pytest tests/test_task_schema_migration.py tests/test_pg_repository.py` all pass after migration |
| Concurrent scan UniqueViolationError | ProjectService phase | `asyncio.gather(GET /projects, GET /projects)` — no 500 errors |
| Git subprocess hang | ProjectService / scaffolding phase | `POST /projects` inside Docker container completes in < 10s |
| Context size explosion | Context assembler phase | Unit test: `len(assemble_full_context(ai_agent_console_path, ...)) < MAX_CONTEXT_CHARS` |
| Alpine.js state / WebSocket leak | SPA frontend phase | Manual: wizard flow → back → forward shows no duplicate WS connections in devtools |
| `src/templates/` repurposing breaks server | SPA frontend phase | Smoke test: `GET /` returns 200 after each sub-step of directory migration |
| Breaking existing tests via `submit()` change | Task-project linking phase | `pytest tests/ -x` passes immediately after `submit()` signature change |

---

## Sources

- Codebase analysis: `src/db/pg_schema.py`, `src/db/migrations.py`, `src/server/routers/tasks.py`, `src/server/routers/views.py`, `src/context/assembler.py`, `src/pipeline/project.py`, `tests/conftest.py`
- Design spec: `docs/project-router-spec.md` (808 lines, full API/DB/UX specification)
- [Alpine.js pitfalls discussion — alpinejs/alpine #749](https://github.com/alpinejs/alpine/discussions/749)
- [Alpine.js reactivity and DOM lifecycle issues — MindfulChase](https://www.mindfulchase.com/explore/troubleshooting-tips/front-end-frameworks/fixing-reactivity-and-dom-lifecycle-issues-in-alpine-js-applications.html)
- [asyncio subprocess hang — cpython issue #125502](https://github.com/python/cpython/issues/125502)
- [asyncio Process.communicate() unsafe to cancel — cpython issue #139373](https://github.com/python/cpython/issues/139373)
- [Jinja2 SSTI exploitation — OnSecurity](https://onsecurity.io/article/server-side-template-injection-with-jinja2/)
- [Prevent SSTI — Cobalt docs](https://docs.cobalt.io/bestpractices/prevent-ssti/)
- [CVE-2025-27516 — Jinja2 sandbox bypass via |attr filter](https://www.ibm.com/support/pages/security-bulletin-there-vulnerability-jinja2-315-py3-none-anywhl-used-ibm-maximo-manage-application-ibm-maximo-application-suite-cve-2025-27516)
- [PostgreSQL ALTER TABLE documentation](https://www.postgresql.org/docs/current/sql-altertable.html)
- [Database race conditions — Doyensec blog 2024](https://blog.doyensec.com/2024/07/11/database-race-conditions.html)
- [Alpine.js state management — alpinejs.dev](https://alpinejs.dev/essentials/state)

---
*Pitfalls research for: Project Router milestone — FastAPI + Alpine.js multi-project support*
*Researched: 2026-03-13*
