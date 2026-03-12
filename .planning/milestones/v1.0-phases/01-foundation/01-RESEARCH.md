# Phase 1: Foundation - Research

**Researched:** 2026-03-11
**Domain:** Python asyncio subprocess management, SQLite persistence, Claude CLI invocation, retry logic, output parsing
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFR-01 | Claude CLI invoked via asyncio.create_subprocess_exec with streaming stdout | Asyncio subprocess patterns, Windows ProactorEventLoop, deadlock-free readline loop documented |
| INFR-03 | Sessions persisted in SQLite database (prompts, plans, execute outputs, reviews, orchestrator decisions) | aiosqlite async patterns, repository pattern, dataclass-based schema documented |
| INFR-05 | Retry logic with 3 attempts and exponential backoff on Claude CLI errors | Tenacity library with async support, wait_exponential, retry_if_exception_type documented |
| INFR-09 | Workspace context (project path, existing files, detected stack, session history) shared across all agent calls via system prompts | File enumeration patterns, stack detection heuristics, --append-system-prompt-file flag documented |
</phase_requirements>

---

## Summary

Phase 1 establishes the four technical pillars all subsequent phases depend on: a deadlock-free async subprocess runner for Claude CLI, a SQLite persistence layer with async access, resilient retry with exponential backoff, and a workspace context assembler that builds system prompt injections. All four are well-understood Python problems with mature standard solutions and no major unknowns — the only hands-on verification needed is Windows behavior for the asyncio subprocess and Claude CLI's actual stream-json line shapes.

The project runs on Windows 11 (confirmed from environment). Python's asyncio subprocess requires `ProactorEventLoop` on Windows, which has been the default since Python 3.10. The key deadlock risk is calling `process.wait()` before draining stdout — the safe pattern is to loop `readline()` until EOF, then call `wait()`. Claude CLI must be invoked with `-p` (print/non-interactive) and `--output-format stream-json` for programmatic use; each stdout line is a complete JSON object.

**Primary recommendation:** Use `asyncio.create_subprocess_exec` with `ProactorEventLoop` (default on Windows 3.10+), read stdout line-by-line with `readline()` in an async loop, store data in SQLite via `aiosqlite` with plain Python dataclasses and a repository class per entity, wrap each Claude CLI call with `tenacity` for 3-attempt exponential backoff, and assemble workspace context by scanning the project directory for stack indicator files.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| aiosqlite | 0.20+ | Async SQLite access on the asyncio event loop | Official asyncio-friendly wrapper around stdlib sqlite3; single-thread-per-connection prevents blocking |
| tenacity | 8.x | Retry with exponential backoff | Mature, decorator-based, native asyncio support with `@retry` on coroutines |
| Python stdlib `asyncio` | 3.10+ | Subprocess creation, event loop | `ProactorEventLoop` is default on Windows 3.10+; no extra install needed |
| Python stdlib `re` | built-in | Regex-based section extraction from agent text output | No dependency needed; sufficient for structured section parsing |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `dataclasses` (stdlib) | 3.10+ | Typed value objects for Session, AgentOutput | Use for all persistent data models — keeps schema close to code |
| `pathlib` (stdlib) | built-in | Workspace path traversal and stack detection | Use instead of `os.path` for all file system operations |
| `json` (stdlib) | built-in | Parse NDJSON lines from Claude CLI stream-json output | Each stdout line is a complete JSON object |
| `asyncio.Lock` (stdlib) | built-in | Serialize concurrent database writes | Use when multiple coroutines can write simultaneously |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| aiosqlite (direct SQL) | SQLAlchemy async + aiosqlite | SQLAlchemy adds complexity and migration tooling not needed for this scope |
| tenacity | Custom retry loop | Tenacity handles jitter, stop conditions, and async transparently; hand-rolling is error-prone |
| `re` module | pyparsing | pyparsing is more readable for grammars but heavier; regex is sufficient for known section headers |

