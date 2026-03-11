# Project Research Summary

**Project:** AI Agent Workflow Console
**Domain:** Python TUI multi-agent AI orchestration
**Researched:** 2026-03-11
**Confidence:** HIGH

## Executive Summary

This project is a terminal-based multi-agent AI coding console built with Python and Textual. It orchestrates three Claude CLI agents (PLAN, EXECUTE, REVIEW) through an AI-driven decision loop, displayed in a 4-panel TUI. Experts build this type of tool by combining an async subprocess runner for Claude CLI with a message-driven TUI framework, connecting them through an explicit finite state machine. The recommended stack (Textual + asyncio + Pydantic + aiosqlite) is mature, well-documented, and purpose-built for this exact use case -- there are no significant technology risks.

The recommended approach is to build bottom-up: data models and subprocess infrastructure first, then the orchestrator engine, then the TUI shell that wires everything together. The core differentiator -- an AI-driven orchestrator that decides which agent runs next based on output quality -- should be implemented with a rule-based fallback before adding LLM-driven routing. This de-risks the most complex component while delivering value incrementally. The 4-panel layout and streaming output are the visual identity and must work reliably from the earliest prototype.

The primary risks are (1) subprocess deadlocks from improper stream reading, (2) structured output parsing brittleness when Claude deviates from the expected format, and (3) orchestrator infinite loops during review-execute cycles. All three are well-understood problems with established prevention patterns: concurrent stream consumption, multi-layer parsing with fallbacks, and hard iteration limits with user confirmation gates. The biggest unknown is Claude CLI's streaming behavior with `stream-json` format -- text streams incrementally but structured output does not, which means the display and parsing architectures must be separate concerns.

## Key Findings

### Recommended Stack

The stack is Python 3.12+ with Textual 8.x as the TUI framework, managed by uv. All core dependencies are mature, async-native, and compatible.

**Core technologies:**
- **Textual 8.1.1**: TUI framework -- only serious modern Python TUI option; async-native, rich widgets, CSS styling, Workers API for subprocess streaming
- **asyncio (stdlib)**: Subprocess orchestration -- `create_subprocess_exec` for streaming Claude CLI output; integrates seamlessly with Textual's event loop
- **Pydantic 2.12.5**: Output validation -- validates agent output contracts; handles malformed LLM output gracefully with clear error messages
- **aiosqlite 0.22.1**: Async persistence -- prevents blocking the Textual event loop during DB writes; simple API
- **uv**: Package management -- 10-100x faster than pip; deterministic lockfile; the new Python standard

**Critical "do not use" decisions:** No LLM agent frameworks (LangChain, PydanticAI) -- they fight the subprocess-based architecture. No alternative async runtimes (trio/anyio) -- Textual is built on asyncio specifically. No curses/ncurses -- poor Windows support.

### Expected Features

**Must have (table stakes):**
- Real-time streaming output from Claude CLI subprocesses
- 4-panel TUI layout (Prompt, Plan, Execute, Review)
- PLAN/EXECUTE/REVIEW agents with structured output contracts
- Session persistence via SQLite (resume across terminal sessions)
- Keyboard-driven workflow (terminal users demand this)
- Status bar showing current agent, state, step count
- Error handling with retry and exponential backoff
- Project/workspace isolation (one project = one folder)

**Should have (differentiators):**
- AI-driven orchestrator deciding next agent (core differentiator vs. all competitors)
- Iterative review cycles with APPROVE/REVISE/REJECT decision loop
- Visible agent handoff contracts between panels (builds trust)
- Cost/token tracking per agent per cycle
- Git auto-commit after successful cycles

**Defer (v2+):**
- Pluggable agent architecture (add agents via config)
- Parallel agent execution
- Additional agents (DEBUG, TEST, DEPLOY)
- Multi-model support, web UI, voice input

### Architecture Approach

The architecture follows a 4-layer design: TUI Layer (Textual widgets) communicates with the Orchestrator Engine via Textual messages (never direct calls). The Orchestrator manages a finite state machine (IDLE -> PLANNING -> EXECUTING -> REVIEWING -> DONE/ITERATE) and dispatches work to the Agent Runner, which launches Claude CLI subprocesses with async streaming. The Persistence Layer (SQLite) stores sessions, outputs, and state independently.

**Major components:**
1. **TUI Layer** -- 4 panels + status bar; renders streaming output; posts messages upward for all user actions
2. **Orchestrator Engine** -- FSM-based state management + agent routing (rule-based initially, AI-driven later)
3. **Agent Runner** -- async subprocess launcher with line-by-line streaming back to TUI via messages
4. **Agent Definitions** -- system prompts + output contracts per agent type (pure data, no logic)
5. **Persistence Layer** -- aiosqlite CRUD for sessions, agent outputs, workspace context

