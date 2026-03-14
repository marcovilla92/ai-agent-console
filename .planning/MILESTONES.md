# Milestones

## v1.0 MVP (Shipped: 2026-03-12)

**Phases:** 5 | **Plans:** 16 | **Files:** 114 | **LOC:** 4,524 Python (2,176 src + 2,348 tests)
**Timeline:** 2 days (2026-03-11 → 2026-03-12)
**Git range:** 27 feat commits

**Key accomplishments:**
1. SQLite persistence layer with streaming NDJSON parser and retry-resilient Claude CLI runner
2. 3-agent pipeline (Plan/Execute/Review) with structured handoffs and config-driven registry
3. 4-panel Textual TUI with keyboard navigation, dark theme, and real-time streaming output
4. AI-driven orchestrator using Claude CLI with JSON schema for autonomous next-agent decisions
5. Git auto-commit, token/cost tracking, resizable panels, and session history browser

### Known Gaps
- **AGNT-01**: PLAN agent structured output sections not enforced (output contract exists but sections not validated)
- **AGNT-02**: EXECUTE agent structured output sections not enforced
- **AGNT-03**: REVIEW agent structured output sections not enforced

---

## v2.1 Project Router (Shipped: 2026-03-14)

**Phases:** 6 (12-17) | **Plans:** 10 | **Timeline:** 2 days (2026-03-13 → 2026-03-14)

**Key accomplishments:**
1. Projects table with auto-registration of ~/projects/ folders
2. Template system: 4 builtin templates + custom CRUD API
3. Context assembler (workspace + CLAUDE.md + .planning/ + git log + task history)
4. Phase suggestion engine parsing STATE.md/ROADMAP.md
5. Task-project integration with context enrichment
6. Alpine.js SPA replacing Jinja2 server-rendered pages

---

## v2.2 UI Redesign (In Progress)

**Phases:** 4 (18-21) | **Plans:** TBD | **Timeline:** Started 2026-03-14

**Goal:** Complete visual overhaul -- clean light theme, fixed sidebar navigation, KPI dashboard cards, expandable task lists, and modern design system with Tailwind CSS.

**Phase overview:**
1. Phase 18: Design System Foundation -- Tailwind CSS, color palette, component styles, transitions
2. Phase 19: Sidebar Layout & Responsive Shell -- Fixed sidebar, responsive breakpoints, navigation
3. Phase 20: Project & Template Views -- Project dashboard with KPI cards, task list, template grid
4. Phase 21: Task Flow & Polish -- Task creation, running view, approval UI, global tasks page

---
