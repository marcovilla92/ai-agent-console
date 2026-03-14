# Feature Landscape

**Domain:** Multi-agent AI pipeline orchestration improvements (v2.3)
**Researched:** 2026-03-14
**Confidence:** HIGH (existing codebase inspected; orchestration-improvements.md provides detailed spec; industry patterns verified via multiple sources)

## Context

This research covers ONLY the 8 new features for v2.3 Orchestration Improvements. The existing pipeline (3-agent Plan/Execute/Review, AI-driven orchestrator with JSON schema decisions, iterative review cycles with 3-iteration limit, structured handoffs, WebSocket streaming, supervised/autonomous modes, git auto-commit) is already shipped and validated.

Key integration points in existing code:
- `src/pipeline/orchestrator.py` -- main orchestration loop, `OrchestratorState` with `accumulated_handoffs` list, `build_orchestrator_prompt()` with 500-char truncation, hardcoded `ORCHESTRATOR_SCHEMA` enum
- `src/pipeline/handoff.py` -- `build_handoff()` concatenates all sections from `AgentResult`
- `src/agents/config.py` -- `AGENT_REGISTRY` dict with `AgentConfig` dataclass, `resolve_pipeline_order()`
- `src/runner/runner.py` -- `call_orchestrator_claude()` missing `--system-prompt-file` flag
- `src/engine/context.py` -- `WebTaskContext` with `stream_output()`, `confirm_reroute()`, approval gates
- `src/agents/prompts/` -- system prompt text files per agent + `orchestrator_system.txt` (exists but unused)
- `src/git/autocommit.py` -- `auto_commit()` assumes files already exist on disk

---

## Table Stakes

Features the pipeline needs to produce real, usable output. Without these, the system generates text but does not actually build anything.

| Feature | Why Expected | Complexity | Dependencies on Existing | Notes |
|---------|--------------|------------|--------------------------|-------|
| File writer module | The EXECUTE agent generates full code in its CODE section but nothing writes it to disk. Without this, the pipeline is a text generator, not a code builder. The `auto_commit` already assumes files exist. This is the single most critical gap. | MEDIUM | Extends `orchestrator.py` (call writer after execute completes). Uses `AgentResult.sections["CODE"]` from `stream_output()`. Needs project path from `ctx.project_path`. | Parse markdown code blocks with file path annotations (`\`\`\`python # src/main.py`). Create directories with `os.makedirs(exist_ok=True)`. Write files. First iteration: write all files. Re-route iterations: write only files mentioned in ISSUES (patch mode). New file: `src/pipeline/file_writer.py`. |
| Orchestrator system prompt fix | `call_orchestrator_claude()` in `runner.py` does not pass `--system-prompt-file`. The file `orchestrator_system.txt` exists but is never used. The orchestrator makes routing decisions without its role definition, meaning it operates on raw inference without instructions about what "approved" means or when to re-route. | LOW | Modifies `src/runner/runner.py` (add `--system-prompt-file` flag). Modifies `orchestrator.py` (pass prompt file path to the call). | This is a bug fix, not a feature. One-line change in the subprocess command construction. Should be done first because it immediately improves all subsequent orchestrator decisions. |
| Bounded handoff windowing | `orchestrator.py:224-226` concatenates ALL handoffs from every agent across every iteration into `accumulated_handoffs`. After 3 cycles (9 agent runs), the prompt can exceed Claude's effective context or degrade response quality. Industry consensus: structured context objects with 200-500 tokens beat full forwarding at 5,000-20,000 tokens. | LOW | Modifies `orchestrator.py` only (handoff windowing logic in the main loop where `agent_prompt` is built). | Keep only the last complete cycle (plan+execute+review handoffs). Cap total handoff text at 8000 chars. Older handoffs discarded, not summarized (summarization adds an LLM call which costs time and a CLI process slot on a 2-concurrent-max VPS). Simple sliding window is the right approach here. |
| Targeted re-route prompts | When review says "BACK TO EXECUTE", the execute agent receives the original prompt + all accumulated handoffs and must infer what went wrong. No focused message about what to fix. This causes the agent to re-read everything and often miss the specific issues. | LOW | Modifies `orchestrator.py` (build targeted prompt on re-route decision). Modifies `handoff.py` (add `build_reroute_prompt()` that extracts ISSUES and IMPROVEMENTS sections from review output). | Extract ISSUES and IMPROVEMENTS sections from the review agent's output. Build a focused prompt: "Fix these specific issues: 1. [issue] 2. [issue]. Only modify files that need changes." This replaces the full handoff dump on re-route paths only. |

