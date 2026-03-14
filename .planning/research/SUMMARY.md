# Project Research Summary

**Project:** AI Agent Console v2.3 — Orchestration Improvements
**Domain:** Multi-agent AI pipeline orchestration (Claude CLI subprocess-based)
**Researched:** 2026-03-14
**Confidence:** HIGH

## Executive Summary

The v2.3 milestone targets eight specific improvements to an already-deployed multi-agent pipeline (Plan/Execute/Review) that orchestrates Claude CLI processes via `asyncio.create_subprocess_exec`. Critically, all eight improvements are internal architecture refactors requiring zero new dependencies — they use Python stdlib and the existing stack. The improvements fall into two categories: bug fixes that should have shipped with v2.0 (the orchestrator and all agents run without their system prompts due to a missing flag in both `call_orchestrator_claude()` and `stream_output()`), and capability extensions that turn the pipeline from a text-generator into a real code builder (file writer) with smarter context management (bounded handoffs, targeted re-routes, section filtering).

The recommended approach follows a strict prerequisite order. Two pre-existing bugs — agents running without system prompts (all agents, not just the orchestrator) and the orchestrator not receiving its role definition — must be fixed first, because every other improvement assumes structured, instruction-following agent output. Once the foundation is solid, the file writer is the highest-impact feature: without it, the pipeline generates code in its database but writes nothing to disk, making `auto_commit` commit empty diffs. The remaining improvements (dynamic schema, test agent, confidence gating) extend and polish the now-functional pipeline.

The key risks are around format assumptions: the file writer depends on the EXECUTE agent producing code blocks in a specific format, which is only reliable after the execute system prompt fix lands. Bounded handoff windowing risks dropping the original plan context on re-route cycles, breaking the execute agent's coherence — this requires pinning the first plan handoff rather than a naive sliding window. The test agent addition creates routing transition gaps in the orchestrator decision handler that must be addressed alongside the dynamic schema work.

## Key Findings

### Recommended Stack

All v2.3 improvements use the existing stack with no new pip dependencies. The work is pure Python — `pathlib`, `re`, `json`, and list operations on existing data structures. The codebase already has everything needed: `AgentConfig` dataclass for the test agent, `accumulated_handoffs: list[str]` for windowing, `confidence: float` on `OrchestratorDecision` for gating, and `AGENT_REGISTRY` for dynamic schema generation.

**Core technologies (no changes to requirements.txt):**
- **Python 3.12 + asyncio:** All pipeline orchestration, subprocess management, context windowing — stdlib only
- **`pathlib` + `re`:** File writer — parse markdown code fences, write files to disk (~80 LOC new module)
- **FastAPI + asyncpg + WebSocket:** Existing web layer, no changes needed
- **Claude CLI via `asyncio.create_subprocess_exec`:** Agent execution model unchanged; only the flags passed to it change

See [STACK.md](STACK.md) for the complete feature-by-feature analysis and the explicit list of libraries NOT to add (LangChain, CrewAI, tiktoken, Redis, aiofiles, GitPython, tree-sitter).

### Expected Features

The 8 improvements are clearly scoped with a dependency order that must be respected. Three are bug fixes disguised as features; five are genuine capability additions.

**Must have (table stakes — pipeline is broken without these):**
- **Agent system prompt fix** — all agents (plan, execute, review) currently run without system prompts; structured output is unreliable without this
- **Orchestrator system prompt fix** — `orchestrator_system.txt` exists but is never loaded; routing decisions lack role definition
- **File writer module** — EXECUTE agent generates code but nothing writes it to disk; auto_commit commits empty diffs
- **Bounded handoff windowing** — unbounded handoff growth degrades context quality after 3+ cycles

**Should have (differentiators that improve quality meaningfully):**
- **Targeted re-route prompts** — focused ISSUES/IMPROVEMENTS extraction for re-route cycles instead of full handoff dumps
- **Smart section filtering** — per-agent section relevance map removes CODE section noise from routing decisions
- **Dynamic schema from registry** — adding agents no longer requires 3-place manual edits; prerequisite for test agent
- **Confidence-based autonomy** — existing `confidence` field (logged but unused) drives control flow; low confidence surfaces to user

**Defer to v2.4+:**
- Subprocess test execution (sandboxed Docker, security boundary needed)
- Cross-task review memory (vector store complexity, marginal value per task)
- LLM-based handoff summarization (extra Claude CLI call per cycle, VPS process slot constraint)
- Diff-based file patching (fragile; full rewrites + git provides same recovery)

