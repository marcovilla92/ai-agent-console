# Phase 4: Orchestrator Intelligence - Research

**Researched:** 2026-03-12
**Domain:** AI-driven workflow orchestration, state machines, Textual modal dialogs
**Confidence:** HIGH

## Summary

Phase 4 replaces the fixed sequential pipeline (PLAN -> EXECUTE -> REVIEW) with an intelligent orchestrator that uses Claude CLI to analyze agent outputs and decide the next step. The core technical challenges are: (1) making a structured Claude CLI call to get a JSON routing decision, (2) managing workflow state across iterations, (3) presenting user confirmation dialogs in the Textual TUI, and (4) enforcing cycle limits to prevent runaway loops.

The existing codebase provides strong foundations. The `runner/runner.py` module already handles Claude CLI invocation with streaming and collection. The `pipeline/runner.py` has the sequential loop and decision extraction logic that will be refactored. The `tui/streaming.py` worker pattern handles async agent execution in Textual's worker system. The key new work is: an `OrchestratorState` dataclass, an orchestrator loop that replaces the linear pipeline, a Claude CLI call with `--json-schema` for structured decisions, a Textual `ModalScreen` for user confirmation, and DB logging for orchestrator decisions.

**Primary recommendation:** Build the orchestrator as a new `pipeline/orchestrator.py` module with an `OrchestratorState` dataclass tracking iteration count, workflow history, and current agent. Use `collect_claude` with `--output-format json --json-schema` for structured routing decisions. Use Textual's `ModalScreen` for user confirmation on re-routing. Wire into the TUI by replacing `send_prompt`'s direct agent worker call with an orchestrator-driven loop.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
No hard-locked decisions from the user. All implementation decisions are at Claude's discretion per CONTEXT.md.

### Claude's Discretion
User delegated all implementation decisions to Claude. Key guidelines from CONTEXT.md:
- Replace `pipeline/runner.py`'s fixed sequential loop with orchestrator that calls Claude CLI after each agent
- Orchestrator prompt receives: agent output sections, handoff context, iteration count, workflow history
- Claude CLI returns structured decision: next_agent, reasoning, confidence
- Parse response as JSON; fall back to text extraction if JSON fails
- When REVIEW says BACK TO PLAN/EXECUTE: present decision + reasoning, user confirms with Enter or cancels with Escape
- Each iteration builds on prior context, not starts fresh
- Iteration = one full cycle that includes a REVIEW agent run
- After 3 iterations without APPROVED: halt and ask user to continue, approve manually, or stop
- Track iteration count in OrchestratorState dataclass
- Status bar shows concise orchestrator reasoning (one line)
- Full orchestrator response logged to dedicated section in session DB
- No separate panel for orchestrator visibility

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ORCH-01 | AI-driven orchestrator calls Claude CLI to analyze agent outputs and decide next agent | Claude CLI `--output-format json --json-schema` for structured decisions; `collect_claude` reuse with extra_args |
| ORCH-02 | REVIEW decision triggers re-PLAN or re-EXECUTE with user confirmation before proceeding | Textual `ModalScreen` pattern for Enter/Escape confirmation; handoff builder reuse for context accumulation |
| ORCH-03 | Cycle detection prevents infinite loops via hard iteration limit and repeated-state detection | OrchestratorState dataclass with iteration counter; 3-iteration hard limit; optional repeated-state hash check |
| ORCH-04 | Orchestrator shows decision reasoning and current workflow state in status area | Existing `StatusBar.set_status()` with orchestrator reasoning; new DB table for full decision logging |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12+ | Runtime | Already in use |
| Textual | 8.x | TUI framework (ModalScreen for dialogs) | Already in use, built-in modal support |
| aiosqlite | latest | Async SQLite for decision logging | Already in use |
| Claude CLI | latest | AI routing decisions via `--json-schema` | Already in use for agent invocation |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| json (stdlib) | - | Parse Claude CLI JSON responses | Orchestrator decision parsing |
| dataclasses (stdlib) | - | OrchestratorState, OrchestratorDecision | State tracking |
| hashlib (stdlib) | - | State hashing for repeated-state detection | Cycle detection |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Claude CLI `--json-schema` | Prompt engineering + regex parsing | Schema flag gives guaranteed structure; regex is fragile |
| Textual ModalScreen | Textual notify() | Modal blocks interaction and requires explicit choice; notify is passive |
| Custom state machine | python-statemachine lib | Overkill for 3-state routing; simple if/elif suffices |