**Installation:**
```bash
pip install aiosqlite tenacity
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/
├── runner/          # Claude CLI subprocess wrapper and stream reader
│   ├── __init__.py
│   ├── runner.py    # ClaudeRunner — launches subprocess, yields lines
│   └── retry.py     # Tenacity-wrapped invoke function
├── db/              # SQLite persistence layer
│   ├── __init__.py
│   ├── schema.py    # CREATE TABLE statements and dataclasses
│   └── repository.py # SessionRepository, AgentOutputRepository
├── context/         # Workspace context assembler
│   ├── __init__.py
│   └── assembler.py # WorkspaceContext — detects stack, enumerates files
├── parser/          # Structured output extractor
│   ├── __init__.py
│   └── extractor.py # SectionExtractor — regex + fallback
tests/
├── test_runner.py
├── test_db.py
├── test_context.py
└── test_parser.py
```

### Pattern 1: Deadlock-Free Async Subprocess Runner

**What:** Launch Claude CLI with `asyncio.create_subprocess_exec`, drain stdout line-by-line in an async `while True` loop, collect stderr concurrently with `asyncio.gather`, call `wait()` only after stdout EOF.

**When to use:** Every Claude CLI invocation.

**Example:**
```python
# Source: https://docs.python.org/3/library/asyncio-subprocess.html
import asyncio

async def run_claude(args: list[str]):
    proc = await asyncio.create_subprocess_exec(
        "claude", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    async def drain_stderr():
        return await proc.stderr.read()

    stderr_task = asyncio.create_task(drain_stderr())

    async for line in proc.stdout:          # iter protocol drains until EOF
        yield line.decode().rstrip("\n")

    await proc.wait()
    stderr = await stderr_task
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, "claude", stderr=stderr)
```

**Windows note:** Python 3.10+ on Windows uses `ProactorEventLoop` by default, which supports subprocess pipes. No explicit policy set needed unless supporting Python < 3.10.

### Pattern 2: NDJSON Stream Processing

**What:** Claude CLI `--output-format stream-json` emits one JSON object per line. Parse each line and extract content_block_delta events for text, and the final ResultMessage for the complete response.

**When to use:** Whenever streaming output from Claude CLI.

**Key message types (from official Claude Code Agent SDK docs):**
- `system` — session initialization
- `assistant` — complete message with content blocks (when not streaming partial)
- `result` — final result with cost/usage info
- `stream_event` — partial streaming events (only with `--include-partial-messages`)

**Standard invocation for agents (non-interactive, text output):**
```python
# Source: https://code.claude.com/docs/en/cli-reference
cmd = [
    "claude", "-p",
    "--output-format", "stream-json",
    "--system-prompt-file", "/path/to/context.txt",
    "--dangerously-skip-permissions",  # for automated non-interactive use
    prompt_text
]
```

**Caution:** The exact shape of NDJSON messages from direct `claude -p --output-format stream-json` (CLI mode, not Agent SDK) has not been fully verified hands-on. The STATE.md flags this as needing verification in Phase 1. The Agent SDK docs describe `StreamEvent` but direct CLI output may differ. Treat per-line JSON structure as LOW confidence until first run.

### Pattern 3: Async SQLite with Repository

**What:** Open a single `aiosqlite` connection at app startup, share it via dependency injection, use a per-table repository class with typed methods.

**When to use:** All session persistence.

**Example:**
```python
# Source: https://aiosqlite.omnilib.dev/en/stable/
import aiosqlite
from dataclasses import dataclass
from typing import Optional

@dataclass
class Session:
    id: Optional[int]
    name: str
    created_at: str
    project_path: str

class SessionRepository:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def create(self, session: Session) -> int:
        cursor = await self._db.execute(
            "INSERT INTO sessions (name, created_at, project_path) VALUES (?,?,?)",
            (session.name, session.created_at, session.project_path),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get(self, session_id: int) -> Optional[Session]:
        async with self._db.execute(
            "SELECT id, name, created_at, project_path FROM sessions WHERE id=?",
            (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return Session(*row) if row else None
```

### Pattern 4: Tenacity Retry Wrapping Async Subprocess

**What:** Wrap the Claude CLI invocation coroutine with Tenacity's `@retry` decorator configured for 3 attempts and exponential backoff with jitter.

**When to use:** Every Claude CLI call.

