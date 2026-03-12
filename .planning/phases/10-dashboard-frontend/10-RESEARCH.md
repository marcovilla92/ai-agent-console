# Phase 10: Dashboard Frontend - Research

**Researched:** 2026-03-12
**Domain:** Server-rendered HTML dashboard with Alpine.js interactivity and WebSocket streaming
**Confidence:** HIGH

## Summary

Phase 10 builds the browser-based dashboard for the AI Agent Console. The project has explicitly decided on a no-build-step stack: Jinja2 server-rendered templates, Alpine.js for interactivity, and Pico CSS for styling. All backend APIs already exist (task CRUD, WebSocket streaming, approval gates) -- this phase wires them to HTML views.

The FastAPI application (`src/server/app.py`) already has Jinja2 installed (v3.1.2) and all REST endpoints (`GET /tasks`, `GET /tasks/{id}`, `POST /tasks`, `POST /tasks/{id}/cancel`, `POST /tasks/{id}/approve`) and WebSocket endpoint (`/ws/tasks/{task_id}?token=...`) are fully implemented. The dashboard needs to: (1) add template routes that return HTML, (2) create Jinja2 templates with Alpine.js components, and (3) connect WebSocket for real-time streaming.

**Primary recommendation:** Add a `views` router with 2-3 HTML page routes, a `templates/` directory with Jinja2 base layout + page templates, and serve Pico CSS + Alpine.js from CDN. No npm, no bundler, no static file hosting needed beyond what Starlette provides.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DASH-01 | User can view list of all tasks with status indicators | `GET /tasks` API exists; template renders task list with status badges via Alpine.js `x-data` + `fetch()` |
| DASH-02 | User can view detailed agent output log for any task with step labels | `GET /tasks/{id}` + `agent_outputs` table exist; WebSocket `/ws/tasks/{task_id}` streams chunks; detail template uses WS for live log |
| DASH-03 | User can create a new task with prompt input and mode selection | `POST /tasks` API exists; form with `<textarea>` + `<select>` mode selector, Alpine.js handles submission |
| DASH-04 | User can access tasks from any device via browser | Jinja2 templates served by FastAPI; Pico CSS is responsive by default; HTTP Basic Auth handled by browser native dialog |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Jinja2 | 3.1.2 | Server-side HTML templating | Already installed with FastAPI; Starlette has built-in Jinja2Templates class |
| Alpine.js | 3.x (CDN) | Client-side interactivity | Project decision -- no build step, declarative in HTML attributes |
| Pico CSS | 2.x (CDN) | Classless/minimal CSS framework | Project decision -- semantic HTML styling, no custom CSS needed for basics |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Starlette StaticFiles | (bundled) | Serve any local static assets | Only if custom CSS/JS files are needed beyond CDN |
| FastAPI Jinja2Templates | (bundled) | Template rendering in route handlers | Every HTML page route |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Alpine.js | HTMX | HTMX better for form-heavy apps but Alpine.js better for WebSocket state management |
| Pico CSS | Tailwind/Bootstrap | Both require build step or larger CDN; explicitly out of scope per REQUIREMENTS.md |
| Jinja2 SSR | SPA (React/Vue) | Explicitly excluded in REQUIREMENTS.md Out of Scope table |

**CDN Links (no install needed):**
```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3/dist/cdn.min.js"></script>
```

## Architecture Patterns

### Recommended Project Structure
```
src/
  server/
    app.py              # Add template mount + views router
    routers/
      views.py          # NEW: HTML page routes (task list, task detail)
      tasks.py           # Existing JSON API (unchanged)
      ws.py              # Existing WebSocket (unchanged)
  templates/
    base.html           # Layout: <html>, Pico CSS, Alpine.js CDN, nav
    task_list.html      # Task list page with create form
    task_detail.html    # Task detail with streaming log + approval UI
```

### Pattern 1: FastAPI Jinja2Templates Setup
**What:** Configure Jinja2Templates and create HTML-returning routes
**When to use:** Every page route
**Example:**
```python
# src/server/routers/views.py
from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from src.server.dependencies import verify_credentials

templates = Jinja2Templates(directory="src/templates")

view_router = APIRouter(dependencies=[Depends(verify_credentials)])

@view_router.get("/", response_class=HTMLResponse)
async def task_list_page(request: Request):
    return templates.TemplateResponse(request, "task_list.html")
```
**Source:** https://fastapi.tiangolo.com/advanced/templates/

