# AI Agent Workflow Console

A local terminal-based multi-agent interface (TUI) that orchestrates AI workflows using Claude CLI.

## Concept

A developer productivity console where each AI agent performs a specific role in a 4-stage workflow:

```
PROMPT → PLAN → EXECUTE → REVIEW
              ↑_______________|
                (orchestrated)
```

## Features

- **4-panel TUI** — Prompt editor, Plan output, Execute output, Review panel
- **AI-driven orchestrator** — Claude decides which agent runs next
- **Structured agent contracts** — Each agent produces deterministic, parseable output
- **Iterative review cycles** — REVIEW can send work back to PLAN or EXECUTE
- **Shared workspace context** — All agents know the project state
- **Session persistence** — SQLite-backed sessions with resume capability
- **Streaming output** — Real-time token-by-token display in panels

## Stack

- Python + [Textual](https://textual.textualize.io/) — TUI framework
- asyncio subprocess — Claude CLI integration
- Pydantic — Output contract validation
- aiosqlite — Session persistence
- uv — Package manager

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Enter` | Send prompt to PLAN agent |
| `Ctrl+P` | Regenerate plan |
| `Ctrl+E` | Execute current plan |
| `Ctrl+R` | Trigger review |
| `Tab` | Switch panels |

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- [Claude CLI](https://claude.ai/download) with `claude --dangerously-skip-permissions`

## Getting Started

```bash
# Install dependencies
uv sync

# Run
uv run python -m app
```

## Project Structure

```
app/
├── agents/          # Agent prompts and output contracts
├── core/            # Subprocess runner, output parser, persistence
├── orchestrator/    # FSM and AI-driven routing
└── ui/              # Textual panels and layout
```

---
*Work in progress — see `.planning/ROADMAP.md` for current status*