**Example:**
```python
# Source: https://tenacity.readthedocs.io/en/stable/
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=1, max=10),
    retry=retry_if_exception_type((subprocess.CalledProcessError, OSError)),
    reraise=True,
)
async def invoke_claude(args: list[str]) -> str:
    """Collect all text from a Claude CLI run, retry on failure."""
    output_chunks = []
    async for line in run_claude(args):
        data = json.loads(line)
        # extract text from assistant messages
        if data.get("type") == "assistant":
            for block in data.get("message", {}).get("content", []):
                if block.get("type") == "text":
                    output_chunks.append(block["text"])
    return "".join(output_chunks)
```

### Pattern 5: Section Extraction with Regex Fallback

**What:** Match known uppercase section headers (GOAL:, TASKS:, etc.) using a single `re.split` or `re.findall` on the raw text. Fall back to returning the full text under a synthetic "CONTENT" key when no sections match.

**When to use:** Parsing agent output after each Claude CLI run.

**Example:**
```python
import re
from typing import dict

SECTION_RE = re.compile(
    r'^([A-Z][A-Z\s]+?):\s*$',
    re.MULTILINE,
)

def extract_sections(text: str) -> dict[str, str]:
    """Return dict of section_name -> content. Falls back to {'CONTENT': text}."""
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        return {"CONTENT": text.strip()}

    sections = {}
    for i, match in enumerate(matches):
        header = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[header] = text[start:end].strip()
    return sections
```

### Pattern 6: Stack Detection via File Heuristics

**What:** Walk the project root directory and check for indicator files to infer stack. Produce a structured context block injected into system prompts.

**When to use:** Before every agent invocation (INFR-09).

**Stack Indicators:**
```python
STACK_INDICATORS = {
    "Python": ["requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"],
    "Node.js": ["package.json"],
    "Rust": ["Cargo.toml"],
    "Go": ["go.mod"],
    "Java": ["pom.xml", "build.gradle"],
    "Ruby": ["Gemfile"],
    "Docker": ["Dockerfile", "docker-compose.yml"],
}
```

**Context block format for system prompt:**
```
=== WORKSPACE CONTEXT ===
Project path: /home/user/myproject
Detected stack: Python, Docker
Key files:
  - requirements.txt
  - src/main.py
  - Dockerfile
Session history: 3 previous sessions
=========================
```

### Anti-Patterns to Avoid

- **Calling `process.wait()` before draining stdout/stderr:** Deadlocks when pipe buffer fills. Always drain first.
- **Blocking `subprocess.run()` in asyncio:** Blocks the entire event loop. Use `asyncio.create_subprocess_exec` exclusively.
- **Opening a new aiosqlite connection per query:** Creates file contention and overhead. Share one connection for the app lifetime.
- **Hand-rolling retry with `asyncio.sleep` loops:** Complex to get right (jitter, backoff cap, stop conditions). Use tenacity.
- **Using `--output-format text` for programmatic use:** Produces unstructured text with no reliable cost/token info. Use `stream-json`.
- **Scanning the entire filesystem for context:** Slow and noisy. Limit to project root + 2 directory levels.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Retry with exponential backoff | Custom `for attempt in range(3)` loop | `tenacity` | Jitter, reraise, async support, configurable stop conditions all solved |
| Async SQLite access | `sqlite3` with `run_in_executor` | `aiosqlite` | aiosqlite's shared thread model prevents concurrent write corruption |
| Subprocess pipe deadlock prevention | Custom buffer flushing | `readline()` loop draining before `wait()` | The documented safe pattern; deviation causes hard-to-reproduce bugs |
| JSON line parsing | Custom stream accumulator | `json.loads(line)` per line | Each NDJSON line is a complete self-contained JSON object |

**Key insight:** All four core problems have established Python solutions that handle the subtle edge cases. The only genuinely project-specific code is the section parser and stack detector.

---

## Common Pitfalls

### Pitfall 1: Windows ProactorEventLoop Not Set

**What goes wrong:** `NotImplementedError: asyncio subprocess is only available on Unix` or subprocess hangs at creation.

**Why it happens:** `SelectorEventLoop` (old default before Python 3.10) does not support subprocess piping on Windows.

