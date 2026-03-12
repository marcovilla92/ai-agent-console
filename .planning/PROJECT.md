# AI Agent Workflow Console

## What This Is

A local terminal-based multi-agent interface (TUI) that orchestrates AI workflows using Claude CLI. It guides a developer through a structured PROMPT → PLAN → EXECUTE → REVIEW pipeline, with a central AI-driven orchestrator that decides autonomously what happens next. Built with Python + Textual, it's a personal productivity console for generating code, scripts, and project structures through AI agents.

## Core Value

The orchestrator must reliably coordinate agents through iterative cycles — taking a rough idea and producing complete, usable code output with zero manual agent management.

## Requirements

### Validated

- ✓ 4-panel TUI layout (Prompt, Plan, Execute, Review) with dark theme — v1.0
- ✓ Keyboard-driven workflow (Ctrl+S send, Ctrl+P/E/R agents, Tab navigate) — v1.0
- ✓ Resizable and collapsible panels via Ctrl+1-4 and Ctrl+Arrow — v1.0
- ✓ Real-time streaming output from Claude CLI into TUI panels — v1.0
- ✓ AI-driven orchestrator decides next agent via Claude CLI with JSON schema — v1.0
- ✓ Iterative review cycles with user confirmation and cycle detection (3 iteration limit) — v1.0
- ✓ 3-agent pipeline (Plan/Execute/Review) with config-driven registry — v1.0
- ✓ Structured handoffs visible between agent panels — v1.0
- ✓ Extensible agent architecture (pluggable agents via config) — v1.0
- ✓ SQLite session persistence (prompts, outputs, reviews, orchestrator decisions) — v1.0
- ✓ Project creation flow (name → dedicated workspace folder) — v1.0
- ✓ Workspace context shared across agents (project path, files, stack, history) — v1.0
- ✓ Retry logic (3 attempts, exponential backoff) on Claude CLI errors — v1.0
- ✓ Git auto-commit after successful execution cycles — v1.0
- ✓ Token usage and cost tracking displayed in status bar — v1.0
- ✓ Session history browser with resume capability (Ctrl+B) — v1.0
- ✓ Status bar showing current agent, state, step, next action — v1.0

### Active

- [ ] Agent output section validation (enforce GOAL, TASKS, etc. presence in output)
- [ ] Optional parallel agent execution
- [ ] Output saved to disk in project folder alongside TUI display

### Out of Scope

- Multi-user / team features — personal tool only
- Web UI — terminal-first identity, doubles codebase
- Multi-model support (OpenAI, Gemini) — Claude CLI only by design
- Direct API calls — CLI handles auth, tools, MCP, permissions
- Mobile support — desktop terminal only
- Voice input — keyboard-first is the value proposition
- Auto-run generated code — dangerous without review
- DEBUG/TEST/DEPLOY agents — deferred to v2

## Context

Shipped v1.0 MVP with 4,524 LOC Python (2,176 src + 2,348 tests).
Tech stack: Python 3.12+, Textual 8.x, aiosqlite, asyncio subprocess.
114 files, 27 feat commits across 5 phases in 2 days.
All 160 tests passing. Runs on Ubuntu 24.04 (OVH VPS).

## Constraints

- **Runtime**: Must use Claude CLI via subprocess — no direct API calls
- **Framework**: Python + Textual for TUI
- **Platform**: Cross-platform (developed on Ubuntu, should work on Windows/macOS)
- **Storage**: SQLite for session persistence
- **Agent communication**: Structured output contracts (enforced via system prompts)
- **Orchestrator**: AI-driven via Claude CLI (not rule-based)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Textual for TUI | Modern Python TUI framework, rich widgets, async support | ✓ Good — theme, grid layout, DataTable, ModalScreen all worked well |
| AI-driven orchestrator over rule-based | More flexible, handles ambiguous situations | ✓ Good — JSON schema enforcement gives structured decisions |
| SQLite over JSON/Markdown for history | Queryable, single file, handles concurrent access | ✓ Good — aiosqlite async pattern clean |
| Streaming output | Real-time feedback essential for long-running tasks | ✓ Good — NDJSON parser + RichLog streaming works |
| Output contracts via system prompts | Ensures deterministic agent outputs | ⚠️ Revisit — sections not validated post-output |
| Project folder creation on new session | Clean workspace isolation per project | ✓ Good |
| asyncio.Event bridge for modals | Await modal results from call_from_thread | ✓ Good — clean pattern for Textual async flow |
| stream_claude yields dict for result events | isinstance check distinguishes text from metadata | ✓ Good — simple, no wrapper class needed |

---
*Last updated: 2026-03-12 after v1.0 milestone*
