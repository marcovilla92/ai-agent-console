# Phase 22: Bug Fixes & Foundation - Research

**Researched:** 2026-03-14
**Domain:** Claude CLI subprocess flag fixes + handoff context windowing
**Confidence:** HIGH

## Summary

Phase 22 addresses two pre-existing bugs (agents and orchestrator running without system prompts) and two context management improvements (bounded handoff windowing with pinned first plan). All four requirements are pure Python changes to existing files -- no new dependencies, no new modules, no frontend changes. The total scope is approximately 40-60 lines of modified code across 4 files.

The bug fixes (FIX-01, FIX-02) are straightforward: `stream_output()` in `context.py` calls `stream_claude(prompt)` without passing `system_prompt_file`, and `call_orchestrator_claude()` in `runner.py` does not accept or pass `--system-prompt-file`. Both fixes require looking up the agent config and threading the path through to the subprocess command. The context management (CTX-05, CTX-06) requires modifying the handoff accumulation logic in `orchestrator.py` to implement a sliding window that keeps only the last complete cycle (3 handoffs: plan+execute+review) while always preserving the very first plan handoff regardless of windowing.

**Primary recommendation:** Fix system prompts first (FIX-01 + FIX-02), then implement bounded handoffs (CTX-05 + CTX-06). The system prompt fixes are independent of each other and can be done in parallel. The handoff changes depend on understanding the current handoff structure but not on the system prompt fixes.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| FIX-01 | All agents (plan, execute, review) receive their system prompt files during web execution via `stream_output()` | `stream_output()` at context.py:85 calls `stream_claude(prompt)` without `system_prompt_file`. Fix: import `get_agent_config` from config.py, look up config by `agent_name`, pass `system_prompt_file=config.system_prompt_file` to `stream_claude()`. |
| FIX-02 | Orchestrator decision calls receive `orchestrator_system.txt` via `--system-prompt-file` flag | `call_orchestrator_claude()` at runner.py:146 does not accept a `system_prompt_file` parameter. Fix: add the parameter, build cmd with `--system-prompt-file` flag, pass path from `orchestrator.py`. |
| CTX-05 | Handoffs are bounded to the last complete cycle (plan+execute+review) with 8000-char cap | `accumulated_handoffs` at orchestrator.py:52 is an unbounded `list[str]`. Fix: after appending each handoff (line 257), apply windowing: keep at most 3 entries (last cycle), enforce 8000 char total by dropping oldest (except pinned plan). |
| CTX-06 | First plan handoff is pinned (exempt from windowing) to preserve original context on re-routes | The first handoff appended is always from the plan agent (state starts at "plan"). Pin index 0 as exempt from the sliding window. Window operates on `accumulated_handoffs[1:]` only. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12 | Runtime | Already deployed |
| asyncio | stdlib | Subprocess management | Already used throughout pipeline |
| pathlib | stdlib | System prompt file paths | Already used in config.py |

### Supporting
No new libraries needed. All changes use existing imports and patterns.

### Alternatives Considered
None. These are targeted bug fixes and refactors to existing code.

**Installation:**
```bash
# No new packages needed
```

## Architecture Patterns

### Files Modified
```
src/
  engine/
    context.py           # FIX-01: add system_prompt_file to stream_claude() call
  runner/
    runner.py             # FIX-02: add system_prompt_file param to call_orchestrator_claude()
  pipeline/
    orchestrator.py       # FIX-02: pass orchestrator prompt file path
                          # CTX-05: bounded handoff windowing
                          # CTX-06: pinned first plan handoff
```

### Pattern 1: System Prompt Lookup in stream_output (FIX-01)

**What:** Look up agent config by name to get system_prompt_file, pass to stream_claude.
**When to use:** Every agent invocation via the web path.
**Current code (context.py:83-85):**
```python
async def stream_output(self, agent_name: str, prompt: str, sections: dict) -> dict[str, str]:
    raw_parts: list[str] = []
    async for event in stream_claude(prompt):  # <-- BUG: no system_prompt_file
```

**Fixed pattern:**
```python
from src.agents.config import get_agent_config

async def stream_output(self, agent_name: str, prompt: str, sections: dict) -> dict[str, str]:
    # Look up system prompt for this agent
    try:
        config = get_agent_config(agent_name)
        system_prompt = config.system_prompt_file
    except KeyError:
        system_prompt = None
        log.warning("No agent config for %r, running without system prompt", agent_name)

    raw_parts: list[str] = []
    async for event in stream_claude(prompt, system_prompt_file=system_prompt):
```

