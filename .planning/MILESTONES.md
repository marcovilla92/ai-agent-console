# Milestones

## v1.0 MVP (Shipped: 2026-03-12)

**Phases:** 5 | **Plans:** 16 | **Files:** 114 | **LOC:** 4,524 Python (2,176 src + 2,348 tests)
**Timeline:** 2 days (2026-03-11 -> 2026-03-12)
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

**Phases:** 6 (12-17) | **Plans:** 10 | **Timeline:** 2 days (2026-03-13 -> 2026-03-14)

**Key accomplishments:**
1. Projects table with auto-registration of ~/projects/ folders
2. Template system: 4 builtin templates + custom CRUD API
3. Context assembler (workspace + CLAUDE.md + .planning/ + git log + task history)
4. Phase suggestion engine parsing STATE.md/ROADMAP.md
5. Task-project integration with context enrichment
6. Alpine.js SPA replacing Jinja2 server-rendered pages

---

## v2.2 UI Redesign (Shipped: 2026-03-14)

**Phases:** 4 (18-21) | **Plans:** 4 | **Timeline:** 1 day (2026-03-14)

**Goal:** Complete visual overhaul -- clean light theme, fixed sidebar navigation, KPI dashboard cards, expandable task lists, and modern design system with Tailwind CSS.

**Key accomplishments:**
1. Tailwind CSS replaces Pico CSS with consistent light theme and component styles
2. Fixed sidebar with responsive breakpoints (desktop/tablet/mobile)
3. Project dashboard with KPI cards and expandable task list
4. Task flow polish with global tasks page, filters, and new task actions

---

## v2.3 Orchestration Improvements (Shipped: 2026-03-14)

**Phases:** 4 (22-25) | **Plans:** 6 | **Timeline:** 1 day (2026-03-14)

**Goal:** Make the agent pipeline produce real output end-to-end -- file writing, smarter re-routing, bounded context, full autonomy by default, and a test agent for code review.

**Key accomplishments:**
1. System prompt fixes for agents and orchestrator
2. Bounded handoff windowing with pinned first plan
3. File writer module with targeted re-route prompts
4. Dynamic schema from registry, routing validation, test agent
5. Autonomous-by-default with confidence-based gating

---

## v2.4 Template System Overhaul (In Progress)

**Phases:** 5 (26-30) | **Plans:** TBD | **Timeline:** Started 2026-03-14

**Goal:** Transform templates from static file scaffolding into live environments that automatically load agents, skills, and plugins -- and enable AI-powered template creation.

**Phase overview:**
1. Phase 26: Agent Loader Foundation -- Discover agents from `.claude/agents/`, parse frontmatter, per-project registry
2. Phase 27: Commands & Settings Loaders -- Discover commands, apply project settings, context injection
3. Phase 28: Orchestrator Dynamic Registry -- Per-task schema building, registry injection, project agent routing
4. Phase 29: AI Template Generation -- Natural language to template via Claude CLI, validation, separate semaphore
5. Phase 30: Template Editor UI -- File tree preview, inline editing, preview-before-save flow

---