### Pattern 2: Alpine.js Fetch + Reactive State
**What:** Alpine.js component that fetches JSON API and renders data reactively
**When to use:** Task list, task detail data loading
**Example:**
```html
<div x-data="taskList()" x-init="loadTasks()">
  <template x-for="task in tasks" :key="task.id">
    <article>
      <h3 x-text="task.name"></h3>
      <span x-text="task.status"></span>
    </article>
  </template>
</div>

<script>
function taskList() {
  return {
    tasks: [],
    async loadTasks() {
      const resp = await fetch('/tasks');
      const data = await resp.json();
      this.tasks = data.tasks;
    }
  }
}
</script>
```

### Pattern 3: WebSocket Connection with Alpine.js
**What:** Alpine.js component that opens WebSocket and appends streaming chunks
**When to use:** Task detail page for real-time output
**Example:**
```html
<div x-data="taskStream()" x-init="connect()">
  <pre x-ref="log"></pre>
  <template x-if="approvalPending">
    <div>
      <p x-text="approvalContext"></p>
      <button @click="approve('approve')">Approve</button>
      <button @click="approve('reject')">Reject</button>
    </div>
  </template>
</div>

<script>
function taskStream() {
  return {
    log: '',
    approvalPending: false,
    approvalContext: '',
    connect() {
      const token = btoa('username:password');  // From auth
      const ws = new WebSocket(`ws://${location.host}/ws/tasks/${taskId}?token=${token}`);
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'chunk') {
          this.log += msg.data;
          this.$refs.log.textContent = this.log;
        } else if (msg.type === 'approval_required') {
          this.approvalPending = true;
          this.approvalContext = JSON.stringify(msg.data);
        } else if (msg.type === 'status') {
          // Update status display
        }
      };
    },
    async approve(decision) {
      await fetch(`/tasks/${taskId}/approve`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({decision})
      });
      this.approvalPending = false;
    }
  }
}
</script>
```

### Pattern 4: HTTP Basic Auth Credential Forwarding
**What:** Browser handles Basic Auth natively; credentials auto-sent on all requests
**When to use:** All page loads and fetch() calls
**Important detail:** The browser prompts for credentials on first 401 response and caches them for the session. All subsequent requests (including `fetch()` and WebSocket) can reuse them.
```javascript
// For fetch() calls to API endpoints, credentials are auto-included
// because the browser caches Basic Auth for the same origin
fetch('/tasks', { credentials: 'same-origin' })