**Key detail:** `stream_claude()` already accepts `system_prompt_file` as a kwarg (runner.py:38) and builds the `--system-prompt-file` flag when it is provided (runner.py:55-56). The plumbing exists; it just is not used from `stream_output()`.

### Pattern 2: Orchestrator System Prompt (FIX-02)

**What:** Add `system_prompt_file` parameter to `call_orchestrator_claude()`, pass the orchestrator prompt path.
**Current code (runner.py:146-160):**
```python
async def call_orchestrator_claude(prompt: str, schema: str) -> str:
    claude = _resolve_claude()
    cmd = [
        claude, "-p",
        "--output-format", "json",
        "--json-schema", schema,
        "--dangerously-skip-permissions",
        prompt,
    ]
```

**Fixed pattern:**
```python
async def call_orchestrator_claude(
    prompt: str, schema: str, system_prompt_file: str | None = None
) -> str:
    claude = _resolve_claude()
    cmd = [
        claude, "-p",
        "--output-format", "json",
        "--json-schema", schema,
        "--dangerously-skip-permissions",
    ]
    if system_prompt_file:
        cmd += ["--system-prompt-file", system_prompt_file]
    cmd.append(prompt)
```

**Caller side (orchestrator.py):**
```python
from pathlib import Path

ORCHESTRATOR_PROMPT_FILE = str(
    Path(__file__).parent.parent / "agents" / "prompts" / "orchestrator_system.txt"
)

# In get_orchestrator_decision():
raw = await call_orchestrator_claude(prompt, ORCHESTRATOR_SCHEMA, ORCHESTRATOR_PROMPT_FILE)
```

### Pattern 3: Bounded Handoffs with Pinned Plan (CTX-05 + CTX-06)

**What:** Sliding window on accumulated_handoffs keeping only last complete cycle, with first plan handoff always preserved.
**Current code (orchestrator.py:257):**
```python
state.accumulated_handoffs.append(build_handoff(agent_result))
```

**Fixed pattern:**
```python
MAX_HANDOFF_ENTRIES = 3  # One complete cycle: plan + execute + review
MAX_HANDOFF_CHARS = 8000

state.accumulated_handoffs.append(build_handoff(agent_result))

# Apply windowing: pin first plan handoff, window the rest
if len(state.accumulated_handoffs) > MAX_HANDOFF_ENTRIES + 1:
    # Keep index 0 (original plan) + last MAX_HANDOFF_ENTRIES
    pinned = state.accumulated_handoffs[0]
    recent = state.accumulated_handoffs[-(MAX_HANDOFF_ENTRIES):]
    state.accumulated_handoffs = [pinned] + recent

# Enforce character cap on windowed portion (pinned exempt)
if len(state.accumulated_handoffs) > 1:
    pinned = state.accumulated_handoffs[0]
    windowed = state.accumulated_handoffs[1:]
    total = "\n\n".join(windowed)
    while len(total) > MAX_HANDOFF_CHARS and len(windowed) > 1:
        windowed.pop(0)
        total = "\n\n".join(windowed)
    state.accumulated_handoffs = [pinned] + windowed

log.info(
    "orchestrate_pipeline: handoff windowing applied, "
    "total_handoffs=%d total_chars=%d",
    len(state.accumulated_handoffs),
    sum(len(h) for h in state.accumulated_handoffs),
)
```

**Critical invariant (CTX-06):** `state.accumulated_handoffs[0]` is ALWAYS the original plan handoff. It is never dropped by windowing. The 8000-char cap applies only to `accumulated_handoffs[1:]`.

### Anti-Patterns to Avoid

- **Do NOT add system_prompt_file to the TaskContext Protocol.** The protocol is agent-agnostic. The system prompt lookup belongs inside `stream_output()` implementation, not in the protocol method signature.
- **Do NOT truncate handoffs at arbitrary character boundaries.** Drop entire handoff entries rather than slicing mid-content. The `=== END HANDOFF ===` markers must remain intact.
- **Do NOT modify `build_handoff()` in handoff.py.** The handoff format is fine. Only the accumulation/windowing logic in orchestrator.py changes.
- **Do NOT change the handoff pinning based on agent_name matching.** Pin by index (first entry = index 0) not by content inspection. The first entry is always from plan because `state.current_agent` starts as `"plan"`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| System prompt file resolution | Custom prompt file finder | `get_agent_config(agent_name).system_prompt_file` | Already exists in config.py, resolves path via PROMPTS_DIR |
| Handoff size measurement | Token counter (tiktoken) | `len(string)` character count | Character count is sufficient for bounding; token counting adds a dependency for marginal benefit |

