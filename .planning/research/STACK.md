# Technology Stack

**Project:** AI Agent Console v2.3 - Orchestration Improvements
**Researched:** 2026-03-14
**Confidence:** HIGH

---

## Context: What Already Exists (Do Not Re-research)

The v2.0-v2.2 stack is validated and deployed:
- Python 3.12, FastAPI >= 0.115, asyncpg >= 0.30, uvicorn >= 0.34
- Claude CLI via `asyncio.create_subprocess_exec` (stream-json and json output modes)
- PostgreSQL 16 with asyncpg connection pool
- Alpine.js 3.x + Tailwind CSS frontend (SPA)
- Pydantic models, pytest, Docker on Coolify

This document covers ONLY what v2.3 orchestration improvements need.

---

## Key Finding: Zero New Dependencies

All eight v2.3 features are **internal architecture refactors** using Python stdlib and existing libraries. This is not an accident -- the improvements target orchestration logic (prompt construction, context windowing, registry patterns), not new integrations.

**Net new pip dependencies: 0**
**Net new frontend dependencies: 0**

---

## Feature-by-Feature Stack Analysis

### 1. File Writer -- `pathlib` + `re` (stdlib)

**Needs:** Parse markdown code fences from EXECUTE agent output, write files to disk.

**Why no library:** The output format is controlled by system prompts (``` ```language # path/to/file ```). A purpose-built regex is more reliable than a generic markdown parser because we define the format. This is ~80 LOC.

**Pattern:**
```python
import re
from dataclasses import dataclass
from pathlib import Path

@dataclass
class FileBlock:
    path: str
    content: str
    language: str

# Match: ```python # src/main.py  or  ```typescript // src/app.ts
FILE_BLOCK_RE = re.compile(
    r'```(\w+)\s*[#/]+\s*(\S+)\s*\n(.*?)```',
    re.DOTALL,
)

def extract_file_blocks(raw_output: str) -> list[FileBlock]:
    return [
        FileBlock(path=m.group(2), content=m.group(3).strip(), language=m.group(1))
        for m in FILE_BLOCK_RE.finditer(raw_output)
    ]

async def write_files(blocks: list[FileBlock], project_path: str) -> list[str]:
    written = []
    for block in blocks:
        target = Path(project_path) / block.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(block.content)
        written.append(str(target))
    return written
```

**Integration point:** Called from `orchestrate_pipeline()` after EXECUTE completes, before handoff to REVIEW. The file writer sits between step 2 (run agent) and step 3 (record history) in the orchestration loop.

**What NOT to use:**
| Avoid | Why |
|-------|-----|
| tree-sitter | Overkill for extracting markdown fenced code blocks from a format we control |
| markdown-it / mistune | Generic markdown parsers don't understand our `# filepath` comment convention |
| aiofiles | `Path.write_text()` is fine -- files are small (code output), and the IO is negligible compared to the Claude CLI call that precedes it |

---

### 2. Targeted Re-route Prompts -- string ops (stdlib)

**Needs:** Extract ISSUES/IMPROVEMENTS from review sections dict, build focused prompt.

**Why no library:** The sections are already parsed by `extract_sections()` into `dict[str, str]`. Building a targeted prompt is string concatenation.

**Pattern:** New function in `src/pipeline/handoff.py`:
```python
def build_reroute_prompt(review_sections: dict[str, str], target_agent: str) -> str:
    issues = review_sections.get("ISSUES", "")
    improvements = review_sections.get("IMPROVEMENTS", "")
    return f"Fix these specific issues found during review:\n\n{issues}\n\n{improvements}\n\nOnly modify files that need changes."
```

**No library needed.** Pure string manipulation on existing data structures.

---

### 3. Bounded Handoffs -- list slicing + `len()` (stdlib)

**Needs:** Window accumulated handoffs to last cycle, cap at 8000 chars.

**Why no library:** The handoffs are `list[str]` on `OrchestratorState`. Windowing is list slicing. Size capping is string truncation.

**Pattern:** Replace unbounded join in `orchestrate_pipeline()`:
```python
# Current (unbounded):
handoff_context = "\n\n".join(state.accumulated_handoffs)

# New (windowed):
HANDOFF_WINDOW = 3  # last cycle = plan + execute + review
HANDOFF_MAX_CHARS = 8000

recent = state.accumulated_handoffs[-HANDOFF_WINDOW:]
handoff_context = "\n\n".join(recent)
if len(handoff_context) > HANDOFF_MAX_CHARS:
    handoff_context = handoff_context[-HANDOFF_MAX_CHARS:]
```

**What NOT to use:**
| Avoid | Why |
|-------|-----|
| tiktoken | Character counting is a good-enough proxy for the 8000-char heuristic. Token counting adds a dependency for marginal accuracy on a threshold that is itself a heuristic. |
| Redis / memcached | Context windowing is in-process list manipulation. No inter-process state needed. |

---

### 4. Orchestrator System Prompt Fix -- one-line change

**Needs:** Pass `--system-prompt-file` to `call_orchestrator_claude()`.

**Pattern:** In `src/runner/runner.py`:
```python
async def call_orchestrator_claude(prompt: str, schema: str, system_prompt_file: str | None = None) -> str:
    cmd = [claude, "-p", "--output-format", "json", "--json-schema", schema, "--dangerously-skip-permissions"]
    if system_prompt_file:
        cmd += ["--system-prompt-file", system_prompt_file]
    cmd.append(prompt)
```

**No library needed.** Literally adding two list elements to an existing subprocess command.

---

### 5. Smart Section Filtering -- dict comprehension (stdlib)

**Needs:** Config mapping agent name to relevant routing sections.

**Pattern:** Add to `src/agents/config.py`:
```python
ROUTING_SECTIONS: dict[str, list[str]] = {
    "plan": ["HANDOFF", "GOAL"],
    "execute": ["HANDOFF", "TARGET"],
    "review": ["DECISION", "ISSUES", "SUMMARY"],
    "test": ["TEST RESULTS", "FAILURES", "HANDOFF"],
}
```

Use in `build_orchestrator_prompt()`:
```python
allowed = ROUTING_SECTIONS.get(state.current_agent, list(latest_sections.keys()))
filtered = {k: v for k, v in latest_sections.items() if k in allowed}
```

**No library needed.** Dict filtering with a static config.

---

### 6. Test Agent -- new prompt file + registry entry

**Needs:** System prompt file, registry config entry, schema enum update.

**Why no library:** The test agent is another Claude CLI call with a different system prompt. It follows the exact same execution pattern as plan/execute/review. The spec explicitly says "static code review, no subprocess" -- so no pytest runner, no test framework integration.

**Pattern:** Add to `AGENT_REGISTRY`:
```python
"test": AgentConfig(
    name="test",
    system_prompt_file=str(PROMPTS_DIR / "test_system.txt"),
    output_sections=["TEST RESULTS", "COVERAGE", "FAILURES", "HANDOFF"],
    next_agent="review",
),
```
Update execute's `next_agent` from `"review"` to `"test"`.

**No library needed.** Config-driven agent registration using existing `AgentConfig` dataclass.

---

### 7. Confidence-Based Autonomy -- float comparison (stdlib)

**Needs:** Threshold checks on existing `decision.confidence` field (already a float 0.0-1.0).

**Pattern:** In `orchestrate_pipeline()`, decision handling:
```python
# Low confidence: force confirmation even in autonomous mode
if decision.confidence < 0.5:
    confirmed = await ctx.confirm_reroute(decision.next_agent, decision.reasoning)
    if not confirmed:
        state.halted = True
        break
# Medium confidence: log warning, proceed
elif decision.confidence < 0.7:
    log.warning("Medium confidence (%.2f) on routing to %s", decision.confidence, decision.next_agent)
# High confidence: proceed silently
```

**No library needed.** Float comparison on an existing field.

---

### 8. Dynamic Schema/Prompt from Registry -- `json` module (stdlib)

**Needs:** Generate orchestrator JSON schema enum from `AGENT_REGISTRY` keys.

**Pattern:** Replace hardcoded `ORCHESTRATOR_SCHEMA`:
```python
def build_orchestrator_schema() -> str:
    agent_names = list(AGENT_REGISTRY.keys()) + ["approved"]
    return json.dumps({
        "type": "object",
        "properties": {
            "next_agent": {
                "type": "string",
                "enum": agent_names,
            },
            "reasoning": {
                "type": "string",
                "description": "One-line explanation of the routing decision",
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
        },
        "required": ["next_agent", "reasoning", "confidence"],
    })
```

For the system prompt template, use f-strings (not Jinja2 -- system prompts are plain text files with at most one dynamic substitution):
```python
def build_orchestrator_system_prompt() -> str:
    agent_descriptions = "\n".join(
        f"- {name}: {', '.join(cfg.output_sections)}"
        for name, cfg in AGENT_REGISTRY.items()
    )
    template = Path(PROMPTS_DIR / "orchestrator_system.txt").read_text()
    return template.replace("{{AGENTS}}", agent_descriptions)
```

**No library needed.** `json.dumps()` and string replacement.

---

## What NOT to Add

| Library | Why People Suggest It | Why Wrong Here |
|---------|----------------------|----------------|
| LangChain / LangGraph | "Agent orchestration framework" | We use Claude CLI via subprocess, not API calls. LangChain's abstractions don't map to subprocess-based execution. We already have a working orchestrator. Adding LangChain would require rewriting the entire execution model. |
| CrewAI / AutoGen | "Multi-agent frameworks" | Same mismatch -- designed for API-based agents. Our agents are Claude CLI processes with system prompt files and structured JSON output. |
| tree-sitter | "Parse code from output" | Overkill. A 10-line regex handles our controlled markdown fenced code block format. |
| Jinja2 (for system prompts) | "Template dynamic prompts" | System prompts have at most one dynamic section (agent list). `str.replace()` is clearer and has zero import overhead. Jinja2 is already in deps but for a different purpose. |
| Redis | "Bounded context store" | Context windowing is a Python list slice. Single-user, single-process. No inter-process state needed. |
| tiktoken | "Token counting for context bounds" | Char counting is adequate for a heuristic threshold. Adding a C-extension dependency for marginal precision on a tunable constant is not justified. |
| Pydantic (for FileBlock) | "Validate file blocks" | A stdlib `@dataclass` with 3 string fields is sufficient. No validation logic needed -- the regex already constrains the shape. |
| aiofiles | "Async file writes" | File writes are tiny (code output files). `Path.write_text()` completes in microseconds. The preceding Claude CLI call takes 10-60 seconds. Async file I/O adds complexity for zero measurable benefit. |
| GitPython | "Git operations" | `asyncio.create_subprocess_exec` already handles git in `autocommit.py`. GitPython is 30MB+ for wrapping the same `git` binary. |

---

## Changes to Existing Dependencies

**None.** All current dependencies stay at their current versions. No version bumps needed.

```txt
# requirements.txt -- NO CHANGES
aiosqlite>=0.20
tenacity>=8.0
textual>=0.50
asyncpg>=0.30
fastapi>=0.115
uvicorn[standard]>=0.34
pydantic-settings>=2.0
httpx>=0.28
jinja2>=3.1
pytest>=8.0
pytest-asyncio>=0.24
```

---

## New Files (no new packages)

| File | Purpose | Estimated Size |
|------|---------|---------------|
| `src/pipeline/file_writer.py` | Extract code blocks from EXECUTE output, write to disk | ~80 LOC |
| `src/agents/prompts/test_system.txt` | Test agent system prompt (static code review) | ~30 lines |

## Modified Files

| File | Change | Scope |
|------|--------|-------|
| `src/pipeline/orchestrator.py` | Bounded handoffs, section filtering, dynamic schema, confidence gating, targeted re-route, file writer call | Major refactor (~100 lines changed) |
| `src/pipeline/handoff.py` | Add `build_reroute_prompt()` | Small addition (~15 LOC) |
| `src/agents/config.py` | Add test agent entry, add `ROUTING_SECTIONS` dict | Small addition (~15 LOC) |
| `src/runner/runner.py` | Add `system_prompt_file` param to `call_orchestrator_claude()` | One-line fix |
| `src/engine/context.py` | Call file writer after execute, handle low-confidence confirmation in autonomous mode | Moderate (~30 LOC) |
| `src/agents/prompts/orchestrator_system.txt` | Add `{{AGENTS}}` placeholder, test agent rules | Rewrite |

---

## Sources

- **Codebase inspection** (HIGH confidence): `src/pipeline/orchestrator.py`, `src/agents/config.py`, `src/pipeline/handoff.py`, `src/engine/context.py`, `src/runner/runner.py`, `src/parser/extractor.py`, `src/agents/base.py`, `src/git/autocommit.py`
- **Feature spec** (HIGH confidence): `docs/orchestration-improvements.md` -- all 8 improvements analyzed with affected files
- **Project context** (HIGH confidence): `.planning/PROJECT.md` -- constraints, key decisions, out-of-scope items
- **Python stdlib docs** (HIGH confidence): `pathlib`, `re`, `json`, `asyncio.subprocess` -- all stdlib, no version concerns on Python 3.12

---
*Stack research for: AI Agent Console v2.3 Orchestration Improvements*
*Researched: 2026-03-14*