**Installation:**
No new dependencies required. All capabilities exist in current stack.

## Architecture Patterns

### Recommended Project Structure
```
src/
  pipeline/
    orchestrator.py     # NEW: OrchestratorState, orchestrate_pipeline()
    runner.py           # KEEP: PipelineResult (may add fields)
    handoff.py          # KEEP: build_handoff() reused for iteration context
  tui/
    confirm_dialog.py   # NEW: ModalScreen for re-routing confirmation
    actions.py          # MODIFY: send_prompt routes through orchestrator
    streaming.py        # MODIFY: worker supports orchestrator-driven chaining
    status_bar.py       # KEEP: set_status() already sufficient
  db/
    schema.py           # MODIFY: add orchestrator_decisions table
    repository.py       # MODIFY: add OrchestratorDecisionRepository
```

### Pattern 1: OrchestratorState Dataclass
**What:** Frozen-ish dataclass tracking orchestrator workflow state across iterations
**When to use:** Created at pipeline start, passed through the orchestration loop
**Example:**
```python
from dataclasses import dataclass, field
from datetime import datetime, timezone

@dataclass
class OrchestratorDecision:
    """Single routing decision from Claude CLI."""
    next_agent: str          # "plan", "execute", "review", "halt"
    reasoning: str           # One-line summary
    confidence: float        # 0.0 - 1.0
    full_response: str       # Raw JSON for DB logging
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class OrchestratorState:
    """Mutable state for the orchestration loop."""
    session_id: int
    original_prompt: str
    iteration_count: int = 0          # Increments after each REVIEW
    max_iterations: int = 3
    current_agent: str = "plan"
    history: list[dict] = field(default_factory=list)  # [{agent, decision, sections_summary}]
    decisions: list[OrchestratorDecision] = field(default_factory=list)
    accumulated_handoffs: list[str] = field(default_factory=list)
    halted: bool = False
    approved: bool = False
```

### Pattern 2: Orchestrator Loop (replacing sequential pipeline)
**What:** Async loop that runs agents, calls Claude CLI for routing, and handles re-routing
**When to use:** Called from TUI `send_prompt` instead of direct agent worker
**Example:**
```python
async def orchestrate_pipeline(
    app: "AgentConsoleApp",
    prompt: str,
    db: aiosqlite.Connection,
    session_id: int,
) -> OrchestratorState:
    state = OrchestratorState(session_id=session_id, original_prompt=prompt)

    while not state.halted and not state.approved:
        # 1. Run current agent (streams to TUI panel)
        sections = await run_agent_with_streaming(app, state)

        # 2. Record in history
        state.history.append({
            "agent": state.current_agent,
            "sections_keys": list(sections.keys()),
        })

        # 3. If review just ran, increment iteration counter
        if state.current_agent == "review":
            state.iteration_count += 1

        # 4. Call Claude CLI for routing decision
        decision = await get_orchestrator_decision(state, sections)
        state.decisions.append(decision)

        # 5. Update status bar with reasoning
        app.status_bar.set_status(
            agent="orchestrator",
            state="routing",
            step=decision.reasoning,
            next_action=f"-> {decision.next_agent.upper()}",
        )

        # 6. Log decision to DB
        await log_decision(db, session_id, decision)

        # 7. Handle the decision
        if decision.next_agent == "approved":
            state.approved = True
        elif decision.next_agent in ("plan", "execute"):
            # Check iteration limit
            if state.iteration_count >= state.max_iterations:
                # Halt and ask user
                user_choice = await show_halt_dialog(app, state)
                if user_choice == "continue":
                    state.iteration_count = 0  # Reset for 3 more
                elif user_choice == "approve":
                    state.approved = True
                    break
                else:  # stop
                    state.halted = True
                    break

            # User confirmation for re-routing
            confirmed = await show_reroute_confirmation(app, decision)
            if confirmed:
                state.current_agent = decision.next_agent
                # Build accumulated context for next iteration
                state.accumulated_handoffs.append(build_handoff_from_sections(sections))
            else:
                state.halted = True
        else:
            # Normal forward progression: plan->execute->review
            state.current_agent = decision.next_agent

    return state
```

