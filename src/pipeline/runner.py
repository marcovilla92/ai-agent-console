"""
Sequential pipeline runner.

Runs PLAN → EXECUTE → REVIEW in sequence, passing handoff context
between each step.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

import aiosqlite

from src.agents.base import AgentResult
from src.agents.config import resolve_pipeline_order
from src.agents.factory import create_agent
from src.db.repository import SessionRepository
from src.db.schema import Session
from src.pipeline.handoff import build_handoff


@dataclass
class PipelineResult:
    session_id: int
    steps: list[AgentResult] = field(default_factory=list)
    final_decision: str | None = None


async def run_pipeline(
    prompt: str,
    project_path: str,
    db: aiosqlite.Connection,
    session_name: str = "default",
) -> PipelineResult:
    """
    Run the full agent pipeline: PLAN → EXECUTE → REVIEW.

    Each agent receives the handoff from the previous agent as additional context.
    Returns a PipelineResult with all steps and the REVIEW decision.
    """
    # Create session
    session_repo = SessionRepository(db)
    session_id = await session_repo.create(Session(
        name=session_name,
        project_path=project_path,
        created_at=datetime.now(timezone.utc).isoformat(),
    ))

    result = PipelineResult(session_id=session_id)
    current_prompt = prompt
    pipeline_steps = resolve_pipeline_order()

    for step_name in pipeline_steps:
        agent = create_agent(step_name, db, project_path)
        step_result = await agent.run(current_prompt, session_id)
        result.steps.append(step_result)

        # Build handoff for next agent
        if step_name != pipeline_steps[-1]:
            handoff_context = build_handoff(step_result)
            current_prompt = f"{prompt}\n\n{handoff_context}"

    # Extract final decision from review
    review_result = result.steps[-1]
    decision_text = review_result.sections.get("DECISION", "")
    if "APPROVED" in decision_text.upper():
        result.final_decision = "APPROVED"
    elif "BACK TO PLAN" in decision_text.upper():
        result.final_decision = "BACK TO PLAN"
    elif "BACK TO EXECUTE" in decision_text.upper():
        result.final_decision = "BACK TO EXECUTE"
    else:
        result.final_decision = decision_text.strip() or None

    return result
