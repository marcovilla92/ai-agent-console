"""
Handoff builder.

Formats the output of one agent into a visible, structured handoff
block that the next agent receives as context.
"""
from datetime import datetime, timezone

from src.agents.base import AgentResult


def build_handoff(from_result: AgentResult) -> str:
    """
    Format an AgentResult into a handoff context string.

    The handoff is human-readable and inspectable -- not hidden internal state.
    """
    lines = [
        f"=== HANDOFF FROM {from_result.agent_name.upper()} ===",
        f"Timestamp: {datetime.now(timezone.utc).isoformat()}",
        "",
    ]

    if from_result.handoff:
        lines.append("Handoff notes:")
        lines.append(from_result.handoff)
        lines.append("")

    # Include key sections (skip HANDOFF itself to avoid duplication)
    for section_name, content in from_result.sections.items():
        if section_name == "HANDOFF":
            continue
        lines.append(f"--- {section_name} ---")
        lines.append(content)
        lines.append("")

    lines.append(f"=== END HANDOFF FROM {from_result.agent_name.upper()} ===")
    return "\n".join(lines)


def build_reroute_prompt(
    review_sections: dict[str, str], original_prompt: str
) -> str:
    """Build a targeted prompt for re-route cycles.

    Instead of dumping all handoffs, extract specific ISSUES and
    IMPROVEMENTS from the review agent's output so execute gets
    focused feedback.
    """
    lines = [
        "=== RE-ROUTE: FOCUSED FEEDBACK FROM REVIEW ===",
        "",
        "Original task:",
        original_prompt,
        "",
    ]

    issues = review_sections.get("ISSUES", "").strip()
    if issues and issues.lower() != "no issues found.":
        lines.append("ISSUES TO FIX:")
        lines.append(issues)
        lines.append("")

    improvements = review_sections.get("IMPROVEMENTS", "").strip()
    if improvements:
        lines.append("IMPROVEMENTS TO MAKE:")
        lines.append(improvements)
        lines.append("")

    decision = review_sections.get("DECISION", "").strip()
    if decision:
        lines.append("REVIEW DECISION:")
        lines.append(decision)
        lines.append("")

    lines.append("=== END RE-ROUTE FEEDBACK ===")
    return "\n".join(lines)