### Pattern 3: Claude CLI Structured Decision Call
**What:** Use `collect_claude` with `--output-format json --json-schema` to get structured routing
**When to use:** After each agent completes, to decide next step
**Example:**
```python
import json

ORCHESTRATOR_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "next_agent": {
            "type": "string",
            "enum": ["plan", "execute", "review", "approved"]
        },
        "reasoning": {
            "type": "string",
            "description": "One-line explanation of the routing decision"
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1
        }
    },
    "required": ["next_agent", "reasoning", "confidence"]
})

async def get_orchestrator_decision(
    state: OrchestratorState,
    latest_sections: dict[str, str],
) -> OrchestratorDecision:
    """Call Claude CLI to analyze output and decide next agent."""
    prompt = build_orchestrator_prompt(state, latest_sections)

    raw = await collect_claude(
        prompt,
        extra_args=[
            "--output-format", "json",
            "--json-schema", ORCHESTRATOR_SCHEMA,
        ],
    )

    # Parse the JSON response
    try:
        response = json.loads(raw)
        # With --output-format json, result is in structured_output field
        data = response.get("structured_output", response)
        return OrchestratorDecision(
            next_agent=data["next_agent"],
            reasoning=data["reasoning"],
            confidence=data.get("confidence", 0.5),
            full_response=raw,
        )
    except (json.JSONDecodeError, KeyError):
        # Fallback: text extraction
        return parse_decision_from_text(raw)
```

### Pattern 4: Textual ModalScreen for Confirmation
**What:** Modal dialog that blocks app interaction until user confirms/cancels re-routing
**When to use:** When orchestrator decides to re-route (BACK TO PLAN / BACK TO EXECUTE)
**Example:**
```python
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static
from textual.containers import Vertical, Horizontal

class RerouteConfirmDialog(ModalScreen[bool]):
    """Modal confirming re-routing decision."""

    DEFAULT_CSS = """
    RerouteConfirmDialog {
        align: center middle;
    }
    #dialog-box {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, agent: str, reasoning: str) -> None:
        super().__init__()
        self.agent = agent
        self.reasoning = reasoning

    def compose(self):
        with Vertical(id="dialog-box"):
            yield Label(f"Re-route to {self.agent.upper()}?")
            yield Static(self.reasoning)
            with Horizontal():
                yield Button("Confirm [Enter]", id="confirm", variant="primary")
                yield Button("Cancel [Esc]", id="cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")

    def key_enter(self) -> None:
        self.dismiss(True)

    def key_escape(self) -> None:
        self.dismiss(False)


class HaltDialog(ModalScreen[str]):
    """Modal shown when iteration limit is reached."""

    DEFAULT_CSS = """
    HaltDialog {
        align: center middle;
    }
    #halt-box {
        width: 70;
        height: auto;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, iterations: int) -> None:
        super().__init__()
        self.iterations = iterations

    def compose(self):
        with Vertical(id="halt-box"):
            yield Label(f"Reached {self.iterations} iterations without APPROVED")
            yield Static("What would you like to do?")
            with Horizontal():
                yield Button("Continue (3 more)", id="continue", variant="primary")
                yield Button("Approve Now", id="approve", variant="success")
                yield Button("Stop", id="stop", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id)
```

### Pattern 5: Async Modal Result in Worker Context
**What:** Bridge between Textual worker (async) and modal screen (event-driven)
**When to use:** When the orchestrator loop (running in a worker) needs to await a modal result
**Critical pattern:** Textual workers cannot directly push screens. Must use `app.call_from_thread` or `asyncio.Event`.
**Example:**
```python
import asyncio

async def show_reroute_confirmation(
    app: "AgentConsoleApp",
    decision: OrchestratorDecision,
) -> bool:
    """Show re-route confirmation modal and await user response."""
    result_event = asyncio.Event()
    result_holder = {"value": False}

    def on_result(confirmed: bool | None) -> None:
        result_holder["value"] = bool(confirmed)
        result_event.set()

    # Push screen from the main thread
    app.call_from_thread(
        app.push_screen,
        RerouteConfirmDialog(decision.next_agent, decision.reasoning),
        on_result,
    )
    await result_event.wait()
    return result_holder["value"]
```

