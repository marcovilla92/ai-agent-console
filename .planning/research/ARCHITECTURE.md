# Architecture Research

**Domain:** Multi-agent AI orchestration TUI (terminal UI)
**Researched:** 2026-03-11
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
+---------------------------------------------------------------+
|                      TUI Layer (Textual)                      |
|  +----------+ +----------+ +----------+ +----------+         |
|  | Prompt   | | Plan     | | Execute  | | Review   |         |
|  | Panel    | | Panel    | | Panel    | | Panel    |         |
|  +----+-----+ +----+-----+ +----+-----+ +----+-----+         |
|       |            |            |            |                |
|  +----+------------+------------+------------+----+           |
|  |              Status Bar / Footer               |           |
|  +------------------------------------------------+           |
+-------------------------------+-------------------------------+
                                |
                    Custom Messages (up)
                    Reactive attrs (down)
                                |
+-------------------------------v-------------------------------+
|                    Orchestrator Engine                         |
|  +------------------+  +------------------+                   |
|  | State Machine    |  | Agent Router     |                   |
|  | (session state)  |  | (next agent)     |                   |
|  +--------+---------+  +--------+---------+                   |
|           |                      |                            |
|  +--------v----------------------v---------+                  |
|  |           Agent Runner                  |                  |
|  |  (asyncio subprocess + streaming)       |                  |
|  +--------+---+---+---+------------------+|                  |
|           |   |   |   |                   |                   |
+-------------------------------+-------------------------------+
                                |
              asyncio.create_subprocess_exec
                                |
+-------------------------------v-------------------------------+
|                    Agent Layer                                 |
|  +----------+  +-----------+  +-----------+                   |
|  | PLAN     |  | EXECUTE   |  | REVIEW    |                   |
|  | Agent    |  | Agent     |  | Agent     |                   |
|  | (claude) |  | (claude)  |  | (claude)  |                   |
|  +----------+  +-----------+  +-----------+                   |
|  Each agent = system prompt + output contract                 |
+-------------------------------+-------------------------------+
                                |
+-------------------------------v-------------------------------+
|                  Persistence Layer                             |
|  +-------------------+  +------------------+                  |
|  | SessionStore      |  | WorkspaceContext |                  |
|  | (SQLite)          |  | (project files)  |                  |
|  +-------------------+  +------------------+                  |
+---------------------------------------------------------------+
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **TUI Layer** | Rendering panels, capturing input, streaming output display | Textual App with compound widgets, CSS grid layout |
| **Orchestrator Engine** | Deciding which agent runs next, managing session state transitions | State machine + Claude CLI call for routing decisions |
| **Agent Runner** | Launching Claude CLI subprocesses, streaming stdout line-by-line back to TUI | `asyncio.create_subprocess_exec` wrapped in Textual Workers |
| **Agent Definitions** | System prompts and output contracts per agent type | Python dataclasses or config files defining prompt templates |
| **State Machine** | Tracking session lifecycle (IDLE -> PLANNING -> EXECUTING -> REVIEWING -> DONE) | Enum-based FSM with explicit transitions |
| **Session Store** | Persisting prompts, plans, outputs, reviews, session metadata | SQLite via `aiosqlite` |
| **Workspace Context** | Shared context passed to every agent (project path, stack, history) | Dataclass assembled before each agent call |

## Recommended Project Structure

```
ai_agent_console/
├── app.py                  # Textual App entry point, compose(), key bindings
├── config.py               # Settings, paths, constants
├── models/                 # Data structures
│   ├── session.py          # Session, AgentOutput, WorkspaceContext dataclasses
│   ├── state.py            # SessionState enum, FSM transitions
│   └── agents.py           # AgentDefinition (name, system_prompt, output_contract)
├── orchestrator/           # Core engine
│   ├── engine.py           # Orchestrator: decides next agent, manages flow
│   ├── router.py           # Agent routing logic (Claude CLI call or rule-based)
│   └── runner.py           # AgentRunner: subprocess launch, streaming, retry
├── agents/                 # Agent prompt definitions
│   ├── plan.py             # PLAN agent system prompt + contract
│   ├── execute.py          # EXECUTE agent system prompt + contract
│   └── review.py           # REVIEW agent system prompt + contract
├── ui/                     # Textual widgets
│   ├── panels/             # One widget per panel
│   │   ├── prompt_panel.py # User input panel
│   │   ├── plan_panel.py   # Plan display panel
│   │   ├── execute_panel.py# Execution output panel
│   │   └── review_panel.py # Review display panel
│   ├── status_bar.py       # Current agent, state, step info
│   ├── messages.py         # Custom Textual Messages (AgentStarted, StreamChunk, AgentCompleted, etc.)
│   └── theme.py            # Centralized CSS/styling
├── persistence/            # Storage
│   ├── database.py         # SQLite schema, migrations, CRUD
│   └── file_store.py       # Saving outputs to project folder on disk
├── console.tcss            # Textual CSS stylesheet
└── __main__.py             # Entry point
```