## Common Pitfalls

### Pitfall 1: Orchestrator System Prompt Changes Routing Behavior
**What goes wrong:** The orchestrator has been making decisions WITHOUT its system prompt for the entire lifetime of the web app. Adding it now may change routing patterns -- decisions that previously approved may now re-route, or vice versa.
**Why it happens:** `orchestrator_system.txt` contains routing rules that the orchestrator was ignoring. Now it will follow them.
**How to avoid:** Review the current `orchestrator_system.txt` content (already inspected -- it is 17 lines with sensible routing rules). Test with a known prompt before and after to verify behavior remains reasonable. The prompt content matches current routing logic, so impact should be positive.
**Warning signs:** Pipeline that previously approved in 1 iteration now takes 2+, or vice versa.

### Pitfall 2: stream_output Agent Name Mismatch
**What goes wrong:** `stream_output()` receives `agent_name` as a string. If orchestrator.py passes a name not in AGENT_REGISTRY (e.g., typo, future agent without config), `get_agent_config()` raises KeyError and the entire agent call fails.
**Why it happens:** No validation between orchestrator state and registry.
**How to avoid:** Wrap `get_agent_config()` in try/except KeyError, fall back to running without system prompt (current behavior), log a warning. This preserves backward compatibility.
**Warning signs:** Agent calls fail with KeyError in logs.

### Pitfall 3: Pinned Plan Handoff Grows Unbounded
**What goes wrong:** The pinned plan handoff (index 0) is exempt from the 8000-char cap. If the plan agent produces an extremely long output (5000+ chars in sections), the total context exceeds the intended bound.
**Why it happens:** Plan output length varies with task complexity.
**How to avoid:** Apply a separate cap to the pinned plan handoff (e.g., 2000 chars). Truncate at section boundaries within the handoff. This is acceptable because the plan's HANDOFF section (the most critical part) is usually short; the verbose sections (ARCHITECTURE, FILES TO CREATE) can be trimmed.
**Warning signs:** Total handoff context exceeding 10000 chars despite windowing.

### Pitfall 4: Handoff Windowing on First Cycle Has No Effect
**What goes wrong:** On the first cycle (plan -> execute -> review), there are exactly 3 handoffs. The window size is 3. Windowing does nothing. This is correct behavior but may confuse testers expecting to see windowing in action.
**Why it happens:** Windowing only activates on re-route cycles (iteration 2+).
**How to avoid:** Document this explicitly. Test windowing with a multi-iteration scenario (mock 2+ cycles).

## Code Examples

### Complete stream_output Fix (FIX-01)

```python
# src/engine/context.py -- stream_output method
# Source: Direct codebase analysis

from src.agents.config import get_agent_config  # Add import at top of file

async def stream_output(
    self, agent_name: str, prompt: str, sections: dict
) -> dict[str, str]:
    from datetime import datetime, timezone

    # Look up system prompt for this agent
    system_prompt = None
    try:
        config = get_agent_config(agent_name)
        system_prompt = config.system_prompt_file
        log.info("stream_output: agent=%s system_prompt=%s", agent_name, system_prompt)
    except KeyError:
        log.warning("stream_output: no config for agent %r, running without system prompt", agent_name)

    raw_parts: list[str] = []
    async for event in stream_claude(prompt, system_prompt_file=system_prompt):
        if isinstance(event, str):
            raw_parts.append(event)
            if self._connection_manager:
                await self._connection_manager.send_chunk(self._task_id, event)
        elif isinstance(event, dict):
            if "result" in event:
                raw_parts.append(str(event["result"]))

    raw_output = "".join(raw_parts)
    parsed_sections = extract_sections(raw_output)

    # Persist to DB (unchanged)
    try:
        repo = AgentOutputRepository(self._pool)
        output = AgentOutput(
            session_id=self._task_id,
            agent_type=agent_name,
            raw_output=raw_output,
            created_at=datetime.now(timezone.utc),
        )
        await repo.create(output)
    except Exception:
        log.exception("Failed to persist agent output for task %d", self._task_id)

    return parsed_sections
```

### Complete call_orchestrator_claude Fix (FIX-02)

