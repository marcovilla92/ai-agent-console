# Roadmap: AI Agent Workflow Console

## Milestones

- ✅ **v1.0 MVP** -- Phases 1-5 (shipped 2026-03-12)
- ✅ **v2.0 Web Platform** -- Phases 6-11 (shipped 2026-03-13)
- ✅ **v2.1 Project Router** -- Phases 12-17 (shipped 2026-03-14)
- 🚧 **v2.2 UI Redesign** -- Phases 18-21 (in progress)

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

<details>
<summary>v2.1 Project Router (Phases 12-17) -- SHIPPED 2026-03-14</summary>

- [x] Phase 12: DB Foundation (1/1 plans) -- completed 2026-03-13
- [x] Phase 13: Template System (2/2 plans) -- completed 2026-03-13
- [x] Phase 14: Context Assembly (2/2 plans) -- completed 2026-03-13
- [x] Phase 15: Project Service and API (2/2 plans) -- completed 2026-03-14
- [x] Phase 16: Task-Project Integration (1/1 plans) -- completed 2026-03-14
- [x] Phase 17: SPA Frontend (2/2 plans) -- completed 2026-03-14

</details>

### v2.2 UI Redesign

- [ ] **Phase 18: Design System Foundation** - Tailwind CSS setup, color palette, component styles, transitions
- [ ] **Phase 19: Sidebar Layout & Responsive Shell** - Fixed sidebar, responsive breakpoints, navigation
- [ ] **Phase 20: Project & Template Views** - Project dashboard with KPI cards, task list, template grid
- [ ] **Phase 21: Task Flow & Polish** - Task creation, running view, approval UI, global tasks page

## Phase Details

### Phase 18: Design System Foundation
**Goal**: The application has a consistent visual language -- Tailwind CSS replaces Pico CSS with a clean light theme, reusable component styles, and polished loading/transition states
**Depends on**: Phase 17 (v2.1 complete)
**Requirements**: DS-01, DS-02, DS-03, DS-04, DS-05
**Success Criteria** (what must be TRUE):
  1. Pico CSS is removed and Tailwind CSS (CDN) is the sole styling framework -- all existing UI elements render correctly
  2. The application uses a consistent light color palette with uniform typography and spacing across all views
  3. Buttons, cards, badges, inputs, and modals follow reusable Tailwind utility patterns that look visually cohesive
  4. Every async operation (API calls, page loads) shows a loading spinner or skeleton placeholder instead of blank space
  5. View transitions use fade or slide animations -- switching between views feels smooth, not jarring
**Plans**: 1 plan
Plans:
- [ ] 18-01-PLAN.md -- Replace Pico with Tailwind, design system, loading states, transitions

### Phase 19: Sidebar Layout & Responsive Shell
**Goal**: Users navigate the application through a persistent sidebar that adapts gracefully across desktop, tablet, and mobile screen sizes
**Depends on**: Phase 18
**Requirements**: NAV-01, NAV-02, NAV-03, NAV-04, NAV-05, RES-01, RES-02, RES-03, RES-04, RES-05
**Success Criteria** (what must be TRUE):
  1. A fixed sidebar on the left shows navigation links (Projects, Templates, Tasks) with the app name/logo at top -- it persists across all views
  2. Active page is visually highlighted in the sidebar so users always know where they are
  3. On desktop (>1024px), the sidebar is fully expanded with labels; on tablet (768-1024px), it collapses to icon-only; on mobile (<768px), it hides behind a hamburger toggle
  4. Main content fills the remaining viewport width without horizontal scrolling at any breakpoint
  5. All interactive elements (buttons, list items, nav links) have at least 44px tap targets on mobile for touch-friendliness
**Plans**: TBD

### Phase 20: Project & Template Views
**Goal**: Users can browse projects and templates in clean card-based layouts, drill into a project dashboard with KPI metrics, and explore task history with expandable detail
**Depends on**: Phase 19
**Requirements**: PROJ-10, PROJ-11, PROJ-12, PROJ-13, PROJ-14, PROJ-15, PROJ-16, TMPL-10, TMPL-11, TMPL-12
**Success Criteria** (what must be TRUE):
  1. Project list page displays all projects as cards in a responsive grid, each showing name, description, stack badges, and last activity time
  2. Clicking a project card opens a dashboard view with KPI cards (total tasks, running, completed, failed) and a task list below
  3. Task rows in the project dashboard show status badge, prompt preview, timestamp, and duration -- clicking a row expands it to reveal full agent output
  4. A prominent "New Task" button is visible in the project dashboard header
  5. Template page displays templates as cards in a grid with name, description, stack info, and builtin/custom badge -- clicking a card shows file list and metadata
**Plans**: TBD

### Phase 21: Task Flow & Polish
**Goal**: Users can create tasks, monitor running tasks with live output, handle approval gates, and browse all tasks across projects from a single page
**Depends on**: Phase 20
**Requirements**: TASK-20, TASK-21, TASK-22, TASK-23, TASK-24
**Success Criteria** (what must be TRUE):
  1. Task creation form provides project selector, prompt textarea, mode toggle (supervised/autonomous), and submit button -- all styled consistently with the design system
  2. Running task view shows a status indicator, live-streaming output via WebSocket, and a cancel button
  3. When a task hits an approval gate, a clear action card appears with approve/reject/continue buttons that are easy to identify and tap
  4. Completed task view shows final status, full output log, and offers "back to project" and "new task" navigation actions
  5. Global tasks page lists all tasks across all projects with status filtering (running, completed, failed, all)
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 18 -> 19 -> 20 -> 21

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
| 12. DB Foundation | v2.1 | 1/1 | Complete | 2026-03-13 |
| 13. Template System | v2.1 | 2/2 | Complete | 2026-03-13 |
| 14. Context Assembly | v2.1 | 2/2 | Complete | 2026-03-13 |
| 15. Project Service and API | v2.1 | 2/2 | Complete | 2026-03-14 |
| 16. Task-Project Integration | v2.1 | 1/1 | Complete | 2026-03-14 |
| 17. SPA Frontend | v2.1 | 2/2 | Complete | 2026-03-14 |
| 18. Design System Foundation | v2.2 | 0/1 | Not started | - |
| 19. Sidebar Layout & Responsive Shell | v2.2 | 0/TBD | Not started | - |
| 20. Project & Template Views | v2.2 | 0/TBD | Not started | - |
| 21. Task Flow & Polish | v2.2 | 0/TBD | Not started | - |
