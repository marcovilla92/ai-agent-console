# Architecture Patterns

**Domain:** Multi-agent pipeline orchestration improvements (v2.3)
**Researched:** 2026-03-14
**Confidence:** HIGH (direct codebase analysis of all pipeline components)

---

## Note on Scope

This document covers **v2.3 orchestration improvements only** -- how file writing, bounded handoffs, targeted re-routing, test agent, dynamic schema, and confidence-based autonomy integrate with the existing pipeline architecture. The base architecture (orchestrator loop, agent registry, TaskContext Protocol, WebTaskContext, Claude CLI runner) is established and working.

---

## Current Architecture

```
User prompt
    |
    v
orchestrate_pipeline() [orchestrator.py]
    |
    +---> ctx.stream_output(agent, prompt) [context.py -> runner.py]
    |         |
    |         +---> stream_claude() subprocess
    |         +---> extract_sections() parse output
    |         +---> persist to agent_outputs DB
    |         +---> return sections dict
    |
    +---> build_handoff(AgentResult) -> accumulated_handoffs[]
    |
    +---> get_orchestrator_decision(state, sections) [orchestrator.py]
    |         |
    |         +---> call_orchestrator_claude(prompt, schema) [runner.py]
    |         +---> JSON parse -> OrchestratorDecision
    |
    +---> route: approved | forward | re-route (with user confirm)
    |
    +---> [loop back or exit]
    |
    v
auto_commit() [autocommit.py] -- only if approved
```

Key boundary: `TaskContext` Protocol decouples orchestrator from UI. `WebTaskContext` is the web implementation. All agent execution flows through `ctx.stream_output()`.

---

## New Components and Integration Points

### Component 1: Orchestrator System Prompt Fix

**Files modified:** `src/runner/runner.py`, `src/pipeline/orchestrator.py`
**Change type:** Bug fix (2 lines)

**Problem:** `call_orchestrator_claude()` in runner.py (line 154) does not pass `--system-prompt-file`. The `orchestrator_system.txt` exists but is never used. The orchestrator makes routing decisions without its role definition or routing rules.

**Integration:**

```python
# runner.py -- add parameter to call_orchestrator_claude()
async def call_orchestrator_claude(
    prompt: str, schema: str, system_prompt_file: str | None = None
) -> str:
    cmd = [claude, "-p", "--output-format", "json", "--json-schema", schema,
           "--dangerously-skip-permissions"]
    if system_prompt_file:
        cmd += ["--system-prompt-file", system_prompt_file]
    cmd.append(prompt)
    ...

# orchestrator.py -- pass the prompt file
from pathlib import Path
ORCHESTRATOR_PROMPT_FILE = str(
    Path(__file__).parent.parent / "agents" / "prompts" / "orchestrator_system.txt"
)
# In get_orchestrator_decision():
raw = await call_orchestrator_claude(prompt, ORCHESTRATOR_SCHEMA, ORCHESTRATOR_PROMPT_FILE)
```

**Impact:** Immediate improvement to routing decision quality. Zero risk. Should be built first.

---

### Component 2: Smart Section Filtering

**Files modified:** `src/pipeline/orchestrator.py`
**Change type:** Optimization in `build_orchestrator_prompt()`

**Problem:** Line 100 truncates ALL sections to 500 chars blindly. The CODE section (irrelevant for routing, often thousands of chars) wastes tokens, while DECISION (critical, usually short) is always within limit.

**Integration:** Add a routing-relevant section map and filter before building the prompt:

```python
ROUTING_SECTIONS: dict[str, set[str]] = {
    "plan": {"GOAL", "HANDOFF", "TASKS"},
    "execute": {"TARGET", "HANDOFF", "FILES"},
    "review": {"DECISION", "ISSUES", "SUMMARY"},
    "test": {"TEST RESULTS", "FAILURES", "HANDOFF"},
}

def build_orchestrator_prompt(state, latest_sections):
    relevant = ROUTING_SECTIONS.get(state.current_agent, set())
    filtered = {k: v for k, v in latest_sections.items() if k in relevant}
    if not filtered:
        filtered = latest_sections  # fallback: pass everything if no match
    # ... use filtered instead of latest_sections
```

