"""
AI-driven orchestrator replacing the fixed sequential pipeline.

Analyzes agent outputs via Claude CLI and decides the next step.
Supports iterative improvement cycles with safety limits.

v2.0: Decoupled from TUI via TaskContext Protocol. Accepts asyncpg.Pool
instead of aiosqlite.Connection for PostgreSQL persistence.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import asyncpg

from src.db.pg_repository import OrchestratorDecisionRepository, TaskRepository
from src.db.pg_schema import OrchestratorDecisionRecord
from src.agents.config import AgentConfig, ROUTING_SECTIONS, build_agent_descriptions, build_agent_enum, validate_transition
from src.pipeline.file_writer import process_execute_output
from src.pipeline.handoff import build_handoff, build_reroute_prompt
from src.pipeline.protocol import TaskContext
from src.runner.runner import call_orchestrator_claude

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
    written_files: list[str] = field(default_factory=list)
    halted: bool = False
    approved: bool = False


# --- JSON Schema for Claude CLI --json-schema flag ---

def build_orchestrator_schema(registry: dict[str, AgentConfig] | None = None) -> str:
    """Build orchestrator JSON schema dynamically from agent registry.

    Args:
        registry: Agent registry to build enum from. Defaults to DEFAULT_REGISTRY.
    """
    return json.dumps({
        "type": "object",
        "properties": {
            "next_agent": {
                "type": "string",
                "enum": build_agent_enum(registry),
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


# Backward-compatible constant (uses DEFAULT_REGISTRY)
ORCHESTRATOR_SCHEMA = build_orchestrator_schema()

ORCHESTRATOR_PROMPT_FILE = str(
    Path(__file__).parent.parent / "agents" / "prompts" / "orchestrator_system.txt"
)


def build_orchestrator_system_prompt(registry: dict[str, AgentConfig] | None = None) -> str:
    """Build a dynamic orchestrator system prompt that includes project agent descriptions.

    Reads the base prompt from ORCHESTRATOR_PROMPT_FILE, then appends a section
    listing project-specific and command-sourced agents if any exist in the registry.

    Args:
        registry: Agent registry. Defaults to DEFAULT_REGISTRY (no project agents).
    """
    base_text = Path(ORCHESTRATOR_PROMPT_FILE).read_text(encoding="utf-8")

    if registry is None:
        return base_text

    # Filter for project/command agents
    project_agents = {
        name: cfg for name, cfg in registry.items()
        if cfg.source in ("project", "command")
    }

    if not project_agents:
        return base_text

    lines = ["\n\nProject-specific specialist agents:"]
    for name, cfg in project_agents.items():
        desc = cfg.description or f"Agent: {name}"
        lines.append(f"- {name.upper()}: {desc}")

    return base_text + "\n".join(lines)


MAX_HANDOFF_ENTRIES = 3  # One complete cycle: plan + execute + review
MAX_HANDOFF_CHARS = 8000  # Cap on windowed portion (excludes pinned plan)
CONFIDENCE_THRESHOLD = 0.5  # Below this, decisions get extra scrutiny


# --- Handoff windowing ---

def apply_handoff_windowing(state: OrchestratorState) -> None:
    """Apply sliding window to accumulated handoffs.

    Keeps at most MAX_HANDOFF_ENTRIES recent handoffs plus the pinned
    first plan handoff (index 0). Enforces MAX_HANDOFF_CHARS on the
    windowed portion only (pinned plan exempt).
    """
    handoffs = state.accumulated_handoffs

    # Entry windowing: pin first + keep last MAX_HANDOFF_ENTRIES
    if len(handoffs) > MAX_HANDOFF_ENTRIES + 1:
        pinned = handoffs[0]
        recent = handoffs[-MAX_HANDOFF_ENTRIES:]
        handoffs = [pinned] + recent

    # Character cap on windowed portion (index 1+)
    if len(handoffs) > 1:
        pinned = handoffs[0]
        windowed = handoffs[1:]
        total = "\n\n".join(windowed)
        while len(total) > MAX_HANDOFF_CHARS and len(windowed) > 1:
            windowed.pop(0)
            total = "\n\n".join(windowed)
        handoffs = [pinned] + windowed

    state.accumulated_handoffs = handoffs
    log.info(
        "apply_handoff_windowing: total_handoffs=%d total_chars=%d",
        len(state.accumulated_handoffs),
        sum(len(h) for h in state.accumulated_handoffs),
    )


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

    allowed = ROUTING_SECTIONS.get(state.current_agent)
    for section_name, content in latest_sections.items():
        if allowed and section_name not in allowed:
            continue
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

    raw = await call_orchestrator_claude(prompt, ORCHESTRATOR_SCHEMA, ORCHESTRATOR_PROMPT_FILE)

    try:
        response = json.loads(raw)
        # Claude CLI returns structured output in "structured_output" field
        data = response.get("structured_output") or response.get("result")
        if isinstance(data, str):
            data = json.loads(data)
        if not data or not isinstance(data, dict):
            return parse_decision_from_text(raw)

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
    pool: asyncpg.Pool,
    session_id: int,
    decision: OrchestratorDecision,
    iteration_count: int,
) -> int:
    """Persist an orchestrator decision to the database."""
    repo = OrchestratorDecisionRepository(pool)
    record = OrchestratorDecisionRecord(
        session_id=session_id,
        next_agent=decision.next_agent,
        reasoning=decision.reasoning,
        confidence=decision.confidence,
        full_response=decision.full_response,
        iteration_count=iteration_count,
        created_at=datetime.now(timezone.utc),
    )
    return await repo.create(record)


# --- Main orchestration loop ---

async def orchestrate_pipeline(
    ctx: TaskContext,
    prompt: str,
    pool: asyncpg.Pool | None = None,
    session_id: int | None = None,
) -> OrchestratorState:
    """
    AI-driven orchestration loop replacing the fixed sequential pipeline.

    Runs agents via ctx.stream_output, calls Claude CLI for routing
    decisions after each agent, and handles re-routing with iteration limits.

    Args:
        ctx: TaskContext implementation (TUI adapter, web handler, etc.)
        prompt: The user's task prompt.
        pool: asyncpg connection pool for persistence (optional).
        session_id: Task/session ID for DB logging (optional).
    """
    state = OrchestratorState(session_id=session_id, original_prompt=prompt)
    log.info("orchestrate_pipeline: started prompt_len=%d session_id=%s", len(prompt), session_id)

    while not state.halted and not state.approved:
        log.info("orchestrate_pipeline: === LOOP iteration=%d agent=%s ===", state.iteration_count, state.current_agent)

        # 1. Build prompt for current agent (include all accumulated handoffs)
        agent_prompt = prompt
        if state.accumulated_handoffs:
            handoff_context = "\n\n".join(state.accumulated_handoffs)
            agent_prompt = f"{prompt}\n\n{handoff_context}"
            log.info("orchestrate_pipeline: added %d handoffs to prompt, total_len=%d", len(state.accumulated_handoffs), len(agent_prompt))

        # 2. Run current agent (streams via TaskContext)
        log.info("orchestrate_pipeline: streaming agent=%s prompt_len=%d", state.current_agent, len(agent_prompt))
        await ctx.update_status(
            agent=state.current_agent,
            state="streaming",
            step="receiving output",
            next_action="Streaming...",
        )

        sections = await ctx.stream_output(
            state.current_agent, agent_prompt, {},
        )
        log.info("orchestrate_pipeline: agent=%s completed sections=%s", state.current_agent, list(sections.keys()))

        # 2b. If execute just completed, write files to disk
        if state.current_agent == "execute":
            newly_written = process_execute_output(ctx.project_path, sections)
            state.written_files.extend(newly_written)
            log.info("orchestrate_pipeline: file_writer wrote %d files", len(newly_written))

        # 3. Record in history and build handoff for next agent
        state.history.append({
            "agent": state.current_agent,
            "sections_keys": list(sections.keys()),
        })

        # Always accumulate handoff so the next agent has context
        from src.agents.base import AgentResult
        agent_result = AgentResult(
            agent_name=state.current_agent,
            raw_output="",
            sections=sections,
            handoff=sections.get("HANDOFF"),
        )
        state.accumulated_handoffs.append(build_handoff(agent_result))
        apply_handoff_windowing(state)
        log.info("orchestrate_pipeline: built handoff from %s, total_handoffs=%d", state.current_agent, len(state.accumulated_handoffs))

        # 4. If review just ran, increment iteration counter
        if state.current_agent == "review":
            state.iteration_count += 1
            log.info("orchestrate_pipeline: review done, iteration_count=%d", state.iteration_count)

        # 5. Call Claude CLI for routing decision
        log.info("orchestrate_pipeline: requesting routing decision...")
        decision = await get_orchestrator_decision(state, sections)
        # Validate routing transition
        validated = validate_transition(state.current_agent, decision.next_agent)
        if validated != decision.next_agent:
            log.warning("orchestrate_pipeline: transition %s->%s invalid, using %s",
                        state.current_agent, decision.next_agent, validated)
            decision = OrchestratorDecision(
                next_agent=validated,
                reasoning=f"(corrected from {decision.next_agent}) {decision.reasoning}",
                confidence=decision.confidence,
                full_response=decision.full_response,
            )
        state.decisions.append(decision)
        log.info("orchestrate_pipeline: decision next=%s confidence=%.2f reasoning=%s",
                 decision.next_agent, decision.confidence, decision.reasoning)

        # 6. Update status with reasoning
        await ctx.update_status(
            agent="orchestrator",
            state="routing",
            step=decision.reasoning,
            next_action=f"-> {decision.next_agent.upper()}",
        )

        # 6b. Confidence-based gating
        if decision.confidence < CONFIDENCE_THRESHOLD:
            if ctx.mode == "supervised":
                log.warning(
                    "orchestrate_pipeline: low confidence %.2f in supervised mode, requesting confirmation",
                    decision.confidence,
                )
                await ctx.update_status(
                    agent="orchestrator",
                    state="low_confidence",
                    step=f"Low confidence ({decision.confidence:.0%}): {decision.reasoning}",
                    next_action=f"Awaiting confirmation -> {decision.next_agent.upper()}",
                )
                confirmed = await ctx.confirm_reroute(
                    decision.next_agent,
                    f"Low confidence ({decision.confidence:.0%}): {decision.reasoning}",
                )
                if not confirmed:
                    log.info("orchestrate_pipeline: low confidence decision rejected, halting")
                    state.halted = True
                    break
            else:
                log.warning(
                    "orchestrate_pipeline: low confidence %.2f in autonomous mode, proceeding anyway",
                    decision.confidence,
                )
                await ctx.update_status(
                    agent="orchestrator",
                    state="low_confidence_warning",
                    step=f"Warning: low confidence ({decision.confidence:.0%}): {decision.reasoning}",
                    next_action=f"Proceeding -> {decision.next_agent.upper()}",
                )

        # 7. Log decision to DB (skip if no pool)
        if pool is not None and session_id is not None:
            await log_decision(pool, session_id, decision, state.iteration_count)

        # 8. Handle the decision
        if decision.next_agent == "approved":
            log.info("orchestrate_pipeline: APPROVED")
            state.approved = True
        elif decision.next_agent in ("plan", "execute") and state.current_agent == "review":
            log.info("orchestrate_pipeline: re-routing from review to %s", decision.next_agent)
            # Re-routing: check iteration limit
            if state.iteration_count >= state.max_iterations:
                log.info("orchestrate_pipeline: iteration limit reached, asking user")
                user_choice = await ctx.handle_halt(state.iteration_count)
                log.info("orchestrate_pipeline: user chose: %s", user_choice)
                if user_choice == "continue":
                    state.iteration_count = 0  # Reset for 3 more
                elif user_choice == "approve":
                    state.approved = True
                    break
                else:  # stop
                    state.halted = True
                    break

            # Build targeted re-route prompt from review feedback
            reroute_context = build_reroute_prompt(sections, state.original_prompt)
            pinned = state.accumulated_handoffs[0] if state.accumulated_handoffs else ""
            state.accumulated_handoffs = [pinned, reroute_context] if pinned else [reroute_context]
            log.info("orchestrate_pipeline: replaced handoffs with targeted re-route prompt")

            # User confirmation for re-routing
            confirmed = await ctx.confirm_reroute(
                decision.next_agent, decision.reasoning,
            )
            if confirmed:
                state.current_agent = decision.next_agent
                log.info("orchestrate_pipeline: reroute confirmed, now agent=%s", state.current_agent)
            else:
                log.info("orchestrate_pipeline: reroute rejected, halting")
                state.halted = True
        else:
            # Normal forward progression: plan->execute->review
            log.info("orchestrate_pipeline: forward to %s", decision.next_agent)
            state.current_agent = decision.next_agent

    # Auto-commit to git if pipeline was approved
    if state.approved:
        try:
            from src.git.autocommit import auto_commit

            task_name = "unnamed"
            if pool and session_id:
                repo = TaskRepository(pool)
                task = await repo.get(session_id)
                if task:
                    task_name = task.name

            committed = await auto_commit(ctx.project_path, task_name)
            if committed:
                await ctx.update_status(
                    agent="orchestrator",
                    state="committed",
                    step="auto-committed to git",
                    next_action="Pipeline complete",
                )
        except Exception:
            log.exception("auto_commit failed in orchestrator")

    return state
