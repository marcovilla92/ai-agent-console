# Phase 17: SPA Frontend - Research

**Researched:** 2026-03-14
**Domain:** Alpine.js single-page application replacing Jinja2 server-rendered templates
**Confidence:** HIGH

## Summary

Phase 17 replaces the existing Jinja2 server-rendered HTML (3 files: `base.html`, `task_list.html`, `task_detail.html` in `src/templates/`) with a single `static/index.html` Alpine.js SPA. The SPA implements a 4-view wizard flow: project selection, project creation, prompt composition (with phase suggestion + context preview), and running task with WebSocket streaming.

All backend APIs already exist from Phases 12-16: `GET /projects`, `POST /projects`, `GET /templates`, `GET /projects/{id}/context`, `GET /projects/{id}/suggested-phase`, `POST /tasks`, and WebSocket at `/ws/tasks/{task_id}`. The existing frontend already uses Alpine.js 3 and Pico CSS via CDN, and the WebSocket streaming pattern (with token auth, reconnection, approval gates) is fully implemented in `task_detail.html`. This phase is purely frontend work with minor server cleanup.

**Primary recommendation:** Build the entire SPA in a single `static/index.html` file using Alpine.js `x-data` with `Alpine.store()` for shared state, `x-show` (not `x-if`) for view switching to preserve WebSocket connections, and Pico CSS for styling. Serve via FastAPI `StaticFiles` mount. Remove `src/templates/`, `views.py`, and the Jinja2Templates dependency.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SPA-01 | Single index.html replaces all Jinja2 server-rendered pages | StaticFiles mount replaces Jinja2Templates; delete src/templates/ and views.py |
| SPA-02 | Project selection view with list, stack badges, and "New Project" button | GET /projects API exists; render project cards with stack badges and relative time |
| SPA-03 | Project creation view with name, description, and template picker | GET /templates and POST /projects APIs exist; form with template dropdown |
| SPA-04 | Prompt view with phase suggestion, context preview, and prompt textarea | GET /projects/{id}/suggested-phase and /context APIs exist; collapsible context |
| SPA-05 | Running view with WebSocket streaming output reuses existing WS logic | Existing WS pattern from task_detail.html: token auth, chunk/status/approval handling |
| SPA-06 | Alpine.store for cross-view state, x-show for view switching | x-show preserves DOM (and WS connections) unlike x-if which destroys/recreates |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Alpine.js | 3.x (CDN) | Reactive UI framework | Already used in existing templates; lightweight, no build step |
| Pico CSS | 2.x (CDN) | Classless CSS framework | Already used in existing templates; semantic HTML styling |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| FastAPI StaticFiles | (bundled) | Serve static/index.html | Mount at "/" to serve the SPA |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Alpine.js | React/Vue | Massive overkill for 4-view wizard; requires build tooling |
| Single file SPA | Multi-file + Vite | Unnecessary complexity; Alpine.js works inline |
| Pico CSS | Tailwind | Requires build step; Pico gives good defaults with semantic HTML |

**Installation:** No installation needed -- both libraries served via CDN (already in base.html).

## Architecture Patterns

### Recommended Project Structure
```
static/
  index.html          # The entire SPA (HTML + Alpine.js + CSS)
src/server/
  app.py              # Mount StaticFiles, remove view_router
  routers/
    views.py           # DELETE THIS FILE
src/templates/         # DELETE THIS DIRECTORY (base.html, task_list.html, task_detail.html)
```

### Pattern 1: Alpine.store for Global State
**What:** Use `Alpine.store('app', {...})` to share state across views instead of per-component `x-data`
**When to use:** Always -- the SPA needs shared state (current view, selected project, active task, WS connection)
**Example:**
```javascript
document.addEventListener('alpine:init', () => {
  Alpine.store('app', {
    view: 'select',           // 'select' | 'create' | 'prompt' | 'running'
    selectedProject: null,
    projects: [],
    templates: [],
    phaseSuggestion: null,
    context: null,
    activeTaskId: null,
    logText: '',
    approvalPending: false,
    approvalContext: '',
    ws: null,

    async loadProjects() {
      const resp = await fetch('/projects', { credentials: 'same-origin' });
      const data = await resp.json();
      this.projects = data.projects;
    },

    selectProject(project) {
      this.selectedProject = project;
      this.view = 'prompt';
      this.loadSuggestion(project.id);
    },

    switchView(view) {
      this.view = view;
    }
  });
});
```