**Interaction:** When test agent is added later, its entry in `ROUTING_SECTIONS` is added in the same dict. No structural change needed.

---

### Component 3: Bounded Handoffs

**Files modified:** `src/pipeline/orchestrator.py`
**Change type:** Modification to handoff accumulation (lines 224-258)

**Problem:** `accumulated_handoffs` grows unbounded. After 3 cycles (9 agent runs), the prompt can exceed Claude's context window or degrade response quality.

**Integration:** After building each handoff, apply windowing:

```python
MAX_HANDOFF_CHARS = 8000
MAX_HANDOFFS = 3  # One complete cycle (plan + execute + review)

# After line 257: state.accumulated_handoffs.append(build_handoff(agent_result))
if len(state.accumulated_handoffs) > MAX_HANDOFFS:
    state.accumulated_handoffs = state.accumulated_handoffs[-MAX_HANDOFFS:]

# Cap total size by dropping oldest
total = "\n\n".join(state.accumulated_handoffs)
while len(total) > MAX_HANDOFF_CHARS and len(state.accumulated_handoffs) > 1:
    state.accumulated_handoffs.pop(0)
    total = "\n\n".join(state.accumulated_handoffs)
```

**Interaction with targeted re-route (Component 5):** On re-route, `build_reroute_prompt()` replaces accumulated handoffs entirely. Bounded handoffs caps forward flow; targeted re-route replaces on feedback loops. They are complementary.

---

### Component 4: File Writer

**Files added:** `src/pipeline/file_writer.py` (NEW)
**Files modified:** `src/pipeline/orchestrator.py`
**Change type:** New module + orchestrator integration

**Responsibility:** Parse EXECUTE agent's CODE section, extract file paths and contents from markdown code blocks, write files to disk.

**Integration point:** Called from `orchestrate_pipeline()` after EXECUTE agent completes (after `stream_output` returns sections, before orchestrator decision). NOT inside `WebTaskContext.stream_output()` -- that method is agent-agnostic and must stay that way.

```python
# In orchestrate_pipeline(), after stream_output returns:
sections = await ctx.stream_output(state.current_agent, agent_prompt, {})

if state.current_agent == "execute":
    from src.pipeline.file_writer import write_files_from_sections
    written = await write_files_from_sections(ctx.project_path, sections)
    await ctx.update_status(
        agent="file_writer", state="complete",
        step=f"Wrote {len(written)} files", next_action="Continuing...",
    )
```

**Parser design:** The EXECUTE agent outputs code blocks with file paths in the CODE section:

```
CODE:
```python # src/main.py
import asyncio
...
```  (close)
```

Extract using regex on code block openers: `` ^```\w*\s*#?\s*(.+\.[\w]+)$ `` to capture file path, content until closing triple-backtick.

```python
# src/pipeline/file_writer.py
import os
import re
import logging
from pathlib import Path

log = logging.getLogger(__name__)

CODE_BLOCK_RE = re.compile(
    r'^```\w*\s*#?\s*(.+?)\s*$\n(.*?)^```\s*$',
    re.MULTILINE | re.DOTALL,
)

async def write_files_from_sections(
    project_path: str, sections: dict[str, str]
) -> list[str]:
    """Extract code blocks from CODE section and write to disk."""
    code = sections.get("CODE", "")
    if not code:
        return []

    written = []
    for match in CODE_BLOCK_RE.finditer(code):
        file_path = match.group(1).strip()
        content = match.group(2)
        full_path = Path(project_path) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        written.append(file_path)
        log.info("file_writer: wrote %s (%d chars)", file_path, len(content))

    return written