### Anti-Patterns to Avoid
- **Rebuilding prompt from scratch each iteration:** Each re-routed agent MUST receive original prompt + all prior handoffs + review feedback. Accumulated context is critical.
- **Blocking the TUI event loop:** The orchestrator loop MUST run in a Textual worker, never on the main thread. Modal dialogs bridge via events.
- **Parsing Claude output with regex for routing:** Use `--json-schema` for guaranteed structure. Regex fallback exists but should rarely activate.
- **Resetting state between iterations:** The OrchestratorState is mutable and persists across the entire workflow. History, handoffs, and decisions accumulate.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structured JSON from Claude | Regex parsing of freeform text | `--output-format json --json-schema` | Guaranteed schema compliance, no parsing fragility |
| Modal confirmation dialogs | Custom overlay widgets | Textual `ModalScreen` | Built-in blocking, key handling, transparency |
| Retry on Claude CLI failure | Manual retry loops | Existing `invoke_claude_with_retry` (Tenacity) | Already handles exponential backoff, 3 attempts |
| Agent instantiation | Direct class construction | `create_agent()` from factory | Registry-driven, consistent with existing pattern |
| Handoff formatting | Ad-hoc string concatenation | `build_handoff()` | Structured, inspectable, consistent format |

**Key insight:** The existing codebase already has most building blocks. The orchestrator is primarily a new control flow layer wiring existing components together, not new infrastructure.

## Common Pitfalls

### Pitfall 1: Worker-Modal Thread Mismatch
**What goes wrong:** Orchestrator loop runs in a Textual worker (background thread). Pushing a ModalScreen from a worker thread causes Textual errors or silent failures.
**Why it happens:** Textual's DOM operations must happen on the main thread.
**How to avoid:** Use `app.call_from_thread()` to push the modal screen and `asyncio.Event` to await the result from the worker.
**Warning signs:** `RuntimeError: Cannot modify DOM from worker thread` or modal not appearing.

### Pitfall 2: Context Window Explosion
**What goes wrong:** After 3+ iterations, the accumulated handoffs + original prompt exceed Claude's context window.
**Why it happens:** Each iteration adds full agent output as handoff context.
**How to avoid:** Summarize prior handoffs rather than including full text. Include only the most recent 2 full handoffs and summaries of older ones. The orchestrator prompt itself should be concise (just key sections, not full raw output).
**Warning signs:** Claude CLI errors about token limits, or degraded quality in later iterations.

### Pitfall 3: Orchestrator Prompt Too Vague
**What goes wrong:** Claude's routing decision is inconsistent or doesn't match expected schema.
**Why it happens:** The orchestrator system prompt doesn't clearly define the routing criteria.
**How to avoid:** Be explicit in the orchestrator prompt: "If DECISION contains APPROVED, return next_agent=approved. If DECISION contains BACK TO PLAN, return next_agent=plan. If DECISION contains BACK TO EXECUTE, return next_agent=execute. For the first pass (plan->execute->review), route forward sequentially."
**Warning signs:** Unexpected routing decisions, orchestrator always choosing the same agent.

### Pitfall 4: Iteration Count Logic Off-by-One
**What goes wrong:** Iteration limit triggers too early or too late.
**Why it happens:** Confusion about when to increment: after each agent, or only after REVIEW.
**How to avoid:** Per CONTEXT.md: "An iteration = one full cycle that includes a REVIEW agent run." Increment ONLY after REVIEW completes. The counter represents completed review cycles.
**Warning signs:** Halt dialog appearing after first REVIEW, or never appearing.

### Pitfall 5: collect_claude Output Format with --output-format json
**What goes wrong:** `collect_claude` is designed for `stream-json` output format but `--output-format json` returns a single JSON object (not streamed).
**Why it happens:** The existing `stream_claude` parses `stream-json` line-by-line. With `--output-format json`, the response is a single JSON blob.
**How to avoid:** For the orchestrator decision call (non-streaming), use `asyncio.create_subprocess_exec` directly to capture stdout as a single string, or ensure `collect_claude` handles the different output format. The orchestrator call should NOT stream -- it's a quick routing decision.
**Warning signs:** JSON parse errors, empty responses, or getting stream-json events instead of a single JSON object.

