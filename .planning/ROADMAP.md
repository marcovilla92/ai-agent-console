# Roadmap: AI Agent Workflow Console

## Milestones

- ✅ **v1.0 MVP** -- Phases 1-5 (shipped 2026-03-12)
- ✅ **v2.0 Web Platform** -- Phases 6-11 (shipped 2026-03-13)
- ✅ **v2.1 Project Router** -- Phases 12-17 (shipped 2026-03-14)
- ✅ **v2.2 UI Redesign** -- Phases 18-21 (shipped 2026-03-14)
- ✅ **v2.3 Orchestration Improvements** -- Phases 22-25 (shipped 2026-03-14)
- 🚧 **v2.4 Template System Overhaul** -- Phases 26-30 (in progress)

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

<details>
<summary>v2.2 UI Redesign (Phases 18-21) -- SHIPPED 2026-03-14</summary>

- [x] Phase 18: Design System Foundation (1/1 plans) -- completed 2026-03-14
- [x] Phase 19: Sidebar Layout & Responsive Shell (1/1 plans) -- completed 2026-03-14
- [x] Phase 20: Project & Template Views (1/1 plans) -- completed 2026-03-14
- [x] Phase 21: Task Flow & Polish (1/1 plans) -- completed 2026-03-14

</details>

<details>
<summary>v2.3 Orchestration Improvements (Phases 22-25) -- SHIPPED 2026-03-14</summary>

- [x] Phase 22: Bug Fixes & Foundation (2/2 plans) -- completed 2026-03-14
- [x] Phase 23: Core Output (2/2 plans) -- completed 2026-03-14
- [x] Phase 24: Pipeline Extension (1/1 plans) -- completed 2026-03-14
- [x] Phase 25: Autonomy Refinement (1/1 plans) -- completed 2026-03-14

</details>

### v2.4 Template System Overhaul

- [x] **Phase 26: Agent Loader Foundation** - Discover agents from project `.claude/agents/`, parse frontmatter, build per-project registry with core agent protection (completed 2026-03-14)
- [x] **Phase 27: Commands & Settings Loaders** - Discover commands from `.claude/commands/` and apply project settings from `.claude/settings.local.json` (completed 2026-03-14)
- [x] **Phase 28: Orchestrator Dynamic Registry** - Build orchestrator schema per-task from injected registry, enable routing to project-specific agents and commands (completed 2026-03-14)
- [ ] **Phase 29: AI Template Generation** - Generate complete templates from natural language descriptions via Claude CLI with validation
- [ ] **Phase 30: Template Editor UI** - Preview file tree, edit file contents inline, save with preview-before-save flow

## Phase Details

### Phase 26: Agent Loader Foundation
**Goal**: The system discovers and loads project-specific agents from `.claude/agents/*.md` into an isolated per-project registry -- templates become live environments where custom agents participate in the pipeline
**Depends on**: Phase 25 (v2.3 complete)
**Requirements**: AGLD-01, AGLD-02, AGLD-03, AGLD-04
**Success Criteria** (what must be TRUE):
  1. When a task starts for a project that has `.claude/agents/*.md` files, those agents appear in the project's agent registry without any manual configuration
  2. Agent markdown files with YAML frontmatter are parsed correctly; plain-text files without frontmatter load with sensible defaults (name from filename, broad transitions)
  3. Two concurrent tasks on different projects each see only their own project agents -- no cross-contamination between registries
  4. Core pipeline agents (plan, execute, test, review) cannot be overridden by a project agent file with the same name -- core agents always win
**Plans:** 2/2 plans complete
Plans:
- [ ] 26-01-PLAN.md — Agent discovery module + AgentConfig extension + frontmatter parsing
- [ ] 26-02-PLAN.md — Registry merge with core protection + per-project isolation

### Phase 27: Commands & Settings Loaders
**Goal**: The system discovers project commands and applies project-level settings -- templates ship commands that agents can reference and settings that configure pipeline behavior
**Depends on**: Phase 26
**Requirements**: CMLD-01, CMLD-02, SETG-01, SETG-02
**Success Criteria** (what must be TRUE):
  1. When a task starts for a project with `.claude/commands/*.md` files, those commands are discovered and injected into the agent context as available instructions
  2. Agents in the pipeline can see the list of available commands and their descriptions in their context -- commands are not invisible
  3. When a project has `.claude/settings.local.json`, its values are read and merged with global settings (project overrides where specified)
  4. Security-sensitive global settings (system-level flags) cannot be overridden by project settings -- the merge is whitelisted
