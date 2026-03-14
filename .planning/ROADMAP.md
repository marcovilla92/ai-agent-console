# Roadmap: AI Agent Workflow Console

## Milestones

- ✅ **v1.0 MVP** -- Phases 1-5 (shipped 2026-03-12)
- ✅ **v2.0 Web Platform** -- Phases 6-11 (shipped 2026-03-13)
- ✅ **v2.1 Project Router** -- Phases 12-17 (shipped 2026-03-14)
- ✅ **v2.2 UI Redesign** -- Phases 18-21 (shipped 2026-03-14)
- 🚧 **v2.3 Orchestration Improvements** -- Phases 22-25 (in progress)

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

### v2.3 Orchestration Improvements

- [ ] **Phase 22: Bug Fixes & Foundation** - Fix agent/orchestrator system prompts and implement bounded handoff windowing
- [ ] **Phase 23: Core Output** - File writer module, targeted re-route prompts, and smart section filtering
- [ ] **Phase 24: Pipeline Extension** - Dynamic schema from registry, routing validation, and test agent
- [ ] **Phase 25: Autonomy Refinement** - Confidence-based gating with autonomous-by-default mode

## Phase Details

### Phase 22: Bug Fixes & Foundation
**Goal**: Agents follow their formatting rules and the orchestrator knows its routing role -- the pipeline produces structured, predictable output with bounded context growth
**Depends on**: Phase 21 (v2.2 complete)
**Requirements**: FIX-01, FIX-02, CTX-05, CTX-06
**Success Criteria** (what must be TRUE):
  1. Every agent (plan, execute, review) produces output that follows its system prompt formatting sections -- visible in the streaming output log
  2. Orchestrator routing decisions reference its role definition and agent descriptions -- decisions are no longer generic "pick next"
  3. Handoff context passed between agents contains only the last complete cycle (plan+execute+review) and stays under 8000 characters -- older cycles are dropped
  4. On re-route cycles, the original plan handoff is always preserved in context regardless of windowing -- execute never loses the initial task description
**Plans**: 2 plans
Plans:
- [ ] 22-01-PLAN.md — Fix system prompts for agents and orchestrator (FIX-01, FIX-02)
- [ ] 22-02-PLAN.md — Bounded handoff windowing with pinned first plan (CTX-05, CTX-06)

### Phase 23: Core Output
**Goal**: The pipeline writes real code files to disk and provides focused feedback on re-route cycles -- execute output becomes usable artifacts, not just text in a database
**Depends on**: Phase 22
**Requirements**: FWRT-01, FWRT-02, FWRT-03, FWRT-04, FWRT-05, FWRT-06, CTX-07, CTX-08
**Success Criteria** (what must be TRUE):
  1. After execute completes, code blocks with file path annotations are parsed and written as actual files under the project workspace -- files exist on disk
  2. The file writer reports exactly which files were written -- the list appears in the task log and feeds into auto-commit
  3. If execute produces a non-empty CODE section but zero files are extracted, a warning is logged instead of silent success
  4. When review triggers a re-route back to execute, the execute agent receives a targeted prompt listing specific ISSUES/IMPROVEMENTS from review -- not the full handoff dump
  5. Orchestrator routing prompt includes only sections relevant to the last agent type (via ROUTING_SECTIONS map) -- CODE sections from execute do not pollute routing decisions
**Plans**: 2 plans
Plans:
- [ ] 22-01-PLAN.md — Fix system prompts for agents and orchestrator (FIX-01, FIX-02)
- [ ] 22-02-PLAN.md — Bounded handoff windowing with pinned first plan (CTX-05, CTX-06)

### Phase 24: Pipeline Extension
**Goal**: Adding a new agent to the pipeline requires only a registry entry -- the orchestrator auto-discovers agents, validates routing transitions, and a test agent performs static code review between execute and review
**Depends on**: Phase 23
**Requirements**: PIPE-01, PIPE-02, PIPE-03, PIPE-04, PIPE-05
**Success Criteria** (what must be TRUE):
  1. Orchestrator JSON schema enum is generated from AGENT_REGISTRY keys at runtime -- adding a new agent config automatically makes it routable
  2. Orchestrator system prompt dynamically lists available agents and their descriptions from the registry -- no hardcoded agent names
  3. Invalid routing transitions (e.g., review to test skipping execute) are caught and fall back to the agent's configured next_agent
  4. A test agent exists in the pipeline that performs static code review via LLM (no subprocess execution) and produces findings for the review agent
  5. The default pipeline flow is plan -> execute -> [file_write] -> test -> review with the orchestrator able to re-route as needed
**Plans**: 2 plans
Plans:
- [ ] 22-01-PLAN.md — Fix system prompts for agents and orchestrator (FIX-01, FIX-02)
- [ ] 22-02-PLAN.md — Bounded handoff windowing with pinned first plan (CTX-05, CTX-06)

### Phase 25: Autonomy Refinement
**Goal**: Tasks run fully autonomously by default with no user confirmations -- supervised mode remains as an opt-in option for when the user wants control
**Depends on**: Phase 24
**Requirements**: AUTO-01, AUTO-02, AUTO-03, AUTO-04
**Success Criteria** (what must be TRUE):
  1. New tasks default to autonomous mode -- the pipeline runs from prompt to completion without any user confirmations
  2. In autonomous mode, low confidence decisions (< 0.5) log a visible warning in the task output but never block execution
  3. In supervised mode, low confidence decisions (< 0.5) trigger a user confirmation gate before proceeding
  4. Users can still select supervised mode when creating a task -- it works exactly as before with approval gates at each stage

## Progress

**Execution Order:**
Phases execute in numeric order: 22 -> 23 -> 24 -> 25

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
| 22. Bug Fixes & Foundation | 1/2 | In Progress|  | - |
| 23. Core Output | v2.3 | 0/TBD | Not started | - |
| 24. Pipeline Extension | v2.3 | 0/TBD | Not started | - |
| 25. Autonomy Refinement | v2.3 | 0/TBD | Not started | - |