### Pitfall 6: Forgetting --dangerously-skip-permissions
**What goes wrong:** Claude CLI prompts for permission interactively, hanging the async subprocess.
**Why it happens:** The orchestrator decision call doesn't include the flag that `stream_claude` already uses.
**How to avoid:** Ensure the orchestrator's Claude CLI call includes `--dangerously-skip-permissions` (or use the existing `stream_claude`/`collect_claude` which already include it).
**Warning signs:** Subprocess hanging indefinitely, no output received.

## Code Examples

### Orchestrator System Prompt
```python
ORCHESTRATOR_SYSTEM_PROMPT = """You are a workflow orchestrator for an AI agent pipeline.
You analyze agent outputs and decide which agent should run next.

The pipeline has three agents:
- PLAN: Creates a structured development plan
- EXECUTE: Implements the plan by writing code
- REVIEW: Reviews the execution output for quality

Routing rules:
1. Normal forward flow: plan -> execute -> review
2. If REVIEW's DECISION says "APPROVED": output next_agent="approved"
3. If REVIEW's DECISION says "BACK TO PLAN": output next_agent="plan"
4. If REVIEW's DECISION says "BACK TO EXECUTE": output next_agent="execute"
5. For the first pass (no prior iterations), always route forward

Analyze the latest agent output and return your routing decision as JSON.
Be concise in your reasoning (one sentence).
"""
```

### Building Orchestrator Decision Prompt
```python
def build_orchestrator_prompt(
    state: OrchestratorState,
    latest_sections: dict[str, str],
) -> str:
    """Build the prompt sent to Claude CLI for routing decision."""
    lines = [
        f"Current agent just completed: {state.current_agent.upper()}",
        f"Iteration count: {state.iteration_count}",
        f"Workflow history: {' -> '.join(h['agent'].upper() for h in state.history)}",
        "",
        "Latest agent output sections:",
    ]

    for section_name, content in latest_sections.items():
        # Truncate long sections to avoid token bloat
        truncated = content[:500] + "..." if len(content) > 500 else content
        lines.append(f"--- {section_name} ---")
        lines.append(truncated)
        lines.append("")

    lines.append("Based on this output, what agent should run next?")
    return "\n".join(lines)
```

### DB Schema Addition
```sql
CREATE TABLE IF NOT EXISTS orchestrator_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    next_agent TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    confidence REAL,
    full_response TEXT NOT NULL,
    iteration_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
```