**Plans:** 2/2 plans complete
Plans:
- [ ] 27-01-PLAN.md — Command loader + settings loader modules with tests
- [ ] 27-02-PLAN.md — Context assembly integration (commands + settings injection)

### Phase 28: Orchestrator Dynamic Registry
**Goal**: The orchestrator builds its routing schema dynamically per-task from the injected registry -- project agents and commands become routable targets in the pipeline
**Depends on**: Phase 27
**Requirements**: ORCH-01, ORCH-02, ORCH-03, CMLD-03
**Success Criteria** (what must be TRUE):
  1. The orchestrator JSON schema enum is rebuilt for each task using `build_orchestrator_schema(registry)` -- adding a project agent automatically makes it appear in routing options
  2. The pipeline accepts a registry as an injected parameter instead of reading a module-level constant -- `orchestrate_pipeline()` works with any registry
  3. The orchestrator can route to project-specific agents (e.g., a `db-migrator` from a FastAPI template) and execution proceeds with that agent's system prompt
  4. Commands discovered from `.claude/commands/` can be targeted by the orchestrator as routing destinations
  5. Project-specific agents appear in the orchestrator's system prompt with their descriptions so it knows when to route to them
**Plans:** 2/2 plans complete
Plans:
- [ ] 28-01-PLAN.md &mdash; Inline prompt support + public schema builder + dynamic system prompt + command injection
- [ ] 28-02-PLAN.md &mdash; Registry threading through WebTaskContext, orchestrate_pipeline, and TaskManager

### Phase 29: AI Template Generation
**Goal**: Users can describe a project in natural language and receive a complete, validated template with files, agents, commands, and settings -- generated by AI
**Depends on**: Phase 26
**Requirements**: AIGEN-01, AIGEN-02, AIGEN-03
**Success Criteria** (what must be TRUE):
  1. User can type a natural language description (e.g., "a FastAPI app with Stripe billing and email notifications") and receive a complete template with source files, CLAUDE.md, agents, commands, and settings
  2. All generated agent and command files are validated through the same loader used at runtime before being returned to the user -- invalid files produce `validation_errors` in the response
  3. AI template generation uses a separate semaphore from the pipeline tasks -- generating a template does not consume a task slot, and returns HTTP 429 if the generation slot is busy
**Plans:** 2 plans
Plans:
- [ ] 29-01-PLAN.md — System prompt + generate endpoint with validation and semaphore
- [ ] 29-02-PLAN.md — Test suite for template generation (mocked Claude CLI)

### Phase 30: Template Editor UI
**Goal**: Users can preview and modify template contents before and after saving -- full visibility and control over what a template contains
**Depends on**: Phase 29
**Requirements**: EDIT-01, EDIT-02, EDIT-03
**Success Criteria** (what must be TRUE):
  1. User can view a template's complete file structure as a collapsible tree (directories and files) in the browser
  2. User can click any file in the tree to view and edit its contents inline via a textarea
  3. User can save modifications with a preview-before-save flow -- changes are visible before committing
**Plans:** 2 plans
Plans:
- [ ] 27-01-PLAN.md — Command loader + settings loader modules with tests
- [ ] 27-02-PLAN.md — Context assembly integration (commands + settings injection)

## Progress

**Execution Order:**
Phases execute in numeric order: 26 -> 27 -> 28 -> 29 -> 30

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
| 18. Design System Foundation | v2.2 | 1/1 | Complete | 2026-03-14 |
| 19. Sidebar Layout & Responsive Shell | v2.2 | 1/1 | Complete | 2026-03-14 |
| 20. Project & Template Views | v2.2 | 1/1 | Complete | 2026-03-14 |
| 21. Task Flow & Polish | v2.2 | 1/1 | Complete | 2026-03-14 |
| 22. Bug Fixes & Foundation | v2.3 | 2/2 | Complete | 2026-03-14 |
| 23. Core Output | v2.3 | 2/2 | Complete | 2026-03-14 |
| 24. Pipeline Extension | v2.3 | 1/1 | Complete | 2026-03-14 |
| 25. Autonomy Refinement | v2.3 | 1/1 | Complete | 2026-03-14 |
| 26. Agent Loader Foundation | 2/2 | Complete    | 2026-03-14 | - |
| 27. Commands & Settings Loaders | 2/2 | Complete    | 2026-03-14 | - |
| 28. Orchestrator Dynamic Registry | 2/2 | Complete    | 2026-03-14 | - |
| 29. AI Template Generation | v2.4 | 0/2 | Not started | - |
| 30. Template Editor UI | v2.4 | 0/0 | Not started | - |
