# Phase 4: Orchestrator Intelligence - Context

**Gathered:** 2026-03-12
**Status:** Ready for planning

<domain>
## Phase Boundary

An AI-driven orchestrator replaces the current rule-based sequential pipeline (PLAN->EXECUTE->REVIEW) with intelligent routing. After each agent completes, the orchestrator analyzes the output via Claude CLI and decides what runs next. Supports iterative improvement cycles (REVIEW->PLAN->EXECUTE->REVIEW) with safety limits. User confirms re-routing decisions.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
User delegated all implementation decisions to Claude. The following are guidelines derived from the codebase and requirements:

### Routing logic
- Replace `pipeline/runner.py`'s fixed sequential loop with an orchestrator that calls Claude CLI after each agent to analyze output and decide next step
- The orchestrator prompt receives: agent output sections, handoff context, iteration count, workflow history
- Claude CLI returns a structured decision: next_agent, reasoning, confidence
- For the first pass (PLAN->EXECUTE->REVIEW with APPROVED), the orchestrator should still work efficiently — AI judgment adds value primarily on re-routing decisions
- Parse the orchestrator's response as JSON for reliability; fall back to text extraction if JSON fails

### Re-routing flow
- When REVIEW says BACK TO PLAN or BACK TO EXECUTE: present the decision + reasoning to user in the TUI
- User confirms with Enter or cancels with Escape before re-routing proceeds
- The re-routed agent receives: original prompt + all prior handoffs + REVIEW feedback (issues, improvements)
- Each iteration builds on prior context, not starts fresh

### Cycle limits & halting
- An "iteration" = one full cycle that includes a REVIEW agent run
- After 3 iterations without APPROVED: halt and ask user "Continue iterating, approve manually, or stop?"
- User can choose to continue (resets counter for 3 more), approve (accept current output), or stop (end workflow)
- Track iteration count in PipelineResult or a new OrchestratorState dataclass

### Decision visibility
- Orchestrator reasoning displayed in status bar: "REVIEW found 2 issues -> re-routing to PLAN"
- Keep it concise — one line in status bar with agent name, state, and reasoning summary
- Full orchestrator response (with detailed reasoning) logged to a dedicated section in the session DB for inspection
- No separate panel — status bar + DB logging is sufficient

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. User wants speed and keyboard-first UX (from PROJECT.md).

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `pipeline/runner.py`: PipelineResult dataclass, session creation logic — refactor into orchestrator loop
- `pipeline/handoff.py`: build_handoff() — reuse for passing context between iterations
- `agents/config.py`: AGENT_REGISTRY, get_agent_config(), resolve_pipeline_order() — use registry for agent lookup
- `agents/factory.py`: create_agent() — reuse for agent instantiation
- `tui/streaming.py`: start_agent_worker() — reuse for streaming each agent's output to panels
- `tui/status_bar.py`: set_status(agent, state, step, next_action) — use for orchestrator visibility
- `runner/runner.py`: stream_claude() / collect_claude() — use for orchestrator's own Claude CLI call

### Established Patterns
- Frozen dataclasses for config (AgentConfig)
- Repository pattern for DB access
- Async generators for streaming
- Visible structured handoffs between agents
- Action handlers in separate module (actions.py)

### Integration Points
- `tui/actions.py`: send_prompt() and run_agent() currently call start_agent_worker directly — needs to route through orchestrator instead
- `tui/status_bar.py`: orchestrator updates status between agent runs
- `db/schema.py`: may need OrchestratorDecision table for logging decisions

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-orchestrator-intelligence*
*Context gathered: 2026-03-12*
