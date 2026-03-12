"""
AI-driven orchestrator replacing the fixed sequential pipeline.

Analyzes agent outputs via Claude CLI and decides the next step.
Supports iterative improvement cycles with safety limits.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import aiosqlite

from src.db.repository import OrchestratorDecisionRepository
from src.db.schema import OrchestratorDecisionRecord
from src.pipeline.handoff import build_handoff
from src.runner.runner import call_orchestrator_claude

if TYPE_CHECKING:
    from src.tui.app import AgentConsoleApp

log = logging.getLogger(__name__)


# --- Dataclasses ---

@dataclass
class OrchestratorDecision:
    """Single routing decision from Claude CLI."""
    next_agent: str       # "plan", "execute", "review", "approved"
    reasoning: str        # One-line summary
    confidence: float     # 0.0 - 1.0
    full_response: str    # Raw response for DB logging
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class OrchestratorState:
    """Mutable state for the orchestration loop."""
    session_id: int
    original_prompt: str
    iteration_count: int = 0
    max_iterations: int = 3
    current_agent: str = "plan"
    history: list[dict] = field(default_factory=list)
    decisions: list[OrchestratorDecision] = field(default_factory=list)
    accumulated_handoffs: list[str] = field(default_factory=list)
    halted: bool = False
    approved: bool = False


# --- JSON Schema for Claude CLI --json-schema flag ---

ORCHESTRATOR_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "next_agent": {
            "type": "string",
            "enum": ["plan", "execute", "review", "approved"],
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


# --- Prompt building ---

def build_orchestrator_prompt(
    state: OrchestratorState,
    latest_sections: dict[str, str],
) -> str:
    """Build the prompt sent to Claude CLI for routing decision."""
    lines = [
        f"Current agent just completed: {state.current_agent.upper()}",
        f"Iteration count: {state.iteration_count}",
    ]

    if state.history:
        chain = " -> ".join(h["agent"].upper() for h in state.history)
        lines.append(f"Workflow history: {chain}")

    lines.append("")
    lines.append("Latest agent output sections:")

    for section_name, content in latest_sections.items():
        truncated = content[:500] + "..." if len(content) > 500 else content
        lines.append(f"--- {section_name} ---")
        lines.append(truncated)
        lines.append("")

    lines.append("Based on this output, what agent should run next?")
    return "\n".join(lines)


# --- Decision parsing ---

def parse_decision_from_text(raw: str) -> OrchestratorDecision:
    """
    Fallback parser: extract routing decision from unstructured text.

    Looks for known keywords. Returns confidence=0.3 to indicate fallback.
    """
    upper = raw.upper()

    if "APPROVED" in upper:
        next_agent = "approved"
        reasoning = "Text fallback: found APPROVED in response"
    elif "BACK TO PLAN" in upper:
        next_agent = "plan"
        reasoning = "Text fallback: found BACK TO PLAN in response"
    elif "BACK TO EXECUTE" in upper:
        next_agent = "execute"
        reasoning = "Text fallback: found BACK TO EXECUTE in response"
    else:
        next_agent = "review"
        reasoning = "Text fallback: no clear decision found, defaulting to review"

    return OrchestratorDecision(
        next_agent=next_agent,
        reasoning=reasoning,
        confidence=0.3,
        full_response=raw,
    )


async def get_orchestrator_decision(
    state: OrchestratorState,
    latest_sections: dict[str, str],
) -> OrchestratorDecision:
    """
    Call Claude CLI to analyze output and decide next agent.

    Parses JSON response from Claude CLI. Falls back to text extraction
    if JSON parsing fails.
    """
    prompt = build_orchestrator_prompt(state, latest_sections)

    raw = await call_orchestrator_claude(prompt, ORCHESTRATOR_SCHEMA)

    try:
        response = json.loads(raw)
        # Claude CLI wraps structured output in {"result": "..."}
        result_str = response.get("result", raw)
        if isinstance(result_str, str):
            data = json.loads(result_str)
        else:
            data = result_str

        return OrchestratorDecision(
            next_agent=data["next_agent"],
            reasoning=data["reasoning"],
            confidence=data.get("confidence", 0.5),
            full_response=raw,
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        log.warning("JSON parse failed for orchestrator response, using text fallback")
        return parse_decision_from_text(raw)


# --- DB logging ---

async def log_decision(
    db: aiosqlite.Connection,
    session_id: int,
    decision: OrchestratorDecision,
    iteration_count: int,
) -> int:
    """Persist an orchestrator decision to the database."""
    repo = OrchestratorDecisionRepository(db)
    record = OrchestratorDecisionRecord(
        session_id=session_id,
        next_agent=decision.next_agent,
        reasoning=decision.reasoning,
        confidence=decision.confidence,
        full_response=decision.full_response,
        iteration_count=iteration_count,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    return await repo.create(record)


# --- Stub modal functions (Plan 02 wires real Textual modals) ---

async def _stub_reroute_confirmation(app: AgentConsoleApp, decision: OrchestratorDecision) -> bool:
    """Stub: always confirms re-routing. Plan 02 replaces with real modal."""
    return True


async def _stub_halt_dialog(app: AgentConsoleApp, state: OrchestratorState) -> str:
    """Stub: always returns 'continue'. Plan 02 replaces with real modal."""
    return "continue"


# --- Main orchestration loop ---

async def orchestrate_pipeline(
    app: AgentConsoleApp,
    prompt: str,
    db: aiosqlite.Connection,
    session_id: int,
) -> OrchestratorState:
    """
    AI-driven orchestration loop replacing the fixed sequential pipeline.

    Runs agents via stream_agent_to_panel, calls Claude CLI for routing
    decisions after each agent, and handles re-routing with iteration limits.
    """
    from src.tui.actions import AGENT_PANEL_MAP
    from src.tui.streaming import stream_agent_to_panel

    state = OrchestratorState(session_id=session_id, original_prompt=prompt)

    while not state.halted and not state.approved:
        # 1. Build prompt for current agent (include accumulated handoffs)
        agent_prompt = prompt
        if state.accumulated_handoffs:
            handoff_context = "\n\n".join(state.accumulated_handoffs)
            agent_prompt = f"{prompt}\n\n{handoff_context}"

        # 2. Run current agent (streams to TUI panel)
        panel_id = AGENT_PANEL_MAP[state.current_agent]
        panel = app.get_panel(panel_id)

        app.status_bar.set_status(
            agent=state.current_agent,
            state="streaming",
            step="receiving output",
            next_action="Streaming...",
        )

        sections = await stream_agent_to_panel(
            app, state.current_agent, agent_prompt, panel, db, session_id,
        )

        # 3. Record in history
        state.history.append({
            "agent": state.current_agent,
            "sections_keys": list(sections.keys()),
        })

        # 4. If review just ran, increment iteration counter
        if state.current_agent == "review":
            state.iteration_count += 1

        # 5. Call Claude CLI for routing decision
        decision = await get_orchestrator_decision(state, sections)
        state.decisions.append(decision)

        # 6. Update status bar with reasoning
        app.status_bar.set_status(
            agent="orchestrator",
            state="routing",
            step=decision.reasoning,
            next_action=f"-> {decision.next_agent.upper()}",
        )

        # 7. Log decision to DB
        await log_decision(db, session_id, decision, state.iteration_count)

        # 8. Handle the decision
        if decision.next_agent == "approved":
            state.approved = True
        elif decision.next_agent in ("plan", "execute") and state.current_agent == "review":
            # Re-routing: check iteration limit
            if state.iteration_count >= state.max_iterations:
                user_choice = await _stub_halt_dialog(app, state)
                if user_choice == "continue":
                    state.iteration_count = 0  # Reset for 3 more
                elif user_choice == "approve":
                    state.approved = True
                    break
                else:  # stop
                    state.halted = True
                    break

            # User confirmation for re-routing (stub always confirms)
            confirmed = await _stub_reroute_confirmation(app, decision)
            if confirmed:
                state.current_agent = decision.next_agent
                # Accumulate handoff context for the next iteration
                from src.agents.base import AgentResult
                agent_result = AgentResult(
                    agent_name=state.history[-1]["agent"],
                    raw_output="",
                    sections=sections,
                )
                state.accumulated_handoffs.append(build_handoff(agent_result))
            else:
                state.halted = True
        else:
            # Normal forward progression: plan->execute->review
            state.current_agent = decision.next_agent

    return state