**How to avoid:** Use Python 3.10+ where `ProactorEventLoop` is default. Add an explicit guard in the entry point:
```python
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
```

**Warning signs:** `NotImplementedError` at `create_subprocess_exec`, or immediate empty output from subprocess.

### Pitfall 2: Claude CLI Prompt Mode vs Interactive Mode

**What goes wrong:** Claude CLI opens an interactive session, waiting for terminal input, instead of processing the prompt and exiting.

**Why it happens:** Forgetting the `-p` flag. Without `-p`, `claude "query"` starts an interactive TUI session that blocks.

**How to avoid:** Always include `-p` for programmatic use: `claude -p "prompt"`.

**Warning signs:** Process never terminates; subprocess stdout never closes.

### Pitfall 3: stream-json Lines Contain Non-JSON Content

**What goes wrong:** `json.JSONDecodeError` when parsing stdout lines from Claude CLI.

**Why it happens:** Claude CLI may emit ANSI escape codes, blank lines, or diagnostic messages before the first JSON object if not invoked cleanly. Also, partial lines during piping.

**How to avoid:** Strip lines, skip blank lines, wrap `json.loads` in try/except and log parse errors rather than crashing:
```python
line = line.strip()
if not line:
    continue
try:
    data = json.loads(line)
except json.JSONDecodeError:
    log.warning("non-JSON line: %s", line)
    continue
```

**Warning signs:** Parse errors on first few lines.

### Pitfall 4: Concurrent aiosqlite Writes Without Locking

**What goes wrong:** `sqlite3.OperationalError: database is locked` when multiple coroutines write simultaneously.

**Why it happens:** SQLite's write lock is per-database-file; concurrent writes from different `aiosqlite.Connection` objects fight for the lock.

**How to avoid:** Use a single shared connection throughout the application. The aiosqlite thread model serializes writes through its internal queue.

**Warning signs:** Intermittent lock errors, especially during concurrent agent runs.

### Pitfall 5: Section Parser Breaks on Mixed Case or Trailing Colons

**What goes wrong:** `extract_sections()` returns `{"CONTENT": entire_text}` instead of parsed sections.

**Why it happens:** Claude may emit `**Goal:**` (bold markdown) or `Goal:` (title case) instead of `GOAL:`.

**How to avoid:** Normalize before matching — strip markdown bold markers, uppercase the candidate header, match case-insensitively:
```python
SECTION_RE = re.compile(
    r'^\*{0,2}([A-Za-z][A-Za-z\s]+?)\*{0,2}:\s*$',
    re.MULTILINE | re.IGNORECASE,
)
```

**Warning signs:** Sections always return as CONTENT even when agent output looks structured.

### Pitfall 6: Workspace Context Exceeds Token Budget

**What goes wrong:** Context injection bloats the system prompt with thousands of file paths, approaching token limits.

**Why it happens:** Unrestricted `pathlib.Path.rglob("*")` on large projects.

**How to avoid:** Cap file listing at 200 entries; exclude `.git`, `node_modules`, `__pycache__`, `.venv`. Use `itertools.islice`:
```python
MAX_FILES = 200
EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}
```

**Warning signs:** System prompt context length warnings; Claude truncating its response.

---

## Code Examples

Verified patterns from official sources:

### Async Subprocess — Safe Streaming Pattern
```python
# Source: https://docs.python.org/3/library/asyncio-subprocess.html
import asyncio

async def stream_claude(prompt: str):
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", "--output-format", "stream-json",
        "--dangerously-skip-permissions",
        prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    # Drain stdout BEFORE wait() to avoid pipe buffer deadlock
    async for raw_line in proc.stdout:
        line = raw_line.decode().strip()
        if line:
            yield line
    await proc.wait()
```

### aiosqlite Connection Lifecycle
```python
# Source: https://aiosqlite.omnilib.dev/en/stable/
import aiosqlite

async def setup_db(path: str) -> aiosqlite.Connection:
    db = await aiosqlite.connect(path)
    await db.execute("PRAGMA journal_mode=WAL")   # Better concurrent reads
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            project_path TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS agent_outputs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES sessions(id),
            agent_type TEXT NOT NULL,   -- 'plan' | 'execute' | 'review'
            raw_output TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    await db.commit()
    return db
```