### Pattern 2: x-show View Switching (Critical Decision)
**What:** Use `x-show` instead of `x-if` for view toggling
**When to use:** Always for the 4 main views -- `x-show` hides elements with `display: none` but keeps them in DOM, preserving WebSocket connections and component state
**Example:**
```html
<div x-show="$store.app.view === 'select'">
  <!-- Project list always in DOM -->
</div>
<div x-show="$store.app.view === 'prompt'">
  <!-- Prompt form always in DOM -->
</div>
<div x-show="$store.app.view === 'running'">
  <!-- WS output always in DOM -- connection preserved when switching views -->
</div>
```

### Pattern 3: WebSocket Token Auth (Reuse Existing)
**What:** Base64-encode credentials for WS auth via query param
**When to use:** When connecting to `/ws/tasks/{task_id}` -- exact same pattern from `task_detail.html`
**Example:**
```javascript
connectWS(taskId) {
  // Reuse credentials from HTTP Basic Auth (browser caches them)
  let token = sessionStorage.getItem('ws_token');
  if (!token) {
    // Fallback: browser already authenticated via Basic Auth
    // Extract from document.cookie or prompt
    const user = prompt('Username:');
    const pass = prompt('Password:');
    token = btoa(user + ':' + pass);
    sessionStorage.setItem('ws_token', token);
  }
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${proto}//${location.host}/ws/tasks/${taskId}?token=${token}`;
  this.ws = new WebSocket(url);
  // ... message handlers
}
```

### Pattern 4: StaticFiles Mount with HTML Fallback
**What:** Serve `static/index.html` as the root page via FastAPI
**When to use:** Replace the Jinja2-based view_router
**Example:**
```python
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

@app.get("/")
async def root():
    return FileResponse("static/index.html")

# If static assets needed later:
# app.mount("/static", StaticFiles(directory="static"), name="static")
```

### Anti-Patterns to Avoid
- **x-if for views:** Destroys DOM elements when hidden, killing WebSocket connections -- use x-show
- **Multiple HTML files with client-side routing:** Adds complexity; a single file with x-show is simpler and matches the wizard flow
- **Storing WS connection in per-component x-data:** Must be in Alpine.store so it survives view switches
- **Fetching context on every view switch:** Cache context in store after first load; only refetch if project changes
- **Removing views.py before static/index.html is serving:** The old and new must coexist briefly during transition

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Relative time display | Custom date formatter | `timeago()` helper (~10 lines) | Simple but easy to get wrong with edge cases |
| CSS component library | Custom button/card styles | Pico CSS semantic HTML | Already in use, zero CSS to write |
| WebSocket reconnection | Custom retry logic | Copy existing pattern from task_detail.html | Tested, handles edge cases |
| Client-side routing | Hash router / history API | x-show view switching | 4 views don't need URL routing |

**Key insight:** The existing `task_detail.html` already implements 80% of the running view (WS connection, chunk handling, approval gates, auto-reconnect). Copy and adapt, don't rewrite.

## Common Pitfalls

### Pitfall 1: Jinja2 Template Conflict
**What goes wrong:** The `templates/` directory is now used by the project template system (blank, fastapi-pg, etc.). The Jinja2 HTML templates are in `src/templates/`. Removing `src/templates/` is safe; the project templates in `templates/` are unrelated.
**Why it happens:** Confusing the two `templates` directories
**How to avoid:** Delete `src/templates/` (Jinja2 HTML) and `src/server/routers/views.py`. The `templates/` root directory (project scaffolding templates) stays.
**Warning signs:** Import errors referencing `Jinja2Templates`

### Pitfall 2: WS Connection Lost on View Switch
**What goes wrong:** Using `x-if` or Alpine component destruction kills the WebSocket
**Why it happens:** `x-if` removes elements from DOM; `x-show` only hides them
**How to avoid:** Use `x-show` exclusively for the 4 main views. Store WS in `Alpine.store('app')`.
**Warning signs:** WS disconnects when navigating away from running view

### Pitfall 3: Static File Serving in Docker
**What goes wrong:** `static/index.html` not found in Docker container
**Why it happens:** Dockerfile doesn't copy `static/` directory
**How to avoid:** Add `COPY static/ ./static/` to Dockerfile (after `COPY templates/`)
**Warning signs:** 404 on production but works locally

### Pitfall 4: HTTP Basic Auth + Fetch Credentials
**What goes wrong:** API calls fail with 401 because credentials not sent
**Why it happens:** `fetch()` doesn't send Basic Auth cookies by default
**How to avoid:** Always include `credentials: 'same-origin'` in fetch options (existing pattern)
**Warning signs:** 401 errors on API calls after page loads fine

### Pitfall 5: Root Route Conflict
**What goes wrong:** Both `view_router` (GET /) and the new static file serve try to handle "/"
**Why it happens:** Not removing view_router before adding static file serve
**How to avoid:** Remove `view_router` inclusion from `app.py` and add the new root route / StaticFiles mount
**Warning signs:** Wrong content served at "/"

### Pitfall 6: Approval Gate UI Missing
**What goes wrong:** The new SPA doesn't include approval UI, breaking supervised mode
**Why it happens:** Focusing only on the 4 new views and forgetting the existing approval pattern
**How to avoid:** Port the approval UI from `task_detail.html` into the running view
**Warning signs:** Supervised tasks hang at approval without UI feedback

## Code Examples

### Complete View State Machine
```javascript
// Views: select -> prompt (existing project) or create (new project)
// create -> select (after creation, project appears in list)
// prompt -> running (after task submission)
// running -> select (after completion, or back button)