---

## Differentiators

Features that elevate the pipeline from "functional" to "smart". Not expected in a basic agent pipeline, but provide meaningful improvement to output quality and developer experience.

| Feature | Value Proposition | Complexity | Dependencies on Existing | Notes |
|---------|-------------------|------------|--------------------------|-------|
| Smart section filtering for orchestrator | The orchestrator currently receives all sections truncated to 500 chars. The CODE section (irrelevant for routing) wastes tokens while DECISION (critical, usually short) is always within limit. Per-agent filtering means the orchestrator sees only what matters for its routing decision: after REVIEW, only DECISION/ISSUES/SUMMARY; after EXECUTE, only HANDOFF/TARGET; after PLAN, only HANDOFF/GOAL. | LOW | Modifies `build_orchestrator_prompt()` in `orchestrator.py`. Uses `state.current_agent` to determine which sections to include. Section names come from `AgentConfig.output_sections` in `config.py`. | Define a `ROUTING_SECTIONS` dict mapping agent name to list of section names relevant for routing. Filter `latest_sections` before building the prompt. Remove the blanket 500-char truncation for included sections (they are already concise by design). |
| Confidence-based decision gating | The `confidence` field (0.0-1.0) from the orchestrator's JSON response is logged to DB but never used for control flow. A fallback text parse (confidence=0.3) is treated identically to a structured response (confidence=0.95). Using confidence as a gate means: high confidence proceeds automatically, low confidence pauses for user review even in autonomous mode. | LOW | Modifies `orchestrator.py` (confidence branching after decision parsing). Modifies `ctx` calls for low-confidence confirmation in `engine/context.py`. | Thresholds: >= 0.7 proceed automatically; 0.5-0.7 log warning, proceed; < 0.5 request user confirmation even in autonomous mode. Default mode becomes autonomous (no confirmations unless low confidence). This inverts the current default (supervised) to match the project goal of "confidence-based autonomy." |
| Test agent (static code review) | No quality gate exists between execute and review. The review agent does both code review AND pipeline routing decision, conflating two concerns. A dedicated test agent between execute and review focuses solely on code quality: syntax validation, import checking, type consistency, structure verification. No subprocess execution -- static analysis only (safe for VPS). | MEDIUM | New file: `src/agents/prompts/test_system.txt`. Modifies `config.py` (add "test" to AGENT_REGISTRY with `next_agent="review"`; update execute's `next_agent` to "test"). Modifies `orchestrator_system.txt` (add test agent routing rules). | Output sections: TEST RESULTS, COVERAGE GAPS, FAILURES, SUGGESTIONS, HANDOFF. The test agent reads the CODE section from execute's handoff and evaluates without running anything. This is an LLM-as-reviewer pattern, not a subprocess runner. Industry data: AI code review catches 42-48% more bugs than human review alone. The review agent then focuses on architectural decisions and approval, not syntax. |
| Dynamic schema/prompt from agent registry | The JSON schema in `orchestrator.py:59-77` hardcodes `["plan", "execute", "review", "approved"]`. The orchestrator system prompt also hardcodes agent names. Adding a new agent (like "test") requires changes in 3 places. Dynamic generation from `AGENT_REGISTRY` means adding an agent to the registry automatically updates the schema enum and the orchestrator's knowledge of available agents. | LOW | Modifies `orchestrator.py` (generate `ORCHESTRATOR_SCHEMA` dynamically from `AGENT_REGISTRY.keys() + ["approved"]`). Modifies `orchestrator_system.txt` (template with `{agent_list}` placeholder rendered at startup). | Generate enum: `agent_names = list(AGENT_REGISTRY.keys()) + ["approved"]`. Generate prompt section describing each agent's role from registry metadata. This makes the test agent addition zero-config from the orchestrator's perspective. |

---

## Anti-Features

Features that seem like natural extensions but should be explicitly excluded from v2.3 scope.

| Anti-Feature | Why Tempting | Why Avoid | What to Do Instead |
|--------------|-------------|-----------|-------------------|
| LLM-based handoff summarization | "Summarize old handoffs instead of discarding them" | Adds an extra Claude CLI call per iteration. On a VPS with max 2 concurrent CLI processes (asyncio.Semaphore), this blocks the pipeline. The cost (time + process slot) exceeds the value of preserving old context. Google ADK uses this but assumes API access, not CLI subprocess constraints. | Simple sliding window: keep last cycle, discard older. 8000-char cap. The most recent cycle contains the most relevant context. |
| Subprocess test execution (pytest, npm test) | "The test agent should actually run the tests" | Security risk: executing arbitrary generated code on the VPS. Resource risk: test suites can hang, consume RAM, or write to filesystem unexpectedly. The VPS runs production services (n8n, Evolution API). Subprocess execution is a fundamentally different trust model. | Static code review only. The test agent reads code and identifies issues through LLM analysis. No `subprocess.run()`. No `pytest`. If real test execution is needed, it belongs in a sandboxed Docker container in a future milestone. |
| Diff-based file patching (search/replace blocks) | "On re-routes, apply diffs instead of full file rewrites" | Diff application is fragile. Aider's experience shows LLMs operate on potentially outdated views of files, making search blocks fail when files have been modified or contain similar sections. Full file rewrites are simpler and git provides the recovery mechanism. | Full file overwrite on every write. Git auto-commit after each approved cycle provides rollback. The file writer writes complete files, not patches. `git diff` shows what changed. |
| Multi-file transaction (atomic writes) | "Either all files write successfully or none do" | Over-engineering for a single-user VPS tool. Partial writes are recoverable via git. Atomic multi-file writes require temp directories, rename operations, and rollback logic that adds complexity without matching a real failure mode (disk full is the only realistic scenario, and atomic writes don't help there). | Write files sequentially. If a write fails mid-way, the files already written are still valid. Git status shows what was written. The user can re-run the task. |
| Agent priority/weight system | "Some agents should be preferred over others in routing" | The orchestrator already uses confidence scores and structured reasoning. Adding agent weights creates a second routing signal that conflicts with or overrides the AI's judgment. The whole point of AI-driven orchestration is that the LLM decides, not a weight table. | Use the confidence threshold system. If the orchestrator consistently makes bad routing decisions, fix the system prompt (improvement #4), not the routing mechanism. |
| Review agent memory across tasks | "The review agent should remember issues from previous tasks on the same project" | Cross-task memory requires a vector store or summary DB, retrieval logic, and relevance filtering. The complexity is high and the value is low: each task is a discrete unit of work. Project-level patterns belong in CLAUDE.md, not in agent memory. | Project context assembly (already built in v2.1) provides project-level knowledge via CLAUDE.md and planning docs. Per-task context is sufficient. |
| Configurable iteration limits per agent | "Let users set max iterations to 5 or 10 instead of 3" | More iterations without quality improvements just burns tokens. The 3-iteration limit is a safety valve, not a tuning knob. If 3 iterations don't converge, the prompt or the approach is wrong. | Keep the hardcoded 3-iteration limit. The confidence gating and targeted re-routes will improve convergence rate within 3 iterations, making higher limits unnecessary. |

---

## Feature Dependencies

```
[System prompt fix (#4)]
    |-- no dependencies, standalone bug fix
    |-- improves ALL subsequent orchestrator decisions
    |-- MUST be done first

[Bounded handoffs (#3)]
    |-- no dependencies, modifies orchestrator.py only
    |-- can be done in parallel with #4

[Targeted re-route prompts (#2)]
    |-- requires: review agent output with ISSUES/IMPROVEMENTS sections (already exists)
    |-- modifies: orchestrator.py (re-route path) + handoff.py (new function)
    |-- benefits from: #4 (better orchestrator decisions on when to re-route)

[Smart section filtering (#5)]
    |-- requires: AGENT_REGISTRY with output_sections (already exists)
    |-- modifies: build_orchestrator_prompt() in orchestrator.py
    |-- benefits from: #4 (system prompt tells orchestrator what sections mean)

[File writer (#1)]
    |-- requires: stream_output() returning sections dict (already exists)
    |-- requires: ctx.project_path (already exists)
    |-- modifies: orchestrator.py (trigger write after execute completes)
    |-- new file: src/pipeline/file_writer.py
    |-- enables: auto_commit to actually commit real files

[Confidence-based autonomy (#7)]
    |-- requires: orchestrator decision with confidence field (already exists)
    |-- modifies: orchestrator.py (decision handling block)
    |-- modifies: engine/context.py (low-confidence confirmation flow)
    |-- benefits from: #4 (better calibrated confidence with system prompt)

[Dynamic schema/prompt (#8)]
    |-- requires: AGENT_REGISTRY (already exists)
    |-- modifies: orchestrator.py (schema generation)
    |-- modifies: orchestrator_system.txt (template)
    |-- MUST be done before or alongside #6 (test agent)

[Test agent (#6)]
    |-- requires: #8 (dynamic schema so test agent is auto-discovered)
    |-- requires: #1 (file writer, so test agent reviews actual written files)
    |-- new files: test_system.txt, config.py update
    |-- modifies: execute config (next_agent: "test" instead of "review")
```

### Critical Path

```
#4 (system prompt fix) ----+
                            |
#3 (bounded handoffs) -----+--> #2 (targeted re-routes) --> #1 (file writer)
                            |                                      |
#5 (section filtering) ----+                                      |
                            |                                      v
#7 (confidence gating) ----+            #8 (dynamic schema) --> #6 (test agent)
```

### Dependency Notes

- **System prompt fix (#4) is zero-risk, high-impact.** The file already exists. The flag just needs to be added to the CLI command. This should ship first because every other improvement benefits from the orchestrator actually knowing its role.

- **File writer (#1) and test agent (#6) are the two features with new files.** Everything else modifies existing code. The file writer is higher priority because without it, the pipeline doesn't produce filesystem output -- the test agent can review code from sections even without files on disk.

- **Dynamic schema (#8) MUST precede test agent (#6).** Adding "test" to the hardcoded enum and then immediately replacing the enum with dynamic generation is wasted work. Build dynamic generation first, then adding the test agent is just a registry entry.

- **Bounded handoffs (#3) and targeted re-routes (#2) are complementary.** Bounded handoffs reduce noise; targeted re-routes increase signal. Together they fix the context quality problem from both ends. However, they are independent changes and can be implemented separately.

- **Confidence gating (#7) changes the default execution mode.** Currently supervised is the default. After #7, autonomous becomes the default with confidence-based fallback to user confirmation. This is a behavioral change that affects the user experience. The frontend already supports both modes -- this changes which one is active by default.

---

## MVP Recommendation

### Phase 1: Foundation fixes (do first, lowest risk)
1. **System prompt fix (#4)** -- bug fix, one-line change, immediate quality improvement
2. **Bounded handoffs (#3)** -- prevents context blowup, simple sliding window
3. **Targeted re-route prompts (#2)** -- focused feedback on re-routes

### Phase 2: Core output capability
4. **File writer (#1)** -- the pipeline finally produces real files
5. **Smart section filtering (#5)** -- cleaner orchestrator inputs

### Phase 3: Intelligence and extensibility
6. **Confidence-based autonomy (#7)** -- default autonomous, smart fallback
7. **Dynamic schema/prompt (#8)** -- extensible agent routing
8. **Test agent (#6)** -- quality gate between execute and review

### Defer to v2.4+
- Subprocess test execution (sandboxed Docker)
- Cross-task review memory
- LLM-based handoff summarization
- Diff-based file patching

---

## Complexity Assessment

| Feature | Complexity | Reason |
|---------|------------|--------|
| System prompt fix (#4) | LOW | Add one flag to subprocess command, pass file path. |
| Bounded handoffs (#3) | LOW | Replace list concatenation with sliding window in orchestrator loop. ~15 lines changed. |
| Targeted re-route (#2) | LOW | New function `build_reroute_prompt()` in handoff.py, called from orchestrator re-route path. ~30 lines new code. |
| Section filtering (#5) | LOW | Dict lookup + filter in `build_orchestrator_prompt()`. ~20 lines changed. |
| Confidence gating (#7) | LOW | Add threshold checks after decision parsing. ~20 lines changed. Behavioral change needs frontend awareness. |
| Dynamic schema (#8) | LOW | Generate enum from registry keys. Template the system prompt. ~25 lines changed. |
| File writer (#1) | MEDIUM | Regex parsing of markdown code blocks, directory creation, file I/O, error handling for malformed output. New module ~100-150 lines. |
| Test agent (#6) | MEDIUM | New system prompt (content design is the hard part), registry entry, orchestrator prompt update. ~50 lines code + system prompt authoring. |

---

## Sources

- `docs/orchestration-improvements.md` -- primary spec with 8 improvements, prioritized. HIGH confidence, authoritative.
- `src/pipeline/orchestrator.py` -- existing orchestration loop, handoff accumulation, schema, prompt building. Inspected directly.
- `src/pipeline/handoff.py` -- existing handoff builder, section concatenation. Inspected directly.
- `src/agents/config.py` -- existing agent registry with AgentConfig dataclass. Inspected directly.
- [JetBrains Research: Smarter Context Management for LLM-Powered Agents](https://blog.jetbrains.com/research/2025/12/efficient-context-management/) -- context compression approaches. MEDIUM confidence.
- [How Agent Handoffs Work in Multi-Agent Systems](https://towardsdatascience.com/how-agent-handoffs-work-in-multi-agent-systems/) -- structured context objects (200-500 tokens) vs full forwarding (5,000-20,000 tokens). MEDIUM confidence.
- [Google ADK Context Compaction](https://google.github.io/adk-docs/context/compaction/) -- sliding window summarization pattern. HIGH confidence (official docs).
- [Ralph Orchestrator: Context Management](https://mikeyobrien.github.io/ralph-orchestrator/advanced/context-management/) -- fresh context per iteration pattern. MEDIUM confidence.
- [Factory.ai: Evaluating Context Compression](https://factory.ai/news/evaluating-compression) -- anchored iterative summarization. MEDIUM confidence.
- [Qodo Code Review Platform](https://devops.com/qodo-adds-multiple-ai-agent-to-code-review-platform/) -- 15+ automated agentic review workflows, specialized agents. MEDIUM confidence.
- [llm-code-format (GitHub)](https://github.com/vizhub-core/llm-code-format) -- streaming markdown code block parser with file path extraction. MEDIUM confidence.
- [parse-llm-code (PyPI)](https://pypi.org/project/parse-llm-code/) -- Python library for extracting code blocks from LLM output. MEDIUM confidence.
- [Code Surgery: How AI Assistants Make Precise Edits](https://fabianhertwig.com/blog/coding-assistants-file-edits/) -- Aider's edit format patterns, search/replace fragility. MEDIUM confidence.
- [AI Coding Agents 2026: Coherence Through Orchestration](https://mikemason.ca/writing/ai-coding-agents-jan-2026/) -- validation before commit pattern. MEDIUM confidence.

---
*Feature research for: AI Agent Workflow Console -- v2.3 Orchestration Improvements*
*Researched: 2026-03-14*
