# Stack Research

**Domain:** Python TUI multi-agent AI orchestration console
**Researched:** 2026-03-11
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12+ | Runtime | Latest stable with best asyncio performance; 3.12 brought significant speedups. Avoid 3.14 (too new for library compat). |
| Textual | 8.1.1 | TUI framework | The only serious modern Python TUI framework. Async-native, rich widget set (collapsible panels, markdown rendering, input areas), CSS-like styling, Workers API for subprocess streaming. Actively maintained by Textualize. |
| Pydantic | 2.12.5 | Structured output validation | Validate agent output contracts (GOAL/TASKS/ARCHITECTURE etc.) parsed from Claude CLI JSON/structured text. V2 rewrite is 5-50x faster than V1. Industry standard for data validation. |
| aiosqlite | 0.22.1 | Async SQLite persistence | Async wrapper around sqlite3 that runs queries in a dedicated thread. Prevents blocking the Textual event loop during DB writes. Simple API mirroring stdlib sqlite3. |
| asyncio (stdlib) | builtin | Async subprocess orchestration | `asyncio.create_subprocess_exec` for streaming Claude CLI output line-by-line. Native to Python, zero dependencies. Textual is built on asyncio so they integrate seamlessly. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| loguru | 0.7.3 | Structured logging | All logging throughout the app. Single `logger` import, no configuration ceremony. File rotation, structured output, exception formatting with variable values. Write logs to file (not TUI) for debugging agent orchestration. |
| Typer | 0.15+ | CLI entry point | Launch the TUI with command-line args (project path, resume session, debug mode). Built on Click, uses type hints for zero-boilerplate CLI definition. |
| tomli / tomllib | stdlib (3.11+) | Configuration | Load project config (agent prompts, retry settings, key bindings) from TOML files. `tomllib` is in stdlib since 3.11, no extra dependency needed. |

### Database Schema Library

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (raw SQL via aiosqlite) | -- | Schema + queries | Use raw SQL for the ~5 tables needed (sessions, agents, messages, projects, config). An ORM is overkill for this scope. Use Pydantic models as the application layer, manual `INSERT`/`SELECT` underneath. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Package management, virtualenv, lockfile | 10-100x faster than pip. Deterministic lockfile via `uv.lock`. Handles venv creation automatically. The new Python standard -- use `uv init`, `uv add`, `uv run`. |
| textual-dev | TUI development tools | Live reload, CSS inspector, console logging during development. Install as dev dependency. Run with `textual run --dev`. |
| pytest | Testing framework | Standard Python test runner. Textual ships with `textual[dev]` which includes a pilot testing API for simulating user interaction. |
| pytest-asyncio | 1.3.0 | Async test support | Required for testing async agent orchestration, subprocess management, and DB operations. Use `asyncio_mode = "auto"` in pytest config. |
| ruff | Linting + formatting | Single tool replacing flake8, isort, black. Extremely fast (Rust-based, same team as uv). Configure in `pyproject.toml`. |

## Installation

