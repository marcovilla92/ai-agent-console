# Phase 5: Polish - Research

**Researched:** 2026-03-12
**Domain:** TUI resizable panels, git automation, token/cost tracking, session browsing
**Confidence:** HIGH

## Summary

Phase 5 adds four daily-use quality features: resizable/collapsible panels (TUI-05), git auto-commit after successful execution (INFR-06), token/cost display in the status bar (INFR-07), and session browsing with resume (INFR-08). All four requirements build on existing infrastructure -- the Textual grid layout, asyncio subprocess runner, stream-json parser, and SQLite session repository.

The most complex item is panel resizing since Textual has no built-in splitter widget. The approach is to dynamically update `grid-rows` and `grid-columns` CSS properties via keyboard shortcuts, toggling panels between their normal `1fr` size and a collapsed `0` or `3` (title-only) height. For collapse, Textual's `Collapsible` widget is available but not ideal for the grid layout -- instead, toggling `display: none` or setting row/column to near-zero is cleaner. Token tracking leverages the `result` event already present in stream-json output (confirmed by existing mock fixtures showing `cost_usd` field). Git auto-commit uses `asyncio.create_subprocess_exec` consistent with the existing runner pattern. Session browsing extends the existing `SessionRepository.list_all()` method with a Textual `OptionList` or `DataTable` modal.

**Primary recommendation:** Implement all four features as independent modules that hook into existing infrastructure -- no architectural changes needed, only additive code.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TUI-05 | User can resize and collapse panels via keyboard or mouse | Dynamic CSS grid-rows/grid-columns manipulation; keyboard bindings; Collapsible-style toggle |
| INFR-06 | Git auto-commit after successful execution cycles with descriptive messages | asyncio subprocess git commands; hook into orchestrator approved state |
| INFR-07 | Token usage and estimated cost tracked per agent per cycle, displayed in status bar | Parse `result` and `message_start` events from stream-json; cost_usd field; pricing table |
| INFR-08 | User can browse past sessions and resume any previous session | Extend SessionRepository; DataTable/OptionList modal; reload agent outputs into panels |
</phase_requirements>

## Standard Stack

### Core (already installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| textual | >=0.50 | TUI framework | Already in use; provides grid layout, widgets, CSS, workers |
| aiosqlite | >=0.20 | Async SQLite | Already in use; session persistence |
| tenacity | >=8.0 | Retry logic | Already in use; CLI retry |

### Supporting (no new dependencies needed)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio (stdlib) | 3.10+ | Subprocess for git commands | Git auto-commit |
| json (stdlib) | 3.10+ | Parse stream-json events | Token tracking |
| dataclasses (stdlib) | 3.10+ | Usage tracking data structures | Token/cost models |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw git subprocess | GitPython library | Adds dependency; asyncio subprocess is consistent with existing runner pattern |
| Manual cost calculation | Claude Agent SDK | Overkill; stream-json already provides cost_usd in result event |
| Custom session browser | textual-datatable | Already built into Textual as DataTable widget |

**Installation:**
```bash
# No new dependencies required -- all features use existing stack + stdlib
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── tui/
│   ├── panels.py          # Add resize/collapse methods
│   ├── app.py             # Add resize/collapse key bindings + session browser action
│   ├── status_bar.py      # Extend with token/cost display section
│   ├── session_browser.py # NEW: ModalScreen for session list + resume
│   └── theme.tcss         # Update grid CSS for dynamic sizing
├── runner/
│   └── runner.py          # Extend stream_claude to capture result event (usage/cost)
├── git/
│   └── autocommit.py      # NEW: async git add/commit after approved cycles
├── db/
│   ├── schema.py          # Add token_usage table
│   └── repository.py      # Add UsageRepository, extend SessionRepository
└── pipeline/
    └── orchestrator.py    # Hook git auto-commit on approved state
```

### Pattern 1: Dynamic CSS Grid Resizing
**What:** Modify grid-rows/grid-columns at runtime via `widget.styles.grid_rows`
**When to use:** Panel resize via keyboard shortcuts
**Example:**
```python
# Source: Textual docs - grid-rows/grid-columns are writable style properties
def action_increase_top_row(self) -> None:
    """Increase top row height, decrease bottom."""
    grid = self.query_one("#app-grid")
    # Current: "1fr 1fr" -> "2fr 1fr"
    self._top_ratio = min(self._top_ratio + 1, 4)
    self._bottom_ratio = max(self._bottom_ratio - 1, 1)
    grid.styles.grid_rows = f"{self._top_ratio}fr {self._bottom_ratio}fr"

def action_collapse_panel(self, panel_id: str) -> None:
    """Toggle a panel between visible and collapsed (title-only)."""
    panel = self.query_one(f"#{panel_id}")
    panel.display = not panel.display
```