document.addEventListener('alpine:init', () => {
  Alpine.store('app', {
    view: 'select',
    selectedProject: null,
    projects: [],
    templates: [],
    phaseSuggestion: null,
    contextData: null,
    showContext: false,
    activeTaskId: null,
    logText: '',
    taskStatus: null,
    approvalPending: false,
    approvalData: null,
    ws: null,

    // --- Project Selection ---
    async loadProjects() {
      const resp = await fetch('/projects', { credentials: 'same-origin' });
      const data = await resp.json();
      this.projects = data.projects;
    },

    selectProject(project) {
      this.selectedProject = project;
      this.view = 'prompt';
      this.loadSuggestion();
    },

    // --- Project Creation ---
    async loadTemplates() {
      const resp = await fetch('/templates', { credentials: 'same-origin' });
      const data = await resp.json();
      this.templates = data.templates;
    },

    async createProject(name, description, template) {
      const resp = await fetch('/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ name, description, template })
      });
      if (resp.ok) {
        await this.loadProjects();
        this.view = 'select';
      }
      return resp;
    },

    // --- Prompt View ---
    async loadSuggestion() {
      if (!this.selectedProject) return;
      const resp = await fetch(
        `/projects/${this.selectedProject.id}/suggested-phase`,
        { credentials: 'same-origin' }
      );
      if (resp.ok) this.phaseSuggestion = await resp.json();
    },

    async loadContext() {
      if (!this.selectedProject) return;
      const resp = await fetch(
        `/projects/${this.selectedProject.id}/context`,
        { credentials: 'same-origin' }
      );
      if (resp.ok) this.contextData = await resp.json();
    },

    async submitTask(prompt, mode) {
      const resp = await fetch('/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
          prompt,
          mode,
          project_id: this.selectedProject?.id || null
        })
      });
      if (resp.ok) {
        const task = await resp.json();
        this.activeTaskId = task.id;
        this.logText = '';
        this.taskStatus = 'running';
        this.view = 'running';
        this.connectWS(task.id);
      }
    },

    // --- Running View (WS) ---
    connectWS(taskId) {
      let token = sessionStorage.getItem('ws_token');
      if (!token) {
        const user = prompt('Username:');
        const pass = prompt('Password:');
        token = btoa(user + ':' + pass);
        sessionStorage.setItem('ws_token', token);
      }
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      this.ws = new WebSocket(
        `${proto}//${location.host}/ws/tasks/${taskId}?token=${token}`
      );

      this.ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'chunk') {
          this.logText += msg.data;
        } else if (msg.type === 'status') {
          this.taskStatus = msg.data;
        } else if (msg.type === 'approval_required') {
          this.approvalPending = true;
          this.approvalData = msg.data;
        }
      };

      this.ws.onclose = () => {
        if (['running', 'queued', 'awaiting_approval'].includes(this.taskStatus)) {
          setTimeout(() => this.connectWS(taskId), 3000);
        }
      };
    },

    async sendApproval(decision) {
      await fetch(`/tasks/${this.activeTaskId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ decision })
      });
      this.approvalPending = false;
    },

    async cancelTask() {
      await fetch(`/tasks/${this.activeTaskId}/cancel`, {
        method: 'POST',
        credentials: 'same-origin'
      });
    },

    backToSelect() {
      if (this.ws) { this.ws.close(); this.ws = null; }
      this.activeTaskId = null;
      this.logText = '';
      this.taskStatus = null;
      this.view = 'select';
      this.loadProjects();
    }
  });
});
```

### Stack Badge Helper
```javascript
// Render stack string as styled badges
// Usage: <template x-for="badge in stackBadges(project.stack)">
//          <span x-text="badge" class="badge"></span>
//        </template>
function stackBadges(stack) {
  if (!stack) return [];
  return stack.split(',').map(s => s.trim()).filter(Boolean);
}
```

### Relative Time Helper
```javascript
function timeAgo(dateStr) {
  if (!dateStr) return 'never';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}
```

### Server-Side Changes (app.py)
```python
# REMOVE these lines:
from src.server.routers.views import view_router
app.include_router(view_router)

# ADD these lines:
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"

@app.get("/", response_class=FileResponse)
async def root():
    return FileResponse(STATIC_DIR / "index.html")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Jinja2 server-side rendering | Alpine.js client-side SPA | Phase 17 | Single file, no server templates |
| Multiple HTML pages with navigation | x-show view switching | Phase 17 | Preserved DOM/WS connections |
| views.py Jinja2Templates router | FileResponse for static HTML | Phase 17 | Simpler serving, no template engine |

**Deprecated/outdated:**
- `src/templates/` directory: Replaced by `static/index.html`
- `src/server/routers/views.py`: No longer needed
- `Jinja2Templates` import in server code: Removable (but jinja2 package stays for project template `.j2` rendering)

## Open Questions

1. **WS Token from HTTP Basic Auth**
   - What we know: Current approach uses `sessionStorage` with manual prompt fallback
   - What's unclear: Can we extract credentials from the browser's Basic Auth cache automatically?
   - Recommendation: Keep the existing `sessionStorage` + prompt pattern -- it works and is proven. The browser prompts for Basic Auth on page load anyway, so the user enters credentials once.

2. **Cancel Button on Running View**
   - What we know: Existing task_detail.html has cancel button
   - What's unclear: Should "Back to Projects" also cancel the running task?
   - Recommendation: Show both "Cancel Task" and "Back to Projects" buttons. "Back" does NOT cancel -- the task continues in background. User can return to running tasks via project selection.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest with httpx (AsyncClient) |
| Config file | pyproject.toml |
| Quick run command | `python -m pytest tests/test_views.py -x` |
| Full suite command | `python -m pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SPA-01 | GET / returns static HTML (not Jinja2) | integration | `python -m pytest tests/test_spa.py::test_root_returns_static_html -x` | Wave 0 |
| SPA-01 | Old view routes removed (no /tasks/{id}/view) | integration | `python -m pytest tests/test_spa.py::test_old_view_routes_removed -x` | Wave 0 |
| SPA-02 | index.html contains project list markup | smoke | `python -m pytest tests/test_spa.py::test_html_contains_project_list -x` | Wave 0 |
| SPA-03 | index.html contains creation form markup | smoke | `python -m pytest tests/test_spa.py::test_html_contains_create_form -x` | Wave 0 |
| SPA-04 | index.html contains prompt view markup | smoke | `python -m pytest tests/test_spa.py::test_html_contains_prompt_view -x` | Wave 0 |
| SPA-05 | index.html contains WS streaming markup | smoke | `python -m pytest tests/test_spa.py::test_html_contains_ws_streaming -x` | Wave 0 |
| SPA-06 | index.html uses x-show not x-if for views | smoke | `python -m pytest tests/test_spa.py::test_uses_xshow_not_xif_for_views -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_spa.py -x`
- **Per wave merge:** `python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_spa.py` -- covers SPA-01 through SPA-06 (smoke + integration tests)
- [ ] Update `tests/test_views.py` -- may need removal or update since views.py is deleted

## Sources

### Primary (HIGH confidence)
- Existing codebase: `src/templates/base.html`, `task_list.html`, `task_detail.html` -- current Alpine.js + Pico CSS patterns
- Existing codebase: `src/server/routers/views.py` -- Jinja2 serving pattern to replace
- Existing codebase: `src/server/routers/ws.py` + `connection_manager.py` -- WebSocket streaming architecture
- Existing codebase: `src/server/routers/projects.py`, `tasks.py`, `templates.py` -- all API endpoints already built

### Secondary (MEDIUM confidence)
- Alpine.js documentation (alpinejs.dev) -- `Alpine.store()`, `x-show`, `x-data` patterns
- Pico CSS documentation (picocss.com) -- semantic HTML component patterns
- Project design spec: `docs/project-router-spec.md` -- UX flow and view specifications

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - already used in project, no new libraries
- Architecture: HIGH - clear requirements, proven patterns from existing code
- Pitfalls: HIGH - identified from actual codebase analysis (Docker, file conflicts, WS preservation)

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (stable -- no external dependencies changing)