See [FEATURES.md](FEATURES.md) for the complete feature dependency graph and complexity assessment.

### Architecture Approach

The existing pipeline is a clear state machine: `orchestrate_pipeline()` loops through agent calls via `ctx.stream_output()`, builds handoffs, calls the orchestrator for decisions, and routes accordingly. The v2.3 changes slot into defined integration points without restructuring the architecture. The `TaskContext` Protocol boundary (decoupling orchestrator from UI) must be respected — file writing and test agent logic belong in `orchestrate_pipeline()`, not inside `WebTaskContext.stream_output()`.

**Major components (new or significantly changed):**
1. **`src/pipeline/file_writer.py` (NEW)** — parses CODE section from execute output, writes files to disk; called from orchestrator after execute completes, before orchestrator decision
2. **`src/pipeline/orchestrator.py` (major refactor)** — bounded handoffs, section filtering, dynamic schema, confidence gating, targeted re-route, file writer integration; ~100 lines changed
3. **`src/agents/prompts/test_system.txt` (NEW)** — test agent system prompt for static code review between execute and review
4. **`src/runner/runner.py` (bug fix)** — add `--system-prompt-file` to both `call_orchestrator_claude()` AND `stream_output()` (the latter is an undocumented pre-existing bug affecting all agents)
5. **`src/agents/config.py` (small addition)** — test agent registry entry, `ROUTING_SECTIONS` dict for section filtering

Target pipeline flow after v2.3: `plan -> execute -> [file_write] -> test -> review`

See [ARCHITECTURE.md](ARCHITECTURE.md) for component integration patterns, data flow diagrams (before/after), and anti-patterns to avoid.

### Critical Pitfalls

1. **Agents run without system prompts** — `WebTaskContext.stream_output()` calls `stream_claude()` without passing `system_prompt_file`, making all agent output less structured and less predictable. Fix this FIRST; it is a prerequisite for every other improvement. Check Docker logs for `--system-prompt-file` in subprocess arguments to detect.

2. **File writer parses code blocks with no enforced format** — the file writer depends on EXECUTE outputting `\`\`\`python # src/main.py` style blocks, but the execute system prompt does not enforce this. Claude varies annotation style between runs. Ship the execute system prompt update and the file writer parser together. Add a zero-file guard: if CODE section is non-empty but zero files extracted, report failure — not silent success.

3. **Bounded handoffs drop original plan context on re-routes** — naive "keep last 3 handoffs" drops the plan handoff, which is the oldest but most critical context for execute on re-route cycles. Pin the first plan handoff as an exempt prefix; window only subsequent cycle handoffs.

4. **Test agent creates invalid routing transitions** — adding "test" to the schema enum without routing transition rules allows the orchestrator to route to "test" from "review" (skipping execute) or loop test indefinitely. Define allowed transitions per agent and validate decisions against them. Build dynamic schema and test agent registry entry in the same phase.

5. **File writer writes to disk before review approval** — broken or incomplete code lands on the filesystem before the review gate. The decision: accept direct-write given git recovery (simpler, per PROJECT.md design intent), document this explicitly, and verify auto_commit does not run mid-pipeline. On re-routes, the second execute output must overwrite the first.

See [PITFALLS.md](PITFALLS.md) for all 13 pitfalls, a "looks done but isn't" checklist, and recovery strategies.

## Implications for Roadmap

Based on research, the dependency structure is unambiguous and drives the phase order. There is no flexibility to reorder: each phase enables the next.

### Phase 1: Bug Fixes and Foundation

**Rationale:** Two pre-existing bugs (agents without system prompts, orchestrator without system prompt) must be fixed before any other improvement. All structured output parsing — required by file writer, section filtering, and targeted re-routes — depends on agents actually following their format instructions. These are low-risk, isolated changes that immediately improve pipeline quality.

**Delivers:** Agents that follow formatting rules, orchestrator that knows its routing role, bounded handoffs that prevent context blowup.

**Implements:**
- Agent system prompt fix: `stream_output()` looks up `AgentConfig` and passes `system_prompt_file`
- Orchestrator system prompt fix: `call_orchestrator_claude()` passes `--system-prompt-file`
- Bounded handoff windowing: sliding window (last complete cycle) with pinned first plan handoff, 8000-char cap at section boundaries

**Avoids:** Pitfall 5 (silent system prompt miss), Pitfall 12 (routing behavior change — review prompt before enabling), Pitfall 2 (plan context loss), Pitfall 9 (mid-content truncation)