### Pattern 2: Stream-JSON Result Event Parsing
**What:** Capture the final `result` event from stream-json to extract cost/usage
**When to use:** After each agent run completes
**Example:**
```python
# The result event structure (confirmed by existing mock in conftest.py):
# {"type":"result","subtype":"success","session_id":"...","cost_usd":0.001,"num_turns":1}
# Also, message_start events contain initial usage info

@dataclass
class AgentUsage:
    agent_name: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
```

### Pattern 3: Async Git Auto-Commit
**What:** Run git add + git commit as async subprocess after approved cycle
**When to use:** After orchestrator sets state.approved = True
**Example:**
```python
async def auto_commit(project_path: str, session_name: str) -> bool:
    """Auto-commit generated files after approved execution cycle."""
    proc = await asyncio.create_subprocess_exec(
        "git", "add", "-A",
        cwd=project_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    if proc.returncode != 0:
        return False

    msg = f"auto: {session_name} - execution cycle approved"
    proc = await asyncio.create_subprocess_exec(
        "git", "commit", "-m", msg,
        cwd=project_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    return proc.returncode == 0
```

### Pattern 4: Session Browser Modal
**What:** ModalScreen with DataTable listing past sessions
**When to use:** User triggers session browse action
**Example:**
```python
class SessionBrowser(ModalScreen[int | None]):
    """Modal listing past sessions for resume."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Past Sessions")
            yield DataTable(id="session-table")
            with Horizontal():
                yield Button("Resume", id="resume", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        table = self.query_one("#session-table", DataTable)
        table.add_columns("ID", "Name", "Project", "Date")
        # Sessions loaded async and populated here
```

### Anti-Patterns to Avoid
- **Blocking git commands in the TUI thread:** Always use asyncio subprocess, never subprocess.run() -- it blocks the event loop
- **Storing cost in agent_outputs table:** Create a separate usage tracking table; agent_outputs stores raw text, not metrics
- **Overcomplicating panel resize with mouse drag:** Textual does not have a splitter widget; keyboard-based resize with fr ratio changes is much simpler and more reliable
- **Parsing token usage from text output:** Use the structured result event, not regex on text

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Session list display | Custom string rendering | Textual DataTable widget | Handles scrolling, selection, column alignment |
| Modal dialogs | Custom overlay logic | Textual ModalScreen | Already used for confirm_dialog.py; consistent UX |
| Git operations | Shell string concatenation | asyncio.create_subprocess_exec with list args | Prevents injection; consistent with runner.py |
| Cost estimation | Manual per-model pricing lookup | Parse cost_usd from stream-json result event | Claude CLI calculates cost server-side; includes caching discounts |
| Panel collapse animation | Custom visibility toggling | Textual display property + CSS transitions | Framework handles reflow automatically |

**Key insight:** The Claude CLI `result` event already provides `cost_usd` -- no need to maintain a pricing table or calculate costs manually. Parse it from stream-json output.

## Common Pitfalls

### Pitfall 1: Git Auto-Commit in Non-Git Projects
**What goes wrong:** `git add -A` fails if the project_path is not inside a git repository
**Why it happens:** User may create projects in directories without git init
**How to avoid:** Check for `.git` directory existence before attempting auto-commit; silently skip if not a git repo
**Warning signs:** CalledProcessError from git commands

### Pitfall 2: Cost Display When Using Claude Max Subscription
**What goes wrong:** cost_usd may be 0 or absent for subscription users (not API users)
**Why it happens:** Claude Max/Pro subscriptions don't charge per-token
**How to avoid:** Display "N/A" when cost_usd is 0 or missing; always show token counts regardless
**Warning signs:** cost_usd field is 0 in result event

### Pitfall 3: Panel Resize Breaking Layout at Terminal Edges
**What goes wrong:** Setting a panel to 0fr or very small fr makes the grid collapse
**Why it happens:** CSS grid with 0fr is technically valid but causes zero-height cells
**How to avoid:** Use minimum of `3` (character height for border + title) for collapsed panels, or toggle `display: none` and let remaining panels fill space
**Warning signs:** Panels disappear entirely or overlap

### Pitfall 4: Session Resume Loading Stale Context
**What goes wrong:** Resuming a session loads old agent outputs but the project files have changed since then
**Why it happens:** Sessions store outputs at time of creation; filesystem evolves independently
**How to avoid:** On resume, re-assemble workspace context from current filesystem; only load the prompt and agent outputs from the session, not the workspace context
**Warning signs:** Agents reference files that no longer exist

