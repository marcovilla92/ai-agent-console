# Roadmap: AI Agent Workflow Console

## Overview

This roadmap takes the project from zero to a working terminal-based multi-agent AI console in 5 phases. We build bottom-up: infrastructure and data models first (Phase 1), then the three core agents with structured contracts (Phase 2), then the TUI shell that displays everything (Phase 3), then the AI-driven orchestrator that makes the system intelligent (Phase 4), and finally polish features that improve daily usage (Phase 5). Each phase delivers a coherent, testable capability that the next phase builds on.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation** - Data models, async subprocess runner, SQLite persistence, output parser with fallbacks (completed 2026-03-12)
- [ ] **Phase 2: Agent Pipeline** - PLAN/EXECUTE/REVIEW agents with structured contracts, project creation, rule-based sequential flow (gap closure in progress)
- [x] **Phase 3: TUI Shell** - 4-panel Textual layout, streaming display, keyboard shortcuts, status bar, dark theme (completed 2026-03-12)
- [ ] **Phase 4: Orchestrator Intelligence** - AI-driven routing via Claude CLI, iterative review cycles, cycle detection, decision visibility
- [ ] **Phase 5: Polish** - Resizable panels, git auto-commit, token tracking, session history browser

## Phase Details

### Phase 1: Foundation
**Goal**: Reliable infrastructure exists for launching Claude CLI subprocesses, persisting data, and parsing structured agent output
**Depends on**: Nothing (first phase)
**Requirements**: INFR-01, INFR-03, INFR-05, INFR-09
**Success Criteria** (what must be TRUE):
  1. A Python process can launch Claude CLI as an async subprocess and read its stdout line-by-line without deadlocks
  2. Session data (prompts, outputs, state) persists in SQLite and survives process restart
  3. Failed Claude CLI calls retry up to 3 times with exponential backoff before surfacing the error
  4. Workspace context (project path, existing files, detected stack) is assembled and injected into agent system prompts
  5. Structured output sections (GOAL, TASKS, etc.) are extracted from Claude CLI text output with regex fallback when formatting deviates
**Plans**: TBD

Plans:
- [x] 01-01: Test scaffolding and project bootstrap
- [ ] 01-02: TBD
- [ ] 01-03: TBD

### Phase 2: Agent Pipeline
**Goal**: Three agents (PLAN, EXECUTE, REVIEW) produce structured outputs and hand off to each other in a sequential pipeline
**Depends on**: Phase 1
**Requirements**: AGNT-01, AGNT-02, AGNT-03, AGNT-04, AGNT-05, INFR-04
**Success Criteria** (what must be TRUE):
  1. PLAN agent accepts a user prompt and produces output with GOAL, ASSUMPTIONS, CONSTRAINTS, TASKS, ARCHITECTURE, FILES TO CREATE, and HANDOFF sections
  2. EXECUTE agent receives the PLAN handoff and produces output with TARGET, PROJECT STRUCTURE, FILES, CODE, COMMANDS, SETUP NOTES, and HANDOFF sections
  3. REVIEW agent receives the EXECUTE handoff and produces output with SUMMARY, ISSUES, RISKS, IMPROVEMENTS, and DECISION (APPROVED / BACK TO PLAN / BACK TO EXECUTE)
  4. Handoff data passed between agents is visible and inspectable (not hidden internal state)
  5. A new agent can be added by creating a config entry (name, system_prompt, output_contract, panel_assignment) without modifying existing code
  6. User can create a new project by entering a name, and the system creates a dedicated workspace folder
**Plans**: 4 plans

Plans:
- [x] 02-01: Agent config registry & base agent class
- [x] 02-02: PLAN/EXECUTE/REVIEW agent implementations with system prompts
- [x] 02-03: Pipeline runner, handoffs & project creation
- [x] 02-04: Gap closure -- derive pipeline order from next_agent chain (AGNT-05)

### Phase 3: TUI Shell
**Goal**: Users interact with the agent pipeline through a 4-panel terminal interface with real-time streaming and keyboard-driven workflow
**Depends on**: Phase 2
**Requirements**: TUI-01, TUI-02, TUI-03, TUI-04, TUI-06, INFR-02
**Success Criteria** (what must be TRUE):
  1. User sees four distinct panels (Prompt editor, Plan output, Execute output, Review output) in a Textual-based terminal application
  2. Agent output streams into the corresponding panel line-by-line in real-time (not displayed only after completion)
  3. User navigates between panels with Tab and triggers actions with Ctrl+Enter (send), Ctrl+P (plan), Ctrl+E (execute), Ctrl+R (review)
  4. Status bar at the bottom shows the current agent name, workflow state, step description, and suggested next action
  5. Interface renders with a dark theme by default
**Plans**: TBD

Plans:
- [x] 03-01: TUI layout with 4 panels and dark theme
- [x] 03-02: Keyboard navigation and shortcuts
- [x] 03-03: Streaming display and status bar

### Phase 4: Orchestrator Intelligence
**Goal**: An AI-driven orchestrator autonomously decides which agent runs next, enabling iterative improvement cycles with safety limits
**Depends on**: Phase 3
**Requirements**: ORCH-01, ORCH-02, ORCH-03, ORCH-04
**Success Criteria** (what must be TRUE):
  1. After each agent completes, the orchestrator calls Claude CLI to analyze the output and decide which agent should run next
  2. When REVIEW decides BACK TO PLAN or BACK TO EXECUTE, the system re-routes to that agent with user confirmation before proceeding
  3. After 3 consecutive iterations without APPROVED, the system halts and asks the user whether to continue or stop
  4. The orchestrator's reasoning (why it chose the next agent) and current workflow state are visible in the status area
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD

### Phase 5: Polish
**Goal**: Daily-use quality improvements: resizable panels, automatic git commits, cost visibility, and session history
**Depends on**: Phase 4
**Requirements**: TUI-05, INFR-06, INFR-07, INFR-08
**Success Criteria** (what must be TRUE):
  1. User can resize and collapse panels via keyboard or mouse drag
  2. After a successful execution cycle, the system auto-commits generated files to git with a descriptive commit message
  3. Token usage and estimated cost per agent per cycle are displayed in the status bar
  4. User can browse past sessions and resume any previous session from the session list
**Plans**: TBD

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 3/3 | Complete   | 2026-03-12 |
| 2. Agent Pipeline | 4/4 | Complete | 2026-03-12 |
| 3. TUI Shell | 3/3 | Complete   | 2026-03-12 |
| 4. Orchestrator Intelligence | 0/2 | Not started | - |
| 5. Polish | 0/2 | Not started | - |
