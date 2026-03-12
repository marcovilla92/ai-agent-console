# Requirements: AI Agent Workflow Console

**Defined:** 2026-03-11
**Core Value:** The orchestrator must reliably coordinate agents through iterative cycles — taking a rough idea and producing complete, usable code output with zero manual agent management.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### TUI & Interface

- [x] **TUI-01**: User sees 4-panel layout (Prompt editor, Plan output, Execute output, Review collapsible)
- [x] **TUI-02**: User navigates between panels with Tab key
- [x] **TUI-03**: User triggers actions via keyboard shortcuts (Ctrl+Enter send prompt, Ctrl+P regenerate plan, Ctrl+E execute, Ctrl+R review)
- [x] **TUI-04**: User sees status bar with current agent name, state, step description, next action
- [ ] **TUI-05**: User can resize and collapse panels via keyboard or mouse
- [x] **TUI-06**: Interface uses dark theme by default

### Agents

- [ ] **AGNT-01**: PLAN agent produces structured output (GOAL, ASSUMPTIONS, CONSTRAINTS, TASKS, ARCHITECTURE, FILES TO CREATE, HANDOFF → EXECUTE)
- [ ] **AGNT-02**: EXECUTE agent produces structured output (TARGET, PROJECT STRUCTURE, FILES, CODE, COMMANDS, SETUP NOTES, HANDOFF → REVIEW)
- [ ] **AGNT-03**: REVIEW agent produces structured output (SUMMARY, ISSUES FOUND, RISKS, IMPROVEMENTS, DECISION: APPROVED / BACK TO PLAN / BACK TO EXECUTE)
- [x] **AGNT-04**: User sees visible handoff context between agent panels showing what data was passed
- [x] **AGNT-05**: New agents can be added via config file (name, system_prompt, output_contract, panel_assignment) without code changes

### Orchestration

- [x] **ORCH-01**: AI-driven orchestrator calls Claude CLI to analyze agent outputs and decide next agent
- [ ] **ORCH-02**: REVIEW decision triggers re-PLAN or re-EXECUTE with user confirmation before proceeding
- [x] **ORCH-03**: Cycle detection prevents infinite loops via hard iteration limit and repeated-state detection
- [x] **ORCH-04**: Orchestrator shows decision reasoning and current workflow state in status area

### Infrastructure

- [x] **INFR-01**: Claude CLI invoked via asyncio.create_subprocess_exec with streaming stdout
- [x] **INFR-02**: Streaming output displays line-by-line in real-time in TUI panels
- [x] **INFR-03**: Sessions persisted in SQLite database (prompts, plans, execute outputs, reviews, orchestrator decisions)
- [x] **INFR-04**: User creates new project by entering name, system creates dedicated folder under workspace
- [x] **INFR-05**: Retry logic with 3 attempts and exponential backoff on Claude CLI errors
- [ ] **INFR-06**: Git auto-commit after successful execution cycles with descriptive commit messages
- [ ] **INFR-07**: Token usage and estimated cost tracked per agent per cycle, displayed in status bar
- [ ] **INFR-08**: User can browse past sessions and resume any previous session
- [x] **INFR-09**: Workspace context (project path, existing files, detected stack, session history) shared across all agent calls via system prompts

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Parallel Execution

- **PARA-01**: User can launch multiple agents in parallel for independent tasks
- **PARA-02**: Orchestrator manages parallel agent completion and result merging

### Additional Agents

- **XAGT-01**: DEBUG agent specialized in error diagnosis and troubleshooting
- **XAGT-02**: TEST agent generates tests for code produced by EXECUTE
- **XAGT-03**: DEPLOY agent prepares deployment configs, Dockerfiles, CI/CD

### Export & Sharing

- **EXPT-01**: User can export full session as markdown report
- **EXPT-02**: User can export project summary with all agent outputs

## Out of Scope

| Feature | Reason |
|---------|--------|
| Web UI / browser dashboard | Terminal-first identity, doubles codebase |
| Multi-model support (OpenAI, Gemini) | Claude CLI only by design, avoids testing matrix |
| Direct API calls | CLI handles auth, tools, MCP, permissions for free |
| Multi-user / collaboration | Personal tool, single-user |
| Voice input | Keyboard-first is the value proposition |
| Plugin marketplace | Premature — pluggable agents sufficient |
| Auto-run generated code | Dangerous without review, user confirms execution |
| GUI file browser | Terminal does this already, marginal value |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| TUI-01 | Phase 3 | Complete |
| TUI-02 | Phase 3 | Complete |
| TUI-03 | Phase 3 | Complete |
| TUI-04 | Phase 3 | Complete |
| TUI-05 | Phase 5 | Pending |
| TUI-06 | Phase 3 | Complete |
| AGNT-01 | Phase 2 | Pending |
| AGNT-02 | Phase 2 | Pending |
| AGNT-03 | Phase 2 | Pending |
| AGNT-04 | Phase 2 | Complete |
| AGNT-05 | Phase 2 | Complete |
| ORCH-01 | Phase 4 | Complete |
| ORCH-02 | Phase 4 | Pending |
| ORCH-03 | Phase 4 | Complete |
| ORCH-04 | Phase 4 | Complete |
| INFR-01 | Phase 1 | Complete |
| INFR-02 | Phase 3 | Complete |
| INFR-03 | Phase 1 | Complete |
| INFR-04 | Phase 2 | Complete |
| INFR-05 | Phase 1 | Complete |
| INFR-06 | Phase 5 | Pending |
| INFR-07 | Phase 5 | Pending |
| INFR-08 | Phase 5 | Pending |
| INFR-09 | Phase 1 | Complete |

**Coverage:**
- v1 requirements: 24 total
- Mapped to phases: 24
- Unmapped: 0

---
*Requirements defined: 2026-03-11*
*Last updated: 2026-03-11 after roadmap creation*