// For WebSocket, must pass token explicitly (browsers don't send auth headers on WS)
// The existing base64 token approach handles this
const token = btoa(`${username}:${password}`);
const ws = new WebSocket(`ws://${location.host}/ws/tasks/${taskId}?token=${token}`);
```

### Anti-Patterns to Avoid
- **Building an SPA with client-side routing:** Use server-rendered pages with Alpine.js sprinkles, not a full SPA. Each page is a separate Jinja2 template.
- **Storing auth tokens in JavaScript:** Let the browser handle Basic Auth natively. The only exception is the WebSocket token which must be passed as query param.
- **Polling for updates:** Use the existing WebSocket infrastructure, not `setInterval` with `fetch()`.
- **Custom CSS classes everywhere:** Pico CSS styles semantic HTML elements directly. Use `<article>`, `<table>`, `<nav>`, `<dialog>` -- not `<div class="card">`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CSS styling/layout | Custom CSS framework | Pico CSS v2 CDN | Styles semantic HTML out of the box, responsive by default |
| Client-side reactivity | Manual DOM manipulation | Alpine.js `x-data`/`x-bind`/`x-for` | Declarative, no build step, handles all needed interactivity |
| Template inheritance | Copy-paste HTML headers | Jinja2 `{% extends "base.html" %}` / `{% block %}` | Standard pattern, DRY |
| Status color coding | Manual CSS per status | Pico CSS `role` attribute or custom properties | `<span data-status="running">` with minimal CSS custom properties |
| Auto-scrolling log | Scroll math | `scrollIntoView()` or `scrollTop = scrollHeight` | One-liner in Alpine.js `$watch` or `$nextTick` |

**Key insight:** The entire frontend is ~3 HTML files, ~1 small JS function file, and ~20 lines of custom CSS. Any more complexity is over-engineering for a single-user dashboard.

## Common Pitfalls

### Pitfall 1: WebSocket Auth Token Exposure
**What goes wrong:** Hardcoding credentials in JavaScript or putting them in a visible `<script>` tag
**Why it happens:** WebSocket requires explicit token passing (browsers don't send Basic Auth headers for WS)
**How to avoid:** Pass credentials from the server-rendered template context OR prompt the user once and store in sessionStorage (acceptable for single-user). The base64 token pattern already exists in the codebase.
**Warning signs:** Credentials visible in page source or URL bar

### Pitfall 2: Jinja2 Template Directory Path
**What goes wrong:** `TemplateNotFoundError` because path is relative to working directory, not to the Python file
**Why it happens:** `Jinja2Templates(directory="templates")` resolves relative to CWD, which varies by deployment
**How to avoid:** Use `pathlib.Path(__file__).parent.parent / "templates"` or a well-defined project-relative path
**Warning signs:** Works locally, breaks in Docker

### Pitfall 3: Alpine.js + Jinja2 Delimiter Collision
**What goes wrong:** Jinja2 tries to interpret Alpine.js `{{ }}` expressions
**Why it happens:** Both use double-curly-brace syntax
**How to avoid:** Use Alpine.js `x-text` and `x-bind` directives instead of `{{ }}` template syntax. Or use Jinja2's `{% raw %}` block around Alpine.js sections that need `{{ }}`.
**Warning signs:** Jinja2 `UndefinedError` on template render

### Pitfall 4: WebSocket Reconnection
**What goes wrong:** User navigates away and back, or connection drops, and log stream stops
**Why it happens:** No automatic WebSocket reconnection
**How to avoid:** Add simple reconnection logic with exponential backoff in the Alpine.js component. Also fetch current task state via REST on page load (the detail page should show existing agent_outputs even without WS).
**Warning signs:** Blank log panel after page refresh

### Pitfall 5: CORS / Mixed Content with Reverse Proxy
**What goes wrong:** WebSocket connection fails behind Traefik/nginx
**Why it happens:** `ws://` vs `wss://` mismatch when behind HTTPS proxy, or missing WebSocket upgrade headers
**How to avoid:** Use `location.protocol === 'https:' ? 'wss:' : 'ws:'` for the WebSocket URL. The heartbeat ping (already implemented at 25s) keeps proxy connections alive.
**Warning signs:** WS connects locally but fails in production

## Code Examples

### FastAPI Template Route with Auth
```python
# Source: FastAPI docs + existing project patterns
from pathlib import Path
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.server.dependencies import verify_credentials, get_task_manager
from src.engine.manager import TaskManager

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

view_router = APIRouter(dependencies=[Depends(verify_credentials)])

@view_router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Task list page."""
    return templates.TemplateResponse(request, "task_list.html")

@view_router.get("/tasks/{task_id}/view", response_class=HTMLResponse)
async def task_detail(
    request: Request,
    task_id: int,
    manager: TaskManager = Depends(get_task_manager),
):
    """Task detail page with streaming log."""
    task = await manager.get(task_id)
    return templates.TemplateResponse(
        request, "task_detail.html",
        context={"task": task, "task_id": task_id},
    )
```

### Jinja2 Base Template with Pico CSS + Alpine.js
```html
<!-- src/templates/base.html -->
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}AI Agent Console{% endblock %}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
  <style>
    /* Minimal custom styles for status indicators */
    [data-status="running"] { color: var(--pico-color-cyan-500); }
    [data-status="completed"] { color: var(--pico-color-green-500); }
    [data-status="failed"] { color: var(--pico-color-red-500); }
    [data-status="queued"] { color: var(--pico-color-grey-500); }
    [data-status="awaiting_approval"] { color: var(--pico-color-amber-500); }
    [data-status="cancelled"] { color: var(--pico-color-grey-400); }
    .log-output { max-height: 70vh; overflow-y: auto; font-size: 0.85em; }
  </style>
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3/dist/cdn.min.js"></script>
</head>
<body>
  <nav class="container">
    <ul><li><strong>AI Agent Console</strong></li></ul>
    <ul><li><a href="/">Tasks</a></li></ul>
  </nav>
  <main class="container">
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

### Alpine.js Task Creation Form
```html
<form x-data="{ prompt: '', mode: 'autonomous', submitting: false }"
      @submit.prevent="
        submitting = true;
        fetch('/tasks', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ prompt, mode })
        })
        .then(r => r.json())
        .then(t => { window.location.href = '/tasks/' + t.id + '/view'; })
        .catch(() => { submitting = false; })
      ">
  <textarea x-model="prompt" placeholder="Describe the task..." required></textarea>
  <select x-model="mode">
    <option value="autonomous">Autonomous</option>
    <option value="supervised">Supervised</option>
  </select>
  <button type="submit" :disabled="submitting" :aria-busy="submitting">
    Create Task
  </button>