**Key architectural insight:** The orchestrator and TUI are independent until the App wires them together. They can be developed and tested in parallel after the models layer exists.

### Critical Pitfalls

1. **Subprocess deadlocks** -- Never call `process.wait()` before consuming stdout/stderr. Use `asyncio.gather` to read both streams concurrently. Test with 1MB+ output.
2. **Structured output parsing brittleness** -- LLM output compliance is ~94% at best. Build multi-layer parsing: strict parse -> lenient regex fallback -> retry. Use markdown section markers (`## SECTION`), not JSON.
3. **Event loop blocking** -- Any sync call in a Textual message handler freezes the entire UI. Use `@work` decorator or `run_worker()` for ALL subprocess and I/O operations from day one.
4. **Orchestrator infinite loops** -- AI-driven routing can get stuck in REVIEW-EXECUTE cycles. Hard limit of 3 iterations before forcing user confirmation. Track state transitions and detect cycles.
5. **Context window exhaustion** -- Accumulated history exceeds practical limits after 2-3 iterations. Pass only HANDOFF sections forward, not full outputs. Summarize older outputs.
6. **Claude CLI stream-json limitation** -- Structured output does NOT stream incrementally. Stream text for display, parse sections only after completion.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Foundation (Models + Subprocess + Persistence)
**Rationale:** Everything depends on reliable data models, subprocess communication, and storage. The architecture research explicitly identifies this as the zero-dependency base layer. All critical pitfalls (deadlocks, event loop blocking, SQLite WAL mode) must be addressed here.
**Delivers:** Data models (session, state, agent definitions), async subprocess runner with streaming, SQLite schema with WAL mode, section-based output parser with fallback layers.
**Addresses:** Subprocess streaming, session persistence, structured agent output, error handling with retry.
**Avoids:** Subprocess deadlocks (Pitfall 1), event loop blocking (Pitfall 3), stream-json display issues (Pitfall 6), SQLite concurrency issues.

### Phase 2: Agent Pipeline (PLAN + EXECUTE + REVIEW)
**Rationale:** With infrastructure in place, build the three core agents and their contracts. This is where the product's value emerges. Agent definitions are pure data (prompts + contracts) so they are low-risk, but the integration with the runner and parser needs testing with real Claude CLI output.
**Delivers:** PLAN agent with GOAL/TASKS/ARCHITECTURE/FILES/HANDOFF contract, EXECUTE agent with code generation contract, REVIEW agent with DECISION (APPROVE/REVISE/REJECT) contract. Rule-based sequential pipeline (PLAN -> EXECUTE -> REVIEW).
**Addresses:** Multi-file context awareness, structured agent contracts, basic pipeline flow.
**Avoids:** Output parsing brittleness (Pitfall 2), context window exhaustion (Pitfall 5).

### Phase 3: TUI Shell (4-Panel Layout + Keyboard + Status)
**Rationale:** The TUI can be built in parallel with Phase 2 after models exist, but full integration requires the agent pipeline. This phase creates the visual identity: 4-panel layout with streaming, keyboard shortcuts, status bar.
**Delivers:** Textual App with Prompt/Plan/Execute/Review panels, real-time streaming display, keyboard shortcuts for all actions, status bar, dark theme, message-driven communication between TUI and orchestrator.
**Addresses:** Real-time streaming output, keyboard-driven workflow, status/progress indicators, dark theme.
**Avoids:** Widget-calls-orchestrator anti-pattern, re-rendering performance trap.

### Phase 4: Orchestrator Intelligence (AI-Driven Routing + Iteration)
**Rationale:** The orchestrator is the core differentiator but also the highest-complexity component. Building it after the agent pipeline and TUI are stable means it can be tested against real agent outputs. Start rule-based, upgrade to AI-driven.
**Delivers:** AI-driven routing (Claude CLI meta-call to decide next agent), iterative review cycles with user confirmation gates, cycle detection, hard iteration limits, cost budget per session.
**Addresses:** AI-driven orchestrator, iterative review cycles, visible handoff contracts.
**Avoids:** Orchestrator infinite loops (Pitfall 4), runaway token costs.

### Phase 5: Polish and v1.x Features
**Rationale:** Once the core loop works end-to-end, add the features that improve daily usage: git integration, token tracking, session history, resizable panels.
**Delivers:** Git auto-commit after cycles, token/cost tracking per agent, session history browser, resizable/collapsible panels, crash recovery.
**Addresses:** Git integration, cost tracking, session history, panel flexibility.

