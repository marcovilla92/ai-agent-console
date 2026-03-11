# AI Agent Workflow Console

## What This Is

A local terminal-based multi-agent interface (TUI) that orchestrates AI workflows using Claude CLI. It guides a developer through a structured PROMPT → PLAN → EXECUTE → REVIEW pipeline, with a central AI-driven orchestrator that decides autonomously what happens next. Built with Python + Textual, it's a personal productivity console for generating code, scripts, and project structures through AI agents.

## Core Value

The orchestrator must reliably coordinate agents through iterative cycles — taking a rough idea and producing complete, usable code output with zero manual agent management.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

<!-- Current scope. Building toward these. -->

- [ ] TUI with 4-panel layout (Prompt, Plan, Execute, Review collapsible)
- [ ] PLAN agent with structured output contract (GOAL, TASKS, ARCHITECTURE, FILES, HANDOFF)
- [ ] EXECUTE agent with structured output contract (TARGET, PROJECT STRUCTURE, CODE, COMMANDS, HANDOFF)
- [ ] REVIEW agent with structured output contract (SUMMARY, ISSUES, RISKS, IMPROVEMENTS, DECISION)
- [ ] AI-driven master orchestrator that decides next agent based on output analysis
- [ ] Streaming output from Claude CLI into TUI panels in real-time
- [ ] Workspace context shared across agents (project path, existing files, stack, history)
- [ ] Session persistence via SQLite (prompts, plans, outputs, reviews)
- [ ] Project creation flow (ask name → create dedicated folder)
- [ ] Output saved both in TUI panel and to disk in project folder
- [ ] Keyboard-driven workflow (Ctrl+Enter, Ctrl+P, Ctrl+E, Ctrl+R, Tab)
- [ ] Resizable panels with dark theme
- [ ] Retry logic (3 attempts) on Claude CLI errors
- [ ] Iterative review cycles — unlimited with user confirmation
- [ ] Optional parallel agent execution
- [ ] Status bar showing current agent, state, step, next action
- [ ] Extensible agent architecture (pluggable agents with dedicated prompts)

### Out of Scope

- Multi-user / team features — personal tool only
- Web UI — terminal only
- OAuth / authentication — local tool
- Mobile support — desktop terminal only
- Agents other than PLAN/EXECUTE/REVIEW for v1 (DEBUG, TEST, DEPLOY deferred)

## Context

- Runs on Windows 11, Python environment available
- Claude CLI already installed and working with `--dangerously-skip-permissions`
- Project will live at `C:\Users\Marco\Documents\VisualStudio\ai-agent-console`
- Primary use case: generating complete code projects from ideas
- User is experienced developer, wants speed and keyboard-first UX
- Textual framework chosen for modern Python TUI capabilities

## Constraints

- **Runtime**: Must use Claude CLI via subprocess — no direct API calls
- **Framework**: Python + Textual for TUI
- **Platform**: Windows 11 primary (should work cross-platform)
- **Storage**: SQLite for session persistence
- **Agent communication**: Structured output contracts (enforced via system prompts)
- **Orchestrator**: AI-driven via Claude CLI (not rule-based)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Textual for TUI | Modern Python TUI framework, rich widgets, async support | — Pending |
| AI-driven orchestrator over rule-based | More flexible, handles ambiguous situations, adapts to output quality | — Pending |
| SQLite over JSON/Markdown for history | Queryable, single file, handles concurrent access | — Pending |
| Streaming output | Real-time feedback essential for long-running agent tasks | — Pending |
| Output contracts via system prompts | Ensures deterministic agent outputs without post-processing | — Pending |
| Project folder creation on new session | Clean workspace isolation per project | — Pending |

---
*Last updated: 2026-03-11 after initialization*