```bash
# Initialize project with uv
uv init ai-agent-console
cd ai-agent-console

# Core dependencies
uv add textual pydantic aiosqlite loguru typer

# Dev dependencies
uv add --dev textual-dev pytest pytest-asyncio ruff
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Textual 8.x | urwid | Never for this project. Urwid is callback-heavy, no async, poor widget ecosystem. Legacy choice. |
| Textual 8.x | prompt_toolkit | Only if building a pure REPL, not a multi-panel TUI. No layout system comparable to Textual. |
| Textual 8.x | Rich (standalone) | Rich is Textual's rendering engine. Use Rich for simple CLI output formatting, Textual when you need interactive widgets and layout. |
| aiosqlite | SQLAlchemy async | If the schema grows beyond ~10 tables or needs migrations. Overkill for this project's 5-table SQLite schema. Adds complexity and startup time. |
| aiosqlite | sqlite3 (sync) | Never. Sync calls will block the Textual event loop, freezing the UI during DB writes. |
| Pydantic | dataclasses | If you only need type hints without validation. But agent output parsing NEEDS validation -- malformed JSON from Claude CLI is expected. Pydantic handles this gracefully. |
| Pydantic | msgspec | If pure performance matters more than ecosystem. msgspec is faster but has a smaller ecosystem and less tooling. Pydantic's error messages are far better for debugging agent output parsing. |
| loguru | structlog | If you need deep integration with Python's stdlib logging or observability platforms (Datadog, etc.). For a local desktop tool, loguru's simplicity wins. |
| uv | pip + venv | Only if uv is not installable on the target system. Pip works but is slower and lacks lockfile support without pip-tools. |
| Typer | Click | If you need very complex CLI subcommand trees. Typer is built on Click anyway and is simpler for this project's needs (just a few launch options). |
| Typer | argparse | Never. Verbose boilerplate for no benefit. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| curses / ncurses | Low-level, no widgets, painful API, poor Windows support | Textual |
| blessed / blessings | Thin wrappers over curses, same problems | Textual |
| PydanticAI | Agent framework that calls LLM APIs directly. Project requirement is subprocess CLI calls, not API calls. Adding PydanticAI would fight the architecture. | Raw asyncio subprocess + Pydantic for validation |
| LangChain / LlamaIndex | Heavy agent frameworks designed for API-based LLM orchestration. Wrong abstraction for CLI subprocess orchestration. Would add massive dependency tree for features you won't use. | Custom orchestrator with asyncio subprocess |
| trio / anyio | Alternative async runtimes. Textual is built on asyncio specifically. Mixing runtimes causes subtle bugs. | asyncio (stdlib) |
| SQLModel | Tiangolo's SQLAlchemy+Pydantic hybrid. Adds SQLAlchemy as transitive dependency for no benefit at this scale. | aiosqlite + Pydantic models |
| poetry | Slower than uv, more complex configuration, Rust-free but that's not a benefit. Being superseded by uv in the ecosystem. | uv |
| black + isort + flake8 | Three separate tools with overlapping concerns and conflicting configs. | ruff (single tool, faster) |

## Stack Patterns by Variant

**If streaming output is choppy or has buffering issues:**
- Set `PYTHONUNBUFFERED=1` for the Claude CLI subprocess
- Use `asyncio.create_subprocess_exec` (not `_shell`) for proper pipe handling
- Read from `proc.stdout` with `async for line in proc.stdout` pattern
- Use Textual's `call_from_thread` or Workers API to post updates to widgets

**If agent output parsing fails frequently:**
- Add Pydantic `model_validator` with fallback parsing (try JSON first, then regex extraction)
- Store raw output in SQLite alongside parsed output for debugging
- Implement retry with exponential backoff on parse failure (not just CLI failure)

**If the TUI needs to run in web browser (future):**
- Textual supports `textual-web` for serving TUI apps over WebSocket
- No architecture changes needed -- Textual abstracts the rendering backend
- Just `pip install textual-web` and `textual serve app.py`

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| textual 8.1.1 | Python 3.9-3.14 | Requires `rich` (bundled/auto-installed) |
| pydantic 2.12.5 | Python 3.9+ | pydantic-core is a Rust extension -- prebuilt wheels available for Windows |
| aiosqlite 0.22.1 | Python 3.9+ | Zero compiled dependencies, pure Python |
| loguru 0.7.3 | Python 3.5+ | Zero dependencies |
| typer 0.15+ | Python 3.7+ | Depends on click and rich |
| pytest-asyncio 1.3.0 | Python 3.10+ | Requires pytest 8+ |

**Key compatibility note:** pytest-asyncio 1.3.0 requires Python 3.10+. Since we target 3.12+, this is fine. But if you need to support 3.9, pin pytest-asyncio < 1.0.

## Project Structure

```
ai-agent-console/
  pyproject.toml          # uv project config, dependencies, ruff config
  uv.lock                 # Deterministic lockfile (auto-generated)
  src/
    agent_console/
      __init__.py
      app.py              # Textual App class, layout, key bindings
      agents/
        __init__.py
        base.py           # Base agent class (subprocess runner + output parser)
        planner.py        # PLAN agent
        executor.py       # EXECUTE agent
        reviewer.py       # REVIEW agent
      orchestrator.py     # AI-driven orchestrator (decides next agent)
      models/
        __init__.py
        contracts.py      # Pydantic models for agent output contracts
        session.py        # Pydantic models for session/project data
      db/
        __init__.py
        store.py          # aiosqlite wrapper, queries, schema init
        migrations.py     # Simple schema versioning
      widgets/
        __init__.py
        prompt_panel.py   # User input panel
        plan_panel.py     # Plan display with streaming
        execute_panel.py  # Execute display with streaming
        review_panel.py   # Review display with streaming
        status_bar.py     # Current agent, state, step
      cli.py              # Typer CLI entry point
  tests/
    conftest.py
    test_agents.py
    test_orchestrator.py
    test_db.py
    test_app.py           # Textual pilot tests
```

## Sources

- [Textual PyPI](https://pypi.org/project/textual/) -- verified v8.1.1, Python 3.9+, released 2026-03-10 (HIGH confidence)
- [Textual Workers docs](https://textual.textualize.io/guide/workers/) -- verified subprocess streaming pattern (HIGH confidence)
- [Pydantic PyPI](https://pypi.org/project/pydantic/) -- verified v2.12.5, Python 3.9+ (HIGH confidence)
- [aiosqlite PyPI](https://pypi.org/project/aiosqlite/) -- verified v0.22.1, Python 3.9+ (HIGH confidence)
- [loguru PyPI](https://pypi.org/project/loguru/) -- verified v0.7.3 (HIGH confidence)
- [pytest-asyncio PyPI](https://pypi.org/project/pytest-asyncio/) -- verified v1.3.0, Python 3.10+ (HIGH confidence)
- [uv vs pip comparison](https://realpython.com/uv-vs-pip/) -- ecosystem adoption evidence (MEDIUM confidence)
- [Typer/Click comparison](https://oneuptime.com/blog/post/2025-07-02-python-cli-click-typer/view) -- feature comparison (MEDIUM confidence)

---
*Stack research for: AI Agent Workflow Console (Python TUI multi-agent orchestration)*
*Researched: 2026-03-11*