```python
# src/runner/runner.py -- call_orchestrator_claude function
# Source: Direct codebase analysis

async def call_orchestrator_claude(
    prompt: str, schema: str, system_prompt_file: str | None = None
) -> str:
    claude = _resolve_claude()
    cmd = [
        claude, "-p",
        "--output-format", "json",
        "--json-schema", schema,
        "--dangerously-skip-permissions",
    ]
    if system_prompt_file:
        cmd += ["--system-prompt-file", system_prompt_file]
    cmd.append(prompt)

    log.info("call_orchestrator_claude: launching decision call, prompt_len=%d system_prompt=%s",
             len(prompt), system_prompt_file)
    # ... rest unchanged
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Agents run without system prompts | System prompts loaded via `--system-prompt-file` | This phase | Structured, predictable output |
| Unbounded handoff accumulation | Sliding window + pinned plan | This phase | Bounded context growth |

## Open Questions

1. **Pinned plan handoff size cap**
   - What we know: The plan handoff should be pinned exempt from the 8000-char window.
   - What is unclear: Should the pinned plan itself have a separate size cap (e.g., 2000 chars)?
   - Recommendation: Apply a 2000-char cap to the pinned plan, truncating at the last complete section boundary. This prevents edge cases where a verbose plan dominates context.

2. **Existing test compatibility**
   - What we know: `test_orchestrator.py` patches `call_orchestrator_claude` with 2 args (prompt, schema). Adding a third parameter (system_prompt_file) with a default of None preserves backward compatibility.
   - What is unclear: Any other call sites that may break.
   - Recommendation: Grep for all `call_orchestrator_claude` usages before modifying the signature. Currently only called from `get_orchestrator_decision()` in orchestrator.py.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `pytest.ini` |
| Quick run command | `cd /home/ubuntu/projects/ai-agent-console && python -m pytest tests/test_orchestrator.py tests/test_handoff.py -x -q` |
| Full suite command | `cd /home/ubuntu/projects/ai-agent-console && python -m pytest tests/ -x -q --ignore=tests/test_pg_repository.py --ignore=tests/test_task_manager.py --ignore=tests/test_server.py --ignore=tests/test_websocket.py` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FIX-01 | stream_output passes system_prompt_file to stream_claude | unit (mock) | `python -m pytest tests/test_stream_output_sysprompt.py -x` | No -- Wave 0 |
| FIX-02 | call_orchestrator_claude accepts and passes system_prompt_file | unit (mock) | `python -m pytest tests/test_orchestrator.py -x -k "system_prompt"` | No -- Wave 0 |
| CTX-05 | Handoffs bounded to last cycle + 8000 char cap | unit | `python -m pytest tests/test_orchestrator.py -x -k "bounded"` | No -- Wave 0 |
| CTX-06 | First plan handoff pinned, never dropped by windowing | unit | `python -m pytest tests/test_orchestrator.py -x -k "pinned"` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_orchestrator.py tests/test_handoff.py -x -q`
- **Per wave merge:** Full suite (excluding PG-dependent tests)
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_orchestrator.py` -- add tests for: bounded handoff windowing (CTX-05), pinned plan handoff (CTX-06), orchestrator system prompt path passed (FIX-02)
- [ ] New test or test section for FIX-01 verifying `stream_claude` called with correct `system_prompt_file` kwarg (mock-based, can go in existing `test_orchestrator.py` or new file)
- [ ] No new framework install needed -- pytest + pytest-asyncio already configured

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of `src/engine/context.py` (200 lines) -- confirmed stream_claude called without system_prompt_file at line 85
- Direct codebase analysis of `src/runner/runner.py` (197 lines) -- confirmed call_orchestrator_claude lacks system_prompt_file at line 146; confirmed stream_claude already supports the parameter at line 38
- Direct codebase analysis of `src/pipeline/orchestrator.py` (343 lines) -- confirmed unbounded handoff accumulation at line 257, confirmed call_orchestrator_claude called without system_prompt_file at line 152
- Direct codebase analysis of `src/agents/config.py` (79 lines) -- confirmed get_agent_config() exists and returns AgentConfig with system_prompt_file
- Direct codebase analysis of `src/agents/prompts/orchestrator_system.txt` (17 lines) -- confirmed content is appropriate routing rules
- Direct codebase analysis of `src/pipeline/handoff.py` (38 lines) -- confirmed handoff format with markers

### Secondary (MEDIUM confidence)
- `.planning/research/PITFALLS.md` -- Pitfall 2 (bounded handoffs drop plan context), Pitfall 5 (stream_output missing system prompt), Pitfall 12 (orchestrator prompt changes routing)
- `.planning/research/ARCHITECTURE.md` -- Component 1 (orchestrator prompt fix), Component 3 (bounded handoffs)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all changes to existing files with known structure
- Architecture: HIGH -- all integration points verified by reading actual source lines
- Pitfalls: HIGH -- pitfalls identified from direct code analysis, not inference

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (stable -- no external API dependencies)