### Tenacity Retry on Async Function
```python
# Source: https://tenacity.readthedocs.io/en/stable/
from tenacity import retry, stop_after_attempt, wait_random_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=1, max=10),
    reraise=True,
)
async def invoke_claude_with_retry(args: list[str]) -> str:
    result = []
    async for line in stream_claude_args(args):
        result.append(line)
    return "\n".join(result)
```

### Workspace Context Assembly
```python
# Source: pathlib stdlib + project pattern
from pathlib import Path
import itertools

EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}
STACK_INDICATORS = {
    "Python": ["requirements.txt", "pyproject.toml", "setup.py"],
    "Node.js": ["package.json"],
    "Rust": ["Cargo.toml"],
    "Go": ["go.mod"],
    "Docker": ["Dockerfile", "docker-compose.yml"],
}
MAX_FILES = 200

def assemble_workspace_context(project_path: str) -> str:
    root = Path(project_path)
    stacks = [
        name for name, indicators in STACK_INDICATORS.items()
        if any((root / f).exists() for f in indicators)
    ]
    def iter_files():
        for p in root.rglob("*"):
            if any(excl in p.parts for excl in EXCLUDE_DIRS):
                continue
            if p.is_file():
                yield str(p.relative_to(root))

    files = list(itertools.islice(iter_files(), MAX_FILES))
    return (
        "=== WORKSPACE CONTEXT ===\n"
        f"Project path: {project_path}\n"
        f"Detected stack: {', '.join(stacks) or 'unknown'}\n"
        f"Files ({len(files)} shown):\n"
        + "\n".join(f"  - {f}" for f in files)
        + "\n=========================\n"
    )
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `subprocess.run()` in asyncio apps | `asyncio.create_subprocess_exec` | Python 3.5+ | Non-blocking; required for TUI integration |
| `SelectorEventLoop` on Windows | `ProactorEventLoop` (default) | Python 3.10 | Subprocess PIPE support on Windows without manual policy change |
| Manual retry loops | `tenacity` with async support | Library v5+ | Handles jitter, stop conditions, exception filtering declaratively |
| Raw `sqlite3` with `run_in_executor` | `aiosqlite` shared thread model | 2018+ | True async surface without thread management |
| `--output-format text` for scripting | `--output-format stream-json` | Claude Code 2024 | Machine-readable, includes token usage, structured message types |

**Deprecated/outdated:**
- `asyncio.get_event_loop()`: Use `asyncio.run()` as the entry point (Python 3.10+).
- `loop.run_until_complete()`: Replaced by `asyncio.run()` in modern code.
- Separate `asyncio.WindowsProactorEventLoopPolicy()` set: Unnecessary on Python 3.10+.

---

## Open Questions

1. **Exact NDJSON message structure from direct `claude -p --output-format stream-json`**
   - What we know: The Agent SDK docs describe `StreamEvent`, `AssistantMessage`, `ResultMessage` types. The GitHub issue [#24596](https://github.com/anthropics/claude-code/issues/24596) confirms the event type reference is underdocumented.
   - What's unclear: Whether the direct CLI emits the same envelope format as the SDK, or if it differs when invoked as a subprocess vs. the Python SDK wrapper.
   - Recommendation: First task in Wave 1 should be a 5-line test script that runs `claude -p --output-format stream-json "say hello"` and dumps all raw lines. Verify message types before building the parser. This was also flagged as a blocker in STATE.md.

2. **`--dangerously-skip-permissions` scope on Windows**
   - What we know: The flag exists and suppresses permission prompts for automated use.
   - What's unclear: Whether it requires a specific Claude Code version or configuration on Windows, and if there are alternative permission modes (`--permission-mode plan`) that are safer for this use case.
   - Recommendation: Test both flags in Phase 1. Consider `--permission-mode plan` as a safer alternative that still avoids interactive prompts.

3. **Claude CLI PATH availability in Windows subprocess env**
   - What we know: `claude` is installed via npm/Node.js and must be on PATH.
   - What's unclear: Whether `asyncio.create_subprocess_exec("claude", ...)` finds the npm-installed binary in Windows when launched from within a Python process.
   - Recommendation: Use `shutil.which("claude")` to resolve the full path at startup; raise a clear error if not found.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (latest stable) |
| Config file | `pytest.ini` or `pyproject.toml [tool.pytest.ini_options]` — Wave 0 |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFR-01 | Claude subprocess launched, streams lines without deadlock | integration | `pytest tests/test_runner.py -x` | Wave 0 |
| INFR-01 | Stream terminates cleanly on process exit | unit | `pytest tests/test_runner.py::test_stream_terminates -x` | Wave 0 |
| INFR-03 | Session saved to SQLite and retrieved after re-open | integration | `pytest tests/test_db.py -x` | Wave 0 |
| INFR-03 | agent_outputs stored and linked to session | unit | `pytest tests/test_db.py::test_agent_output_persistence -x` | Wave 0 |
| INFR-05 | Failed call retried up to 3 times with increasing delay | unit (mock) | `pytest tests/test_runner.py::test_retry_behavior -x` | Wave 0 |
| INFR-05 | After 3 failures error is surfaced, not swallowed | unit (mock) | `pytest tests/test_runner.py::test_retry_exhausted -x` | Wave 0 |
| INFR-09 | Workspace context includes project path, stack, files | unit | `pytest tests/test_context.py -x` | Wave 0 |
| INFR-09 | Context excludes .git/node_modules and caps at 200 files | unit | `pytest tests/test_context.py::test_context_excludes -x` | Wave 0 |
| INFR-01 | Section parser extracts GOAL/TASKS from well-formed text | unit | `pytest tests/test_parser.py -x` | Wave 0 |
| INFR-01 | Section parser falls back to CONTENT on unstructured text | unit | `pytest tests/test_parser.py::test_fallback -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/ -x -q`
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_runner.py` — covers INFR-01, INFR-05
- [ ] `tests/test_db.py` — covers INFR-03
- [ ] `tests/test_context.py` — covers INFR-09
- [ ] `tests/test_parser.py` — covers section extraction (INFR-01 output parsing)
- [ ] `tests/conftest.py` — shared fixtures: in-memory aiosqlite DB, mock subprocess
- [ ] `pytest.ini` or `pyproject.toml` with `asyncio_mode = "auto"` for pytest-asyncio
- [ ] Framework install: `pip install pytest pytest-asyncio`