```

**Key decisions:**
- Overwrite always, git provides recovery (per PROJECT.md design intent)
- Create directories with `mkdir(parents=True, exist_ok=True)`
- Return list of written file paths for UI status updates
- No patch mode -- on re-route iterations, the targeted prompt (Component 5) tells execute to only output changed files, so the writer gets only changed files
- Async function but uses sync file I/O (file writes are fast, no need for `aiofiles`)

**Interaction with auto_commit:** `auto_commit()` already stages files in `src/` and `tests/` plus tracked files. Written files will be picked up naturally. May need to expand staging patterns if files are written outside those directories.

---

### Component 5: Targeted Re-route Prompts

**Files modified:** `src/pipeline/handoff.py`, `src/pipeline/orchestrator.py`
**Change type:** New function in handoff.py + orchestrator re-route branch modification

**Integration:** New function `build_reroute_prompt()` in `handoff.py`:

```python
def build_reroute_prompt(
    review_sections: dict[str, str],
    target_agent: str,
) -> str:
    """Build focused re-route prompt from review feedback."""
    lines = ["=== REVIEW FEEDBACK - FIX REQUIRED ===", ""]

    if target_agent == "execute":
        for key in ("ISSUES", "IMPROVEMENTS"):
            if key in review_sections:
                lines.append(f"{key}:")
                lines.append(review_sections[key])
                lines.append("")
        lines.append("Fix ONLY the issues listed above. Do not rewrite working code.")
        lines.append("Output only the files that need changes.")
    elif target_agent == "plan":
        for key in ("ISSUES", "RISKS", "DECISION"):
            if key in review_sections:
                lines.append(f"{key}:")
                lines.append(review_sections[key])
                lines.append("")
        lines.append("Revise the plan to address these architectural issues.")

    lines.append("=== END REVIEW FEEDBACK ===")
    return "\n".join(lines)
```

**Orchestrator change (line 288-309):** On re-route, replace accumulated handoffs with targeted prompt:

```python
if decision.next_agent in ("plan", "execute") and state.current_agent == "review":
    # Build targeted prompt instead of carrying all handoffs
    reroute_prompt = build_reroute_prompt(sections, decision.next_agent)
    state.accumulated_handoffs = [reroute_prompt]  # Replace, don't append
    # ... rest of re-route logic (iteration check, confirmation) unchanged
```

**Why replace instead of append:** The targeted prompt contains everything the next agent needs to know. Old handoffs are noise at this point -- they describe previous iterations that led to the issues being fixed. The bounded handoff window (Component 3) is for forward flow; targeted re-route is for feedback loops.

---

### Component 6: Dynamic Schema from Registry

**Files modified:** `src/pipeline/orchestrator.py`
**Change type:** Replace hardcoded schema constant with function

**Problem:** `ORCHESTRATOR_SCHEMA` (line 59-77) hardcodes `["plan", "execute", "review", "approved"]`. Adding a new agent (test) requires manual schema update.

**Integration:** Replace the constant with a builder function:

```python
from src.agents.config import AGENT_REGISTRY