</form>
```

### WebSocket Message Types (from existing codebase)
```javascript
// Messages received from server (connection_manager.py):
// { "type": "chunk", "data": "text output from agent" }
// { "type": "status", "data": "running|completed|failed|cancelled|awaiting_approval" }
// { "type": "approval_required", "data": { "action": "reroute|halt", "context": {...} } }
// { "type": "ping" }  -- heartbeat, ignore

// Approval is sent via REST (not WS):
// POST /tasks/{id}/approve  { "decision": "approve|reject|continue" }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `templates.TemplateResponse("name.html", {"request": request})` | `templates.TemplateResponse(request, "name.html")` | FastAPI 0.108+ / Starlette 0.29+ | Request is now first positional arg, not in context dict |
| Pico CSS v1 class-based | Pico CSS v2 semantic HTML | 2024 | v2 uses `<article>`, `<nav>`, `<dialog>` directly |
| Alpine.js v2 `x-init` | Alpine.js v3 `x-data` + `x-init` | 2021 | v3 syntax is current; v2 is obsolete |

**Deprecated/outdated:**
- Old Starlette `TemplateResponse` signature: context dict with `"request"` key is deprecated in favor of `request` as first positional arg

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio 0.23+ |
| Config file | pyproject.toml (minimal) |
| Quick run command | `python -m pytest tests/test_server.py -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DASH-01 | GET / returns HTML with task list structure | integration | `python -m pytest tests/test_views.py::test_task_list_page -x` | No -- Wave 0 |
| DASH-02 | GET /tasks/{id}/view returns HTML with log container | integration | `python -m pytest tests/test_views.py::test_task_detail_page -x` | No -- Wave 0 |
| DASH-03 | Task creation form present on list page | integration | `python -m pytest tests/test_views.py::test_create_form_present -x` | No -- Wave 0 |
| DASH-04 | Pages return valid HTML with Pico CSS and Alpine.js CDN links | integration | `python -m pytest tests/test_views.py::test_base_template_includes -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_views.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_views.py` -- covers DASH-01 through DASH-04 (HTML page routes return 200, contain expected elements)
- [ ] `src/templates/` directory -- must exist before templates can render
- [ ] `src/server/routers/views.py` -- new router for HTML pages

## Open Questions

1. **WebSocket credential passing from browser**
   - What we know: WS requires base64 token in query param. Browser caches Basic Auth credentials but won't send them on WS handshake.
   - What's unclear: How to extract cached Basic Auth credentials in JavaScript to construct the WS token.
   - Recommendation: The simplest approach is to encode credentials from the Jinja2 template context (server knows them from the auth dependency) and inject them as a `data-` attribute or hidden field. Alternatively, use `sessionStorage` after first prompt. For a single-user tool, embedding in template context is acceptable.

2. **Agent output log rendering format**
   - What we know: `agent_outputs` table stores `raw_output` text per agent step. WebSocket streams individual chunks in real-time.
   - What's unclear: Whether raw output should be rendered as plain text or parsed (markdown, ANSI codes).
   - Recommendation: Start with `<pre>` for raw text. Sufficient for v2.0. Markdown rendering can be deferred.

## Sources

### Primary (HIGH confidence)
- Project codebase: `src/server/` -- all API endpoints, WebSocket, auth verified by reading source
- Project codebase: `src/db/pg_schema.py`, `src/db/pg_repository.py` -- data model verified
- Project codebase: `src/engine/context.py` -- approval flow and WS message types verified
- FastAPI templates docs: https://fastapi.tiangolo.com/advanced/templates/
- Installed packages: Jinja2 3.1.2, FastAPI 0.135.1, Starlette 0.52.1 (verified via `pip list`)

### Secondary (MEDIUM confidence)
- Pico CSS v2: https://picocss.com/docs -- CDN link and semantic HTML patterns
- Alpine.js v3: https://alpinejs.dev/essentials/installation -- CDN link and API

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries are project decisions locked in REQUIREMENTS.md and already installed
- Architecture: HIGH -- FastAPI Jinja2 pattern is well-documented and the API layer is already built
- Pitfalls: HIGH -- delimiter collision and template path issues are well-known FastAPI/Jinja2 problems

**Research date:** 2026-03-12
**Valid until:** 2026-04-12 (stable stack, no fast-moving dependencies)