---

## Sources

### Primary (HIGH confidence)

- [Python asyncio-subprocess official docs](https://docs.python.org/3/library/asyncio-subprocess.html) — deadlock risks, Windows ProactorEventLoop, `readline()` streaming pattern
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference) — `-p` flag, `--output-format stream-json`, `--system-prompt-file`, `--dangerously-skip-permissions`, `--append-system-prompt`
- [Claude Agent SDK streaming docs](https://platform.claude.com/docs/en/agent-sdk/streaming-output) — StreamEvent types, message flow order, content_block_delta, ResultMessage
- [aiosqlite official docs](https://aiosqlite.omnilib.dev/en/stable/) — async connection model, context manager pattern
- [tenacity official docs](https://tenacity.readthedocs.io/en/stable/) — `@retry`, `stop_after_attempt`, `wait_random_exponential`, async coroutine support

### Secondary (MEDIUM confidence)

- [GitHub issue #24596 — CLI stream-json event type reference](https://github.com/anthropics/claude-code/issues/24596) — confirms event type documentation gap; verified it exists
- [aiosqlite PyPI](https://pypi.org/project/aiosqlite/) — version 0.20+ confirmed active

### Tertiary (LOW confidence)

- WebSearch results on stack detection patterns — general heuristics, not from a specific authoritative library; pattern is self-constructed from common knowledge

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — All libraries verified against official docs and PyPI
- Architecture: HIGH for subprocess and SQLite patterns (official docs); MEDIUM for section parser pattern (project-specific, regex approach derived from requirements)
- Pitfalls: HIGH for subprocess deadlocks (official docs), MEDIUM for Claude CLI stream-json message format (partially unverified, flagged as open question)

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (stable domain; Claude CLI output format could change faster — re-verify if updating Claude Code version)