**Research flag:** Skip — standard bug fix patterns, no new territory.

### Phase 2: Core Output Capability

**Rationale:** The file writer is the single most impactful feature — the pipeline cannot be a code builder without it. Targeted re-route prompts make re-route cycles meaningful (focused ISSUES list instead of full handoff dump) and pair naturally with the file writer since they control what execute outputs on re-route. Both depend on Phase 1 (file writer depends on structured CODE sections; targeted re-routes depend on structured ISSUES sections).

**Delivers:** Files actually written to disk after execute, focused feedback on re-route cycles, auto-commit that commits real changes.

**Implements:**
- `src/pipeline/file_writer.py` — new module with multi-pattern code block parser, zero-file guard, written-file-list return
- Execute system prompt update — enforce strict `\`\`\`lang # path/to/file` format
- `build_reroute_prompt()` in `handoff.py` — extract ISSUES/IMPROVEMENTS for targeted re-route; replace `accumulated_handoffs` on re-route, not append
- Smart section filtering in `build_orchestrator_prompt()` — `ROUTING_SECTIONS` dict per agent

**Avoids:** Pitfall 1 (zero-file extraction — multi-pattern fallback + zero-file guard), Pitfall 4 (direct-write with git recovery documented), Pitfall 6 (fuzzy section name matching for ISSUES extraction), Pitfall 13 (pass written file list to auto_commit instead of hardcoded `src/` + `tests/` patterns)

**Research flag:** Skip — regex parsing, file I/O, string manipulation; all standard patterns.

### Phase 3: Pipeline Extension

**Rationale:** Dynamic schema must precede the test agent to avoid a 3-place manual edit. Together they extend the pipeline from 3 to 4 agents and add routing transition validation. These features depend on Phase 2 (test agent reviews files on disk from file writer; section filtering already handles test agent sections via `ROUTING_SECTIONS`).

**Delivers:** Extensible agent registry where adding a new agent is a single registry entry, a quality gate between execute and review (static code review via LLM), orchestrator routing that auto-discovers agents.

**Implements:**
- `build_orchestrator_schema()` — dynamic enum from `AGENT_REGISTRY.keys() + ["approved"]`
- Allowed transition validation — `{"execute": ["test", "review"], "test": ["review", "execute"], "review": ["plan", "execute", "approved"]}` with fallback to `AgentConfig.next_agent` on invalid transitions
- `src/agents/prompts/test_system.txt` — test agent system prompt (static code review, no subprocess)
- Test agent registry entry — `next_agent="review"`, update `execute.next_agent="test"`
- Orchestrator system prompt update — add test agent routing rules

**Avoids:** Pitfall 3 (transition rules alongside schema), Pitfall 8 (static LLM review, not subprocess), Pitfall 10 (agent name constants; startup assertion `set(enum) - {"approved"} == set(AGENT_REGISTRY.keys())`)

**Research flag:** Test agent system prompt content warrants care. Review LLM-as-reviewer patterns (Qodo, Aider) before writing `test_system.txt`. The prompt determines whether the test agent catches real bugs or produces noise. This is not an API research question but a prompt authoring question.

### Phase 4: Autonomy Refinement

**Rationale:** Confidence-based gating touches the `TaskContext` Protocol (a shared interface contract), making it a breaking change that affects all Protocol implementations. It belongs last when the pipeline is stable and confidence scores are meaningful (the system prompt fixes in Phase 1 significantly improve score calibration). This phase also inverts the default execution mode from supervised to autonomous-with-fallback.

**Delivers:** Autonomous-by-default pipeline where low-confidence decisions surface to the user in supervised mode (never block in autonomous mode).

**Implements:**
- Confidence threshold logic in `orchestrate_pipeline()` — `< 0.5` logs warning + proceeds in autonomous, requires approval in supervised; `0.5–0.7` logs warning, proceeds in both modes
- Protocol extension: optional `force` parameter on `confirm_reroute()` for supervised low-confidence
- Distinct WebSocket event `low_confidence_warning` separate from `approval_required`

**Avoids:** Pitfall 7 (autonomous mode NEVER blocks — log + proceed; only supervised mode shows approval gate)

**Research flag:** Skip — threshold comparison on existing field; WebSocket event is additive.

### Phase Ordering Rationale