### Pitfall 5: Missing Result Event in Stream-JSON
**What goes wrong:** The `result` event may not always arrive (documented bug in Claude Code CLI issue #1920)
**Why it happens:** Known intermittent issue where CLI fails to emit final result event
**How to avoid:** Treat cost/usage as optional; set defaults (0 cost, 0 tokens) if result event never arrives; don't block on it
**Warning signs:** Token display shows 0 after a successful run

### Pitfall 6: Race Condition on Git Auto-Commit
**What goes wrong:** Multiple concurrent operations could trigger overlapping git commits
**Why it happens:** Workers run in background; if two approve quickly, git operations interleave
**How to avoid:** Use a simple asyncio.Lock for git operations; the existing `exclusive=True` on workers already prevents concurrent agent runs, but add the lock as a safety measure
**Warning signs:** Git lock errors or merge conflicts on auto-commit

## Code Examples

### Extending stream_claude to Capture Usage

```python
# In src/runner/runner.py - modify stream_claude to yield a final usage dict
# OR create a wrapper that collects usage separately

@dataclass
class StreamResult:
    """Result of streaming a Claude CLI call."""
    text: str
    usage: dict  # {"input_tokens": N, "output_tokens": N, "cost_usd": float}

async def stream_claude_with_usage(
    prompt: str,
    *,
    system_prompt_file: str | None = None,
) -> AsyncGenerator[str | dict, None]:
    """
    Like stream_claude, but also yields the result event dict at the end.
    The caller can check isinstance(chunk, dict) to detect the result event.
    """
    # ... same setup as stream_claude ...
    async for raw_line in proc.stdout:
        line = raw_line.decode().strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type = data.get("type")

        if msg_type == "content_block_delta":
            delta = data.get("delta", {})
            if delta.get("type") == "text_delta" and delta.get("text"):
                yield delta["text"]
        elif msg_type == "result":
            # Yield the result event as a dict for the caller to process
            yield {
                "type": "result",
                "cost_usd": data.get("cost_usd", 0.0),
                "num_turns": data.get("num_turns", 0),
                "session_id": data.get("session_id", ""),
            }
```

### Extended Status Bar with Cost Display

```python
# In src/tui/status_bar.py - add token/cost fields
class StatusBar(Static):
    def __init__(self) -> None:
        super().__init__(id="status-bar")
        self._agent = "none"
        self._state = "idle"
        self._step = ""
        self._next_action = "Enter a prompt and press Ctrl+S"
        self._tokens = ""  # NEW
        self._cost = ""    # NEW

    def set_usage(self, *, input_tokens: int = 0, output_tokens: int = 0, cost_usd: float = 0.0) -> None:
        """Update token/cost display."""
        self._tokens = f"In:{input_tokens} Out:{output_tokens}"
        self._cost = f"${cost_usd:.4f}" if cost_usd > 0 else ""
        self._refresh_text()

    def _refresh_text(self) -> None:
        parts = [
            f"Agent: {self._agent.upper()}",
            f"State: {self._state}",
        ]
        if self._step:
            parts.append(f"Step: {self._step}")
        if self._tokens:
            parts.append(self._tokens)
        if self._cost:
            parts.append(f"Cost: {self._cost}")
        parts.append(f"Next: {self._next_action}")
        self._display_text = " | ".join(parts)
        self.update(self._display_text)
```

### Keyboard Bindings for Panel Resize/Collapse

```python
# In src/tui/app.py - add resize bindings
BINDINGS = [
    # Existing
    ("tab", "cycle_focus", "Next Panel"),
    ("ctrl+s", "send_prompt", "Send"),
    # ... existing bindings ...
    # New: Panel resize
    ("ctrl+up", "resize_up", "Grow Top"),
    ("ctrl+down", "resize_down", "Grow Bottom"),
    ("ctrl+left", "resize_left", "Grow Left"),
    ("ctrl+right", "resize_right", "Grow Right"),
    # New: Panel collapse toggle
    ("1", "toggle_prompt", "Toggle Prompt"),
    ("2", "toggle_plan", "Toggle Plan"),
    ("3", "toggle_execute", "Toggle Execute"),
    ("4", "toggle_review", "Toggle Review"),
    # New: Session browser
    ("ctrl+b", "browse_sessions", "Sessions"),
]
```

### DB Schema Extension for Usage Tracking

```sql
-- New table for token usage tracking
CREATE TABLE IF NOT EXISTS agent_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    agent_type TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL
);
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual token counting | Claude CLI result event provides cost_usd directly | 2025+ | No need to maintain pricing table |
| GitPython library | asyncio.create_subprocess_exec | Project convention | Consistent with existing runner pattern |
| Fixed panel layout | Dynamic CSS grid manipulation | Textual 0.50+ | grid-rows/grid-columns writable at runtime |

**Deprecated/outdated:**
- Textual `dark` attribute: Use `THEME = "textual-dark"` (already correct in codebase)
- `--output-format json` for streaming: Use `stream-json` for real-time, `json` for batch (already correct)

## Open Questions

1. **Panel collapse keyboard shortcuts may conflict**
   - What we know: Number keys 1-4 are intuitive for toggling panels, but might interfere with text input in PromptPanel
   - What's unclear: Whether Textual routes number keys to the app or to the focused TextArea
   - Recommendation: Use modifier keys (e.g., `ctrl+1` through `ctrl+4`) or only apply when not in PromptPanel focus. Test with `app.focused` check.

2. **Mouse drag for panel resize**
   - What we know: TUI-05 mentions "keyboard or mouse drag"; Textual has no built-in splitter/drag widget
   - What's unclear: Whether mouse drag is feasible without significant custom widget work
   - Recommendation: Prioritize keyboard resize; mouse drag could be a custom Draggable widget using `on_mouse_move` events, but keep it simple. The requirement says "keyboard or mouse" -- delivering keyboard is sufficient for v1.

3. **Stream-JSON result event reliability**
   - What we know: Issue #1920 documents intermittent missing result events
   - What's unclear: Whether this is fixed in current Claude CLI versions
   - Recommendation: Always treat usage data as optional; display "N/A" when unavailable

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio 0.23+ |
| Config file | pyproject.toml (asyncio_mode = auto assumed from Phase 01 decisions) |
| Quick run command | `python -m pytest tests/ -x --timeout=10` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TUI-05 | Panel resize via keyboard changes grid-rows/grid-columns | unit | `python -m pytest tests/test_panel_resize.py -x` | No - Wave 0 |
| TUI-05 | Panel collapse toggles display property | unit | `python -m pytest tests/test_panel_resize.py -x` | No - Wave 0 |
| INFR-06 | Git auto-commit runs after approved cycle | unit | `python -m pytest tests/test_autocommit.py -x` | No - Wave 0 |
| INFR-06 | Git auto-commit skips non-git directories | unit | `python -m pytest tests/test_autocommit.py -x` | No - Wave 0 |
| INFR-07 | Result event parsed for cost_usd and token counts | unit | `python -m pytest tests/test_usage_tracking.py -x` | No - Wave 0 |
| INFR-07 | Status bar displays token/cost info | unit | `python -m pytest tests/test_usage_tracking.py -x` | No - Wave 0 |
| INFR-08 | Session list loaded from DB and displayed | unit | `python -m pytest tests/test_session_browser.py -x` | No - Wave 0 |
| INFR-08 | Session resume loads outputs into panels | unit | `python -m pytest tests/test_session_browser.py -x` | No - Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x --timeout=10`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_panel_resize.py` -- covers TUI-05 resize and collapse
- [ ] `tests/test_autocommit.py` -- covers INFR-06 git auto-commit
- [ ] `tests/test_usage_tracking.py` -- covers INFR-07 token/cost parsing and display
- [ ] `tests/test_session_browser.py` -- covers INFR-08 session list and resume

## Sources

### Primary (HIGH confidence)
- Textual widget gallery (https://textual.textualize.io/widget_gallery/) - confirmed no splitter widget, confirmed Collapsible and DataTable available
- Textual layout guide (https://textual.textualize.io/guide/layout/) - grid-rows/grid-columns are writable properties
- Textual Collapsible docs (https://textual.textualize.io/widgets/collapsible/) - toggle API confirmed
- Claude Code costs docs (https://code.claude.com/docs/en/costs) - cost tracking overview
- Claude Agent SDK cost tracking (https://platform.claude.com/docs/en/agent-sdk/cost-tracking) - result event structure: total_cost_usd, usage dict
- Claude Code headless docs (https://code.claude.com/docs/en/headless) - stream-json format: result event at end
- Existing conftest.py mock (tests/conftest.py) - confirms result event: `{"type":"result","subtype":"success","result":"hello","cost_usd":0.001}`

### Secondary (MEDIUM confidence)
- GitHub issue #1920 (https://github.com/anthropics/claude-code/issues/1920) - result event structure: type, subtype, session_id, cost_usd, num_turns
- GitHub issue #24596 (https://github.com/anthropics/claude-code/issues/24596) - stream-json event types documented
- Claude API pricing page (https://platform.claude.com/docs/en/about-claude/pricing) - Sonnet 4.6: $3/$15 per M tokens; but cost_usd from CLI is authoritative

### Tertiary (LOW confidence)
- Mouse drag resize feasibility in Textual -- no documented examples found; recommend keyboard-only for v1

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies; all features use existing libraries
- Architecture: HIGH - additive modules following established patterns (subprocess, ModalScreen, repository)
- Pitfalls: HIGH - confirmed via official docs and GitHub issues
- Panel resize: MEDIUM - no splitter widget exists; dynamic CSS approach is documented but not commonly shown in examples
- Cost tracking: HIGH - result event confirmed in existing mock fixtures and official docs

**Research date:** 2026-03-12
**Valid until:** 2026-04-12 (stable stack, no fast-moving dependencies)