### Direct Claude CLI Call for Orchestrator (Non-Streaming)
```python
async def call_orchestrator_claude(
    prompt: str,
    schema: str,
) -> str:
    """
    Call Claude CLI with --output-format json --json-schema for structured output.

    Unlike stream_claude, this returns a single JSON response (not streamed).
    Uses a dedicated subprocess call rather than the streaming path.
    """
    claude = _resolve_claude()
    cmd = [
        claude, "-p",
        "--output-format", "json",
        "--json-schema", schema,
        "--dangerously-skip-permissions",
        prompt,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode, "claude",
            stderr=stderr.decode(errors="replace"),
        )

    return stdout.decode()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Sequential pipeline (fixed order) | AI-driven routing with Claude CLI | This phase | Enables iterative improvement cycles |
| No user confirmation on routing | ModalScreen confirmation | This phase | User stays in control of re-routing |
| No iteration tracking | OrchestratorState with limits | This phase | Prevents infinite loops |
| No orchestrator visibility | Status bar + DB logging | This phase | Transparent decision-making |

**Deprecated/outdated:**
- `pipeline/runner.py` `run_pipeline()` function: will be superseded by orchestrator loop (but keep PipelineResult dataclass)
- Fixed `next_agent` chain in `AGENT_REGISTRY`: still used for default forward flow, but orchestrator can override

## Open Questions

1. **Should the orchestrator system prompt be a file or inline string?**
   - What we know: Other agents use `system_prompt_file` from PROMPTS_DIR
   - What's unclear: Orchestrator prompt is simpler and more static than agent prompts
   - Recommendation: Create `agents/prompts/orchestrator_system.txt` for consistency with existing pattern

2. **Should `collect_claude` be extended to support `--output-format json` or create a separate function?**
   - What we know: `collect_claude` calls `stream_claude` which parses `stream-json` events. `--output-format json` returns a single JSON blob, not streamed events.
   - What's unclear: Whether `stream_claude` handles single JSON responses correctly
   - Recommendation: Create a dedicated `call_orchestrator_claude()` that uses `proc.communicate()` instead of line-by-line iteration. Keeps concerns separated and avoids breaking existing streaming.

3. **Worker threading model for orchestrator loop**
   - What we know: Current `start_agent_worker` runs one agent per worker. The orchestrator needs to run a multi-agent loop.
   - What's unclear: Whether a single long-running worker is better than chaining multiple workers
   - Recommendation: Single long-running worker for the orchestrator loop. It internally calls `stream_agent_to_panel` for each agent and uses `call_from_thread` for modals. Simpler than worker chaining.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (auto mode) |
| Config file | `pytest.ini` |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ORCH-01 | Orchestrator calls Claude CLI and gets structured decision | unit (mocked CLI) | `pytest tests/test_orchestrator.py::test_get_decision -x` | No -- Wave 0 |
| ORCH-01 | Orchestrator routes forward on first pass (plan->exec->review) | unit | `pytest tests/test_orchestrator.py::test_forward_routing -x` | No -- Wave 0 |
| ORCH-02 | Re-routing triggers confirmation dialog | unit (mocked modal) | `pytest tests/test_orchestrator.py::test_reroute_confirmation -x` | No -- Wave 0 |
| ORCH-02 | Cancelled re-route halts pipeline | unit | `pytest tests/test_orchestrator.py::test_reroute_cancel_halts -x` | No -- Wave 0 |
| ORCH-03 | Iteration limit triggers halt after 3 reviews | unit | `pytest tests/test_orchestrator.py::test_iteration_limit -x` | No -- Wave 0 |
| ORCH-03 | User can continue (resets counter) or stop | unit | `pytest tests/test_orchestrator.py::test_halt_continue_resets -x` | No -- Wave 0 |
| ORCH-04 | Decision reasoning appears in status bar | unit | `pytest tests/test_orchestrator.py::test_status_bar_update -x` | No -- Wave 0 |
| ORCH-04 | Decision logged to DB | unit | `pytest tests/test_orchestrator.py::test_decision_db_logging -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_orchestrator.py -x -q`
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_orchestrator.py` -- covers ORCH-01 through ORCH-04
- [ ] `tests/test_confirm_dialog.py` -- covers ORCH-02 modal dialog behavior
- [ ] Update `tests/conftest.py` -- add orchestrator-related fixtures (mock Claude CLI JSON response, mock modal results)

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `src/pipeline/runner.py`, `src/runner/runner.py`, `src/tui/streaming.py`, `src/tui/actions.py`, `src/tui/status_bar.py`, `src/agents/config.py`, `src/db/schema.py`
- [Claude Code CLI headless docs](https://code.claude.com/docs/en/headless) -- `--output-format json`, `--json-schema` flag
- [Textual Screens documentation](https://textual.textualize.io/guide/screens/) -- `ModalScreen`, `dismiss()`, `push_screen()` with callback

### Secondary (MEDIUM confidence)
- [Mouse vs Python - Textual Modal Dialogs](https://www.blog.pythonlibrary.org/2024/02/06/creating-a-modal-dialog-for-your-tuis-in-textual/) -- ModalScreen usage patterns
- [mathspp - Modal screens in Textual](https://mathspp.com/blog/how-to-use-modal-screens-in-textual) -- callback pattern for modal results

### Tertiary (LOW confidence)
- Worker-to-modal threading pattern: Based on Textual's `call_from_thread` documented behavior. Needs validation during implementation that `asyncio.Event` correctly bridges worker thread to main thread in this context.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all components already in use, no new dependencies
- Architecture: HIGH - patterns directly supported by existing codebase and Textual/Claude CLI capabilities
- Pitfalls: HIGH - identified through codebase inspection and understanding of async/threading patterns
- Claude CLI --json-schema: MEDIUM - verified in official docs but not tested with this specific codebase's runner module; need dedicated function

**Research date:** 2026-03-12
**Valid until:** 2026-04-12 (stable domain, low churn)