### Phase Ordering Rationale

- **Phases 1-2 before 3:** The TUI needs real data to display. Building panels before the pipeline produces hollow widgets that need rework.
- **Phase 2 before 4:** The orchestrator routes between agents. Without working agents, the orchestrator cannot be meaningfully tested.
- **Phase 4 after 3:** The orchestrator's decisions are visible in the TUI. Testing the orchestrator with visual feedback catches issues that unit tests miss.
- **Phase 5 last:** Polish features have no dependencies on unproven patterns. They are safe to parallelize and deprioritize.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1:** Claude CLI `stream-json` behavior needs hands-on experimentation. The documented limitation (structured output does not stream) needs verification with current CLI version.
- **Phase 4:** AI-driven routing prompt design is novel -- no established patterns exist for TUI orchestrator meta-prompts. Will need iterative prompt engineering.

Phases with standard patterns (skip research-phase):
- **Phase 2:** Agent prompt engineering follows well-documented patterns from the competitor analysis (aider architect mode, OpenCode Build/Plan).
- **Phase 3:** Textual TUI development is thoroughly documented with official guides, examples, and the textual-dev tooling.
- **Phase 5:** Git integration, token parsing, and session management are all standard CRUD patterns.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All libraries verified on PyPI with current versions. Textual 8.1.1 released 2026-03-10. No version conflicts. |
| Features | HIGH | Competitor analysis covers 7+ tools with detailed feature matrices. Clear consensus on table stakes. |
| Architecture | HIGH | Patterns sourced from official Textual docs, Google/Microsoft architecture guides, and multiple production agent systems. |
| Pitfalls | HIGH (core) / MEDIUM (CLI-specific) | Subprocess and TUI pitfalls are well-documented. Claude CLI streaming behavior has fewer sources and may change between versions. |

**Overall confidence:** HIGH

### Gaps to Address

- **Claude CLI `stream-json` exact behavior:** Research identified a known limitation but the exact message format and timing need hands-on verification in Phase 1. Build a minimal streaming test before committing to the display architecture.
- **Windows-specific Textual rendering:** Research flags Windows Terminal vs. legacy conhost differences. Manual testing on Windows is needed in Phase 3 -- automated tests cannot fully verify terminal rendering.
- **Orchestrator prompt effectiveness:** The AI-driven routing prompt has no established pattern to follow. Phase 4 will need empirical testing with diverse prompts to tune the routing meta-prompt. Budget time for prompt iteration.
- **Context window management strategy:** The "pass only HANDOFF sections" approach is sound in theory but needs validation with real agent output sizes. Measure actual token counts in Phase 2 before finalizing the summarization strategy.

## Sources

### Primary (HIGH confidence)
- [Textual PyPI](https://pypi.org/project/textual/) -- v8.1.1, Python 3.9+
- [Textual Workers Guide](https://textual.textualize.io/guide/workers/) -- subprocess streaming pattern
- [Textual Events and Messages Guide](https://textual.textualize.io/guide/events/) -- message-driven communication
- [Pydantic PyPI](https://pypi.org/project/pydantic/) -- v2.12.5, validation patterns
- [Python asyncio Subprocess Docs](https://docs.python.org/3/library/asyncio-subprocess.html) -- stream reading patterns
- [aiosqlite PyPI](https://pypi.org/project/aiosqlite/) -- v0.22.1, async SQLite

### Secondary (MEDIUM confidence)
- [Google Cloud: Agentic AI Design Patterns](https://docs.google.com/architecture/choose-design-pattern-agentic-ai-system) -- pipeline and orchestrator patterns
- [Microsoft: AI Agent Orchestration Patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns) -- multi-agent architectures
- [GitHub Blog: Multi-agent workflows](https://github.blog/ai-and-ml/generative-ai/multi-agent-workflows-often-fail-heres-how-to-engineer-ones-that-dont/) -- engineering recommendations
- [OpenCode GitHub](https://github.com/opencode-ai/opencode) -- 95K+ stars, TUI reference implementation
- [Competitor analysis](https://pinggy.io/blog/top_cli_based_ai_coding_agents/) -- market overview of CLI coding agents

### Tertiary (LOW confidence)
- [Claude CLI stream-json issue #15511](https://github.com/anthropics/claude-code/issues/15511) -- structured output streaming limitation (may be resolved in newer CLI versions)

---
*Research completed: 2026-03-11*
*Ready for roadmap: yes*