### Structure Rationale

- **models/**: Pure data structures with no dependencies on UI or persistence. Every other layer imports from here, nothing imports into here. This is the gravity center.
- **orchestrator/**: The brain. Separated from UI so it can be tested independently. `engine.py` owns the loop, `runner.py` owns subprocess management, `router.py` owns "what's next" decisions.
- **agents/**: Just data (prompts and contracts). No logic. Adding a new agent = adding one file here plus registering it in the router.
- **ui/**: Textual widgets that know how to render data and emit messages. They do not call the orchestrator directly -- they post messages up, and the App dispatches.
- **persistence/**: Isolated storage layer. Could swap SQLite for anything without touching other layers.

## Architectural Patterns

### Pattern 1: Message-Driven TUI-to-Orchestrator Communication

**What:** The TUI layer communicates with the orchestrator exclusively through Textual's message system. Panels post custom messages upward (e.g., `PromptSubmitted`, `RetryRequested`). The App handles these messages and calls orchestrator methods. The orchestrator pushes updates back via reactive attributes or by posting messages that panels listen to.

**When to use:** Always. This is the core integration pattern.

**Trade-offs:** Clean separation and testability. Slightly more boilerplate than direct calls, but prevents the spaghetti that inevitably results from widgets calling engine methods directly.

**Example:**
```python
# ui/messages.py
from textual.message import Message

class PromptSubmitted(Message):
    def __init__(self, text: str, project_name: str) -> None:
        super().__init__()
        self.text = text
        self.project_name = project_name

class StreamChunk(Message):
    def __init__(self, agent: str, content: str) -> None:
        super().__init__()
        self.agent = agent
        self.content = content

class AgentCompleted(Message):
    def __init__(self, agent: str, output: str, success: bool) -> None:
        super().__init__()
        self.agent = agent
        self.output = output
        self.success = success

# app.py
class AgentConsole(App):
    def on_prompt_submitted(self, event: PromptSubmitted) -> None:
        self.run_worker(self.orchestrator.start_session(event.text, event.project_name))

    def on_agent_completed(self, event: AgentCompleted) -> None:
        self.run_worker(self.orchestrator.handle_completion(event.agent, event.output))
```

### Pattern 2: State Machine for Session Lifecycle

**What:** The session lifecycle is an explicit finite state machine with named states and valid transitions. The orchestrator checks the current state before performing any action. Invalid transitions raise errors rather than silently proceeding.

**When to use:** Always. The pipeline (PROMPT -> PLAN -> EXECUTE -> REVIEW -> DONE/ITERATE) maps naturally to an FSM.

**Trade-offs:** Rigid but predictable. Prevents impossible states like "reviewing before planning". The AI-driven router operates within the FSM's constraints -- it chooses the next agent, but only from valid transitions.

**Example:**
```python
from enum import Enum, auto

class SessionState(Enum):
    IDLE = auto()
    PLANNING = auto()
    EXECUTING = auto()
    REVIEWING = auto()
    ITERATING = auto()   # Re-entering PLAN or EXECUTE after review
    COMPLETED = auto()
    ERROR = auto()

VALID_TRANSITIONS = {
    SessionState.IDLE: {SessionState.PLANNING},
    SessionState.PLANNING: {SessionState.EXECUTING, SessionState.ERROR},
    SessionState.EXECUTING: {SessionState.REVIEWING, SessionState.ERROR},
    SessionState.REVIEWING: {SessionState.COMPLETED, SessionState.ITERATING, SessionState.ERROR},
    SessionState.ITERATING: {SessionState.PLANNING, SessionState.EXECUTING},
    SessionState.ERROR: {SessionState.IDLE, SessionState.PLANNING, SessionState.EXECUTING},
}
```

### Pattern 3: Streaming Subprocess via Async Workers

**What:** Each agent invocation launches a Claude CLI subprocess using `asyncio.create_subprocess_exec`. Output is read line-by-line from stdout and posted back to the TUI as `StreamChunk` messages. The Worker API handles cancellation and lifecycle.

**When to use:** Every agent call. This is the only way to get real-time streaming into the TUI.

**Trade-offs:** Requires careful buffer management. Must read stdout before/while waiting (not after) to avoid deadlocks. The `exclusive=True` worker flag ensures only one agent runs at a time (unless parallel mode is enabled).

**Example:**
```python
# orchestrator/runner.py
import asyncio
from textual.app import App

class AgentRunner:
    def __init__(self, app: App):
        self.app = app

    async def run_agent(self, agent_def: "AgentDefinition", context: "WorkspaceContext") -> str:
        cmd = [
            "claude", "--dangerously-skip-permissions",
            "-p", agent_def.build_prompt(context),
            "--output-format", "text",
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        output_lines = []
        async for line in process.stdout:
            text = line.decode().rstrip()
            output_lines.append(text)
            self.app.post_message(StreamChunk(agent=agent_def.name, content=text))

        await process.wait()
        full_output = "\n".join(output_lines)

        if process.returncode != 0:
            stderr = await process.stderr.read()
            raise AgentError(agent_def.name, stderr.decode())

        return full_output
```

### Pattern 4: Structured Output Contracts

**What:** Each agent's system prompt enforces a specific output format with named sections (e.g., GOAL, TASKS, ARCHITECTURE for the PLAN agent). The orchestrator parses these sections from raw text output using simple delimiter-based parsing, not JSON. This keeps agent prompts natural while still enabling programmatic extraction.

**When to use:** Every agent. The orchestrator and the REVIEW agent both consume structured sections from other agents' outputs.

**Trade-offs:** Text section parsing is fragile compared to JSON but far more reliable in practice with LLMs. Claude consistently produces markdown-style sections when instructed. A thin parser that looks for `## SECTION_NAME` headers is sufficient.

**Example:**
```python
# models/agents.py
from dataclasses import dataclass, field

@dataclass
class AgentDefinition:
    name: str
    system_prompt: str
    output_sections: list[str]  # Expected section headers

    def build_prompt(self, context: "WorkspaceContext") -> str:
        return f"{self.system_prompt}\n\n## Context\n{context.to_prompt()}"

PLAN_AGENT = AgentDefinition(
    name="PLAN",
    system_prompt="You are a planning agent...",
    output_sections=["GOAL", "TASKS", "ARCHITECTURE", "FILES", "HANDOFF"],
)

# Simple section parser
def parse_sections(output: str, expected: list[str]) -> dict[str, str]:
    sections = {}
    current = None
    lines = []
    for line in output.split("\n"):
        header = line.strip().lstrip("#").strip()
        if header in expected:
            if current:
                sections[current] = "\n".join(lines).strip()
            current = header
            lines = []
        elif current:
            lines.append(line)
    if current:
        sections[current] = "\n".join(lines).strip()
    return sections
```

### Pattern 5: AI-Driven Router (Orchestrator-as-Agent)

**What:** After each agent completes, the orchestrator calls Claude CLI with a meta-prompt: "Given the current state, the agent's output, and the review (if any), what should happen next?" The response is a structured decision (next agent, or completion). This is distinct from the agents themselves -- it's a lightweight routing call.

**When to use:** After every agent completion. The router decides: proceed to next stage, iterate, or finish.

**Trade-offs:** An LLM call for routing adds latency (~2-5s). But it handles ambiguity that rule-based routing cannot (e.g., "this plan is incomplete, should we re-plan or proceed?"). For v1, keep a rule-based fallback for when the routing call fails.

**Example:**
```python
# orchestrator/router.py
ROUTER_PROMPT = """You are an orchestrator deciding the next step.
Current state: {state}
Last agent: {agent}
Last output summary: {summary}

Valid next steps: {valid_transitions}

Respond with exactly one of: {valid_transitions}
If the output quality is insufficient, choose to iterate.
"""
```

## Data Flow

### Request Flow (Happy Path)

```
User types prompt in PromptPanel
    |
    v  [PromptSubmitted message]
App.on_prompt_submitted()
    |
    v
Orchestrator.start_session(prompt, project_name)
    |-- Creates Session in SQLite
    |-- Builds WorkspaceContext
    |-- Sets state: IDLE -> PLANNING
    |
    v
AgentRunner.run_agent(PLAN_AGENT, context)
    |-- Launches `claude` subprocess
    |-- Streams stdout line-by-line
    |       |
    |       v  [StreamChunk messages]
    |   PlanPanel.on_stream_chunk() -> appends text
    |
    v  [AgentCompleted message]
Orchestrator.handle_completion("PLAN", output)
    |-- Parses sections from output
    |-- Persists to SQLite
    |-- Calls Router: "what next?"
    |-- Router says: EXECUTING
    |-- Sets state: PLANNING -> EXECUTING
    |
    v
AgentRunner.run_agent(EXECUTE_AGENT, context + plan)
    |-- Same streaming pattern
    |
    v  [AgentCompleted message]
Orchestrator.handle_completion("EXECUTE", output)
    |-- Router says: REVIEWING
    |-- Sets state: EXECUTING -> REVIEWING
    |
    v
AgentRunner.run_agent(REVIEW_AGENT, context + plan + code)
    |-- Same streaming pattern
    |
    v  [AgentCompleted message]
Orchestrator.handle_completion("REVIEW", output)
    |-- Parses DECISION section
    |-- Router decides: COMPLETED or ITERATING
    |-- If ITERATING: user confirms, then re-enters PLANNING or EXECUTING
    |-- If COMPLETED: saves final outputs to project folder
```

### State Management

```
Session (in-memory + SQLite)
    |
    +-- state: SessionState enum (FSM)
    +-- prompt: str (original user input)
    +-- project_name: str
    +-- project_path: Path
    +-- history: list[AgentOutput]  (append-only log of all agent runs)
    +-- workspace_context: WorkspaceContext
            |
            +-- project_path: Path
            +-- existing_files: list[str]
            +-- stack: str (detected or specified)
            +-- agent_history: list[AgentOutput] (fed to next agent)
```

### Key Data Flows

1. **Prompt -> Agent context:** User prompt is combined with WorkspaceContext into a single prompt string that gets passed to `claude` via `-p` flag. Each subsequent agent receives the accumulated history of all previous agent outputs.

2. **Streaming -> UI:** Subprocess stdout is read async line-by-line. Each line is posted as a `StreamChunk` message. The target panel appends the text. This gives real-time feedback during the 30-120 second agent runs.

3. **Agent output -> Persistence:** On agent completion, the full output text plus parsed sections are saved to SQLite. The raw output is also written to the project folder on disk for later reference.

4. **Review -> Iteration decision:** The REVIEW agent's output includes a DECISION section. The router (or a simple parse) extracts this. If "iterate", the orchestrator transitions to ITERATING and asks the user to confirm before re-running PLAN or EXECUTE with the review feedback injected into context.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1 user, sequential agents | Current architecture. Single subprocess at a time. Simple and sufficient. |
| 1 user, parallel agents | Run PLAN for multiple sub-tasks concurrently via multiple Workers. Needs careful state tracking per sub-task. |
| Multiple projects | Each project = separate session in SQLite. No architectural change needed. Tab-based UI for switching. |

### Scaling Priorities

1. **First bottleneck: Agent response time.** Claude CLI calls take 30-120s. The architecture already handles this via streaming. No fix needed -- this is inherent to LLM latency.
2. **Second bottleneck: Context window limits.** As iteration cycles grow, the accumulated history gets too large for Claude's context. Mitigation: summarize older agent outputs before injecting into context. Keep last 2 full outputs, summarize the rest.

## Anti-Patterns

### Anti-Pattern 1: Widgets Calling Orchestrator Directly

**What people do:** Panel widgets import the orchestrator and call `orchestrator.run_agent()` directly from button handlers.
**Why it's wrong:** Creates tight coupling. Widgets become untestable without a real orchestrator. Multiple panels might trigger conflicting agent runs. State becomes unpredictable.
**Do this instead:** Widgets post messages. The App (single coordinator) handles messages and calls the orchestrator. One place controls flow.

### Anti-Pattern 2: Blocking Subprocess Calls

**What people do:** Use `subprocess.run()` or synchronous `Popen` in a Textual app.
**Why it's wrong:** Freezes the entire TUI for 30-120 seconds. No streaming. No cancel button. User thinks it crashed.
**Do this instead:** Use `asyncio.create_subprocess_exec` inside a Textual Worker (async, not thread). Read stdout in an async for loop. Post `StreamChunk` messages for each line.

### Anti-Pattern 3: JSON Output Contracts

**What people do:** Ask Claude to return JSON-only output, then parse it.
**Why it's wrong:** LLMs frequently produce invalid JSON (trailing commas, unescaped strings, markdown wrapping). Parsing failures cause agent failures. JSON output is also unreadable in the TUI during streaming.
**Do this instead:** Use markdown-section-based contracts (`## SECTION_NAME`). Parse with simple string splitting. Display streaming text naturally. Fall back gracefully if a section is missing.

### Anti-Pattern 4: Stateless Orchestrator

**What people do:** Treat each agent call independently with no session state tracking.
**Why it's wrong:** Lose the ability to iterate. Cannot resume interrupted sessions. Cannot enforce valid transitions (e.g., accidentally executing before planning).
**Do this instead:** Maintain an explicit FSM with SessionState enum. Persist state transitions to SQLite. Validate every transition against VALID_TRANSITIONS.

### Anti-Pattern 5: Monolithic Agent Prompts

**What people do:** Stuff all context, history, and instructions into a single enormous system prompt.
**Why it's wrong:** Hits context window limits fast. Agent performance degrades with prompt length. Impossible to debug which part of the prompt caused bad output.
**Do this instead:** Compose prompts from small, focused pieces: system prompt (static) + output contract (static) + workspace context (dynamic) + relevant prior outputs (dynamic, summarized if old).

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Claude CLI | `asyncio.create_subprocess_exec` with stdout PIPE | Always use `--dangerously-skip-permissions`. Use `--output-format text` for streaming-friendly output. Retry 3x on non-zero exit. |
| File system | `pathlib.Path` / `aiofiles` | Project folders created at `Documents/VisualStudio/{project_name}`. Outputs saved as `.md` files per agent run. |
| SQLite | `aiosqlite` (async wrapper) | Single DB file in app data dir. One table per entity: sessions, agent_outputs, workspace_contexts. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| UI <-> Orchestrator | Textual Messages (up) + reactive attributes (down) | Never import orchestrator in widget code. App is the bridge. |
| Orchestrator <-> AgentRunner | Direct async method calls | Runner is owned by orchestrator. Returns full output string. |
| Orchestrator <-> Persistence | Direct async method calls via repository pattern | Orchestrator calls `session_store.save_output()`, never raw SQL. |
| AgentRunner <-> Claude CLI | Subprocess with PIPE | One subprocess per agent invocation. Killed on cancellation. |

## Build Order (Dependency Chain)

The following build order respects component dependencies:

1. **Models first** (session, state, agent definitions) -- zero dependencies, everything else imports these
2. **Persistence layer** (SQLite schema, CRUD) -- depends only on models
3. **Agent definitions** (prompts, contracts) -- depends only on models
4. **Agent Runner** (subprocess + streaming) -- depends on models + needs a way to post messages
5. **Orchestrator engine** (state machine + routing) -- depends on runner + persistence + models
6. **TUI panels** (individual widgets) -- depends on models for display, messages for communication
7. **App shell** (compose, keybindings, message handlers) -- wires everything together
8. **Router intelligence** (AI-driven routing via Claude CLI) -- can start rule-based, upgrade to AI-driven later

**Key insight:** The orchestrator and TUI are independent of each other until the App wires them together. This means they can be developed and tested in parallel after the models layer exists.

## Sources

- [Textual Workers Guide](https://textual.textualize.io/guide/workers/) -- Worker API, async/thread patterns, exclusive workers
- [Textual Events and Messages Guide](https://textual.textualize.io/guide/events/) -- Custom message pattern, handler naming
- [Textual Widgets Guide](https://textual.textualize.io/guide/widgets/) -- Compose pattern, compound widgets
- [Python asyncio Subprocess Docs](https://docs.python.org/3/library/asyncio-subprocess.html) -- create_subprocess_exec, PIPE streaming
- [Google Cloud: Choose a Design Pattern for Agentic AI](https://docs.google.com/architecture/choose-design-pattern-agentic-ai-system) -- Sequential pipeline, orchestrator patterns
- [Microsoft: AI Agent Orchestration Patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns) -- Multi-agent orchestration architectures
- [Pipeline of Agents Pattern](https://www.vitaliihonchar.com/insights/how-to-build-pipeline-of-agents) -- Sequential agent pipeline architecture
- [6 Patterns for Production Agentic Workflows](https://medium.com/@wasowski.jarek/building-ai-workflows-neither-programming-nor-prompt-engineering-cdd45d2d314a) -- State machine, sandwich pattern, immutable state

---
*Architecture research for: Multi-agent AI orchestration TUI*
*Researched: 2026-03-11*