- **Bug fixes before features:** Pitfall 5 shows every v2.3 feature depends on structured agent output, which requires system prompts actually being loaded. Starting with features while this bug exists means testing against unreliable output.
- **File writer before test agent:** The test agent is more useful reviewing files on disk than reviewing code from sections alone. File writer must land first.
- **Dynamic schema before test agent:** Adding "test" to a hardcoded enum and then immediately replacing the enum with dynamic generation is wasted work. Build dynamic generation first.
- **Protocol changes last:** Confidence gating modifies `TaskContext`, a shared interface. Deferring it avoids instability during the more complex Phase 2 and Phase 3 work.
- **Section filtering in Phase 2 (not Phase 1):** While simple, it depends on sections being consistently structured (Phase 1 system prompt fixes deliver this), and it pairs semantically with the file writer work since both deal with structured section output.

### Research Flags

Phases needing deeper research during planning:
- **Phase 3 (test agent prompt):** The `test_system.txt` content is where quality lives. Not an API research question — a prompt authoring question that benefits from reviewing existing LLM code review approaches.

Phases with standard patterns (skip research-phase):
- **Phase 1:** Bug fix patterns (add a subprocess flag, look up config); sliding window list manipulation. All standard.
- **Phase 2:** Regex parsing, file I/O, string extraction from dict. Well-documented Python patterns.
- **Phase 4:** Float comparison, WebSocket event emission. No new territory.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Direct codebase inspection of all modified files; all 8 features use stdlib or existing packages; no external API unknowns |
| Features | HIGH | `docs/orchestration-improvements.md` is the authoritative spec; all 8 improvements analyzed with code-level detail |
| Architecture | HIGH | All integration points verified by reading actual source files (orchestrator.py 343 lines, context.py 200 lines, runner.py 197 lines, etc.) |
| Pitfalls | HIGH | Most pitfalls identified from direct code analysis (reading the specific lines with the bug) rather than inference |

**Overall confidence:** HIGH

### Gaps to Address

- **Test agent system prompt content:** The research defines what sections it should produce and what it must NOT do (no subprocess), but does not draft the actual prompt. This is the one piece of genuine design work remaining. Address during Phase 3 planning.
- **Execute system prompt current format:** The strict code block format (`\`\`\`lang # path/to/file`) is documented as a requirement, but `execute_system.txt` was not inspected for its existing format instructions. Verify before writing the file writer regex to ensure the enforced format aligns with the parser.
- **Allowed transition validation implementation:** Pitfall 3 identifies the need for routing transition validation, and the pattern is clear (allowed transitions dict), but the exact handling of invalid transitions (log + fallback to `AgentConfig.next_agent` vs reject decision) needs a firm decision during Phase 3 implementation.

## Sources

### Primary (HIGH confidence)

- **Direct codebase analysis** — `src/pipeline/orchestrator.py` (343 lines), `src/engine/context.py` (200 lines), `src/runner/runner.py` (197 lines), `src/agents/config.py` (79 lines), `src/pipeline/handoff.py` (38 lines), `src/parser/extractor.py` (47 lines), `src/git/autocommit.py` (80 lines), `src/agents/base.py` (74 lines)
- **`docs/orchestration-improvements.md`** — authoritative spec for all 8 improvements with prioritization
- **`.planning/PROJECT.md`** — v2.3 milestone definition, constraints, out-of-scope items
- **Python 3.12 stdlib docs** — `pathlib`, `re`, `json`, `asyncio.subprocess`

### Secondary (MEDIUM confidence)

- [JetBrains Research: Efficient Context Management](https://blog.jetbrains.com/research/2025/12/efficient-context-management/) — context compression approaches for LLM agents
- [Towards Data Science: How Agent Handoffs Work](https://towardsdatascience.com/how-agent-handoffs-work-in-multi-agent-systems/) — structured context objects (200-500 tokens) vs full forwarding (5,000-20,000 tokens)
- [Google ADK Context Compaction](https://google.github.io/adk-docs/context/compaction/) — sliding window summarization pattern (official docs)
- [Qodo Code Review Platform](https://devops.com/qodo-adds-multiple-ai-agent-to-code-review-platform/) — 15+ automated agentic review workflows, specialized agents
- [Code Surgery: AI Assistants Make Precise Edits](https://fabianhertwig.com/blog/coding-assistants-file-edits/) — Aider's edit format patterns, search/replace fragility

### Tertiary (LOW confidence)

- [Factory.ai: Evaluating Context Compression](https://factory.ai/news/evaluating-compression) — anchored iterative summarization (noted but approach rejected for VPS constraints)

---
*Research completed: 2026-03-14*
*Ready for roadmap: yes*