def build_orchestrator_schema() -> str:
    """Generate JSON schema with agent enum from registry."""
    agent_names = list(AGENT_REGISTRY.keys()) + ["approved"]
    return json.dumps({
        "type": "object",
        "properties": {
            "next_agent": {"type": "string", "enum": agent_names},
            "reasoning": {"type": "string", "description": "One-line explanation"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["next_agent", "reasoning", "confidence"],
    })

# Usage: call build_orchestrator_schema() in get_orchestrator_decision()
# Can cache at module level if AGENT_REGISTRY is static after import
ORCHESTRATOR_SCHEMA = build_orchestrator_schema()
```

**System prompt generation:** The `orchestrator_system.txt` should also reflect available agents. Two options:

1. Generate prompt text dynamically (requires changing `call_orchestrator_claude` to accept inline text instead of file path)
2. Keep static file, update manually when adding agents

**Recommendation:** Option 2. The system prompt changes rarely (only when adding agents). The schema is the critical part -- it enforces valid JSON responses with correct enum values. Update `orchestrator_system.txt` when adding the test agent. The cognitive overhead of dynamic prompt generation is not worth the marginal maintenance savings.

---

### Component 7: Test Agent

**Files added:** `src/agents/prompts/test_system.txt` (NEW)
**Files modified:** `src/agents/config.py`, `src/pipeline/orchestrator.py` (section filter map), `src/agents/prompts/orchestrator_system.txt`
**Change type:** New agent in registry + prompt file

**Design decision: Static code review, NOT subprocess execution.** Running `pytest` via subprocess adds complexity (venv management, dependency installation, path resolution, security sandboxing). Claude excels at static analysis -- missing error handling, type mismatches, import issues, logic errors.

**Registry entry in config.py:**

```python
"test": AgentConfig(
    name="test",
    system_prompt_file=str(PROMPTS_DIR / "test_system.txt"),
    output_sections=["TEST RESULTS", "FAILURES", "SUGGESTIONS", "HANDOFF"],
    next_agent="review",
),
```

**Pipeline flow change:** Update execute's `next_agent`:

```python
"execute": AgentConfig(
    name="execute",
    system_prompt_file=str(PROMPTS_DIR / "execute_system.txt"),
    output_sections=["TARGET", "PROJECT STRUCTURE", "FILES", "CODE",
                     "COMMANDS", "SETUP NOTES", "HANDOFF"],
    next_agent="test",  # Changed from "review"
),
```

**Pipeline flow:** plan -> execute -> [file_write] -> test -> review

**Orchestrator system prompt update:** Add TEST agent to routing rules:

```
The pipeline has four agents:
- PLAN: Creates a structured development plan
- EXECUTE: Implements the plan by writing code
- TEST: Reviews code for bugs, errors, and quality issues (static analysis)
- REVIEW: Final review of implementation quality

Routing rules:
...
4. If TEST finds critical failures: route to "execute" for fixes
5. If TEST passes: route to "review"
```

**Section filter map update (Component 2):**

```python
ROUTING_SECTIONS["test"] = {"TEST RESULTS", "FAILURES", "HANDOFF"}
```

**Interaction with dynamic schema (Component 6):** If dynamic schema is built first, adding "test" to `AGENT_REGISTRY` automatically includes it in the schema enum. If not, manual schema update is needed -- this is why Component 6 should precede Component 7.

---

### Component 8: Confidence-Based Autonomy

**Files modified:** `src/pipeline/orchestrator.py`, `src/pipeline/protocol.py`, `src/engine/context.py`
**Change type:** Protocol extension + orchestrator logic change

**Integration:** After `get_orchestrator_decision()` returns, check confidence before acting:

```python
# In orchestrate_pipeline(), after getting decision:
decision = await get_orchestrator_decision(state, sections)

# Low confidence gate -- force user confirmation even in autonomous mode
if decision.confidence < 0.5:
    confirmed = await ctx.confirm_reroute(
        decision.next_agent,
        f"LOW CONFIDENCE ({decision.confidence:.0%}): {decision.reasoning}",
        force=True,  # bypass autonomous auto-approve
    )
    if not confirmed:
        state.halted = True
        break
```

**Protocol change:** Add optional `force` parameter to `confirm_reroute`:

```python
# protocol.py
async def confirm_reroute(
    self, next_agent: str, reasoning: str, force: bool = False
) -> bool: ...

# context.py (WebTaskContext)
async def confirm_reroute(
    self, next_agent: str, reasoning: str, force: bool = False
) -> bool:
    if self._mode != "supervised" and not force:
        return True  # auto-approve in autonomous mode
    # Otherwise, wait for user approval
    decision = await self._wait_for_approval(
        "reroute", {"next_agent": next_agent, "reasoning": reasoning}
    )
    return decision == "approve"
```

**Why this goes last:** It touches the Protocol (a shared interface contract). All other features must be stable before adjusting how autonomy decisions flow. The improved decision quality from system prompt fix + section filtering makes confidence scores more meaningful.

---

## Data Flow: Before vs After

### Before (current):

```
prompt + ALL accumulated_handoffs (unbounded)
    -> agent (no system prompt on orchestrator)
    -> ALL sections (truncated to 500 chars each)
    -> orchestrator decision (no system prompt, confidence ignored)
    -> no files written to disk
```

### After (target):

```
prompt + WINDOWED handoffs (last cycle, 8K cap)
    -> agent
    |
    +-- if execute: sections -> file_writer -> disk
    |
    +-- FILTERED sections (routing-relevant only)
    -> orchestrator decision (WITH system prompt, dynamic schema)
    |
    +-- if re-route: TARGETED prompt (ISSUES only) replaces handoffs
    +-- if low confidence: force user confirmation
    |
    +-- if forward to test: test agent reviews before review agent
```

---

## Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `orchestrator.py` | Main loop, state machine, routing | All components below |
| `file_writer.py` (NEW) | Parse CODE section, write to disk | Called by orchestrator after execute |
| `handoff.py` | Build handoff context + re-route prompts | Called by orchestrator |
| `runner.py` | Claude CLI subprocess execution | Called by orchestrator + context |
| `context.py` | Stream output, approval gates | Called by orchestrator |
| `config.py` | Agent registry (declarative) | Read by orchestrator, schema builder |
| `agents/prompts/` | System prompts for each agent | Read by runner |

---

## Recommended Build Order

### Phase 1: Foundation fixes (no new features, immediate quality improvement)

| Step | What | Files | Why This Position |
|------|------|-------|-------------------|
| 1 | System prompt fix | `runner.py`, `orchestrator.py` | Zero risk, 10-minute fix, immediately improves routing |
| 2 | Section filtering | `orchestrator.py` | Reduces wasted tokens, pairs with prompt fix |
| 3 | Bounded handoffs | `orchestrator.py` | Prevents context overflow, must land before file writer |

Steps 1-3 are independent -- can be built in any order or parallelized. Group as one phase because they are all small orchestrator fixes.

### Phase 2: Core output capability

| Step | What | Files | Why This Position |
|------|------|-------|-------------------|
| 4 | File writer | NEW `file_writer.py`, `orchestrator.py` | Most impactful feature -- pipeline finally produces files |
| 5 | Targeted re-route | `handoff.py`, `orchestrator.py` | Makes re-route cycles effective (focused instructions + file writes) |

Step 4 depends on step 3 (bounded handoffs prevent bloat during write-rewrite cycles). Step 5 depends on step 4 (targeted re-routes are meaningful only when files get written).

### Phase 3: Pipeline extension

| Step | What | Files | Why This Position |
|------|------|-------|-------------------|
| 6 | Dynamic schema | `orchestrator.py` | Must land before test agent (avoids manual schema update) |
| 7 | Test agent | NEW `test_system.txt`, `config.py`, `orchestrator_system.txt` | Depends on dynamic schema + file writer + section filtering |

### Phase 4: Autonomy refinement

| Step | What | Files | Why This Position |
|------|------|-------|-------------------|
| 8 | Confidence-based autonomy | `orchestrator.py`, `protocol.py`, `context.py` | Touches Protocol (breaking change); needs stable pipeline first |

### Dependency Graph

```
[1] System prompt fix ----+
[2] Section filtering ----+--> [4] File writer --> [5] Targeted re-route
[3] Bounded handoffs -----+         |
                                    v
                          [6] Dynamic schema --> [7] Test agent
                                                      |
                                                      v
                                              [8] Confidence autonomy
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Putting file_writer inside WebTaskContext.stream_output()

**What:** Making `stream_output` aware of which agent is running and conditionally writing files.
**Why bad:** Violates single responsibility. `stream_output` is agent-agnostic by design -- it streams Claude CLI output, parses sections, and persists to DB. Adding execute-specific logic couples it to agent knowledge and breaks the Protocol contract (other TaskContext implementations would need the same logic).
**Instead:** Call `file_writer` from `orchestrate_pipeline()` after `stream_output` returns, conditioned on `state.current_agent == "execute"`.

### Anti-Pattern 2: Building re-route instructions in the orchestrator system prompt

**What:** Telling the orchestrator Claude to generate targeted instructions for the next agent as part of its routing decision.
**Why bad:** Doubles the orchestrator's job (routing + prompt engineering). The orchestrator should decide WHERE to route, not WHAT to tell the target agent. Also wastes an expensive Claude CLI call on prompt generation when Python can do it deterministically for free.
**Instead:** Extract ISSUES/IMPROVEMENTS sections programmatically in `build_reroute_prompt()`. Deterministic, free, instant.

### Anti-Pattern 3: Running actual test suites in the test agent

**What:** Having the test agent spawn `pytest`/`npm test` subprocesses.
**Why bad:** Requires dependency installation, virtual environment management, security sandboxing. The execute agent already runs in a constrained subprocess. Adding another subprocess layer multiplies failure modes. The project under test may not even have a test framework set up yet.
**Instead:** Static code review via Claude CLI. The test agent reads the code and checks for bugs, missing error handling, type mismatches, import issues. This is what Claude excels at without tooling.

### Anti-Pattern 4: Modifying the Protocol for every new feature

**What:** Adding methods to `TaskContext` for file writing, testing, section filtering, etc.
**Why bad:** Every Protocol change requires updating all implementations (`WebTaskContext`, any future adapters). The Protocol should stay minimal -- it defines UI contract, not pipeline logic.
**Instead:** Only modify Protocol when the change is inherently about UI interaction. The confidence gate (forcing user confirmation) is the one justified case. File writing and testing are pipeline concerns handled in `orchestrate_pipeline()`.

### Anti-Pattern 5: Accumulating targeted re-route prompt alongside old handoffs

**What:** Appending `build_reroute_prompt()` output to existing `accumulated_handoffs` instead of replacing it.
**Why bad:** The agent receives old handoffs (describing the iteration that produced the issues) PLUS the targeted fix list. It must sort out which context is current. The old handoffs are noise -- they describe what was already tried and failed.
**Instead:** `state.accumulated_handoffs = [reroute_prompt]` -- replace entirely. The targeted prompt contains everything needed.

---

## Scalability Considerations

| Concern | Current (3 agents) | After (4 agents + file writer) | Note |
|---------|--------------------|---------------------------------|------|
| Context size | Unbounded handoff growth | 8K cap + windowing | Bounded handoffs prevent degradation |
| CLI calls per cycle | 4 (plan+exec+review+decision) | 6 (plan+exec+test+review+2 decisions) | ~50% more CLI calls per full cycle |
| Disk writes | None (code only in DB) | After each execute run | Git recovery for overwrites |
| Decision quality | No system prompt, all sections | System prompt + filtered sections | Fewer tokens, better routing |
| Agent additions | 3-place manual edit | 1-place registry edit + prompt file | Dynamic schema handles new agents |

---

## Sources

All findings based on direct codebase analysis (HIGH confidence):

- `src/pipeline/orchestrator.py` -- Main loop, state machine, handoff accumulation, decision handling
- `src/agents/config.py` -- Agent registry pattern, `AgentConfig` dataclass, `resolve_pipeline_order()`
- `src/agents/base.py` -- `AgentResult` dataclass, `BaseAgent` lifecycle
- `src/pipeline/handoff.py` -- `build_handoff()` current implementation
- `src/pipeline/protocol.py` -- `TaskContext` Protocol definition (5 methods)
- `src/runner/runner.py` -- `stream_claude()`, `call_orchestrator_claude()` (missing system prompt)
- `src/engine/context.py` -- `WebTaskContext` implementation (approval gates, streaming)
- `src/agents/prompts/orchestrator_system.txt` -- Routing rules (unused due to runner bug)
- `src/agents/prompts/execute_system.txt` -- CODE section format for file writer parser
- `src/agents/prompts/review_system.txt` -- ISSUES/IMPROVEMENTS sections for re-route extraction
- `src/parser/extractor.py` -- `extract_sections()` regex pattern
- `src/git/autocommit.py` -- Staging patterns (`src/`, `tests/`, tracked files)
- `docs/orchestration-improvements.md` -- 8-improvement analysis document

---
*Architecture research for: AI Agent Console v2.3 Orchestration Improvements*
*Researched: 2026-03-14*
