"""
Agent configuration registry.

Each agent is defined declaratively with a name, system prompt path,
expected output sections, and optional next agent in the pipeline.
Adding a new agent requires only a new entry here -- no code changes.
"""
from dataclasses import dataclass, field
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"


@dataclass(frozen=True)
class AgentConfig:
    name: str
    system_prompt_file: str
    output_sections: list[str] = field(default_factory=list)
    next_agent: str | None = None


AGENT_REGISTRY: dict[str, AgentConfig] = {
    "plan": AgentConfig(
        name="plan",
        system_prompt_file=str(PROMPTS_DIR / "plan_system.txt"),
        output_sections=[
            "GOAL", "ASSUMPTIONS", "CONSTRAINTS", "TASKS",
            "ARCHITECTURE", "FILES TO CREATE", "HANDOFF",
        ],
        next_agent="execute",
    ),
    "execute": AgentConfig(
        name="execute",
        system_prompt_file=str(PROMPTS_DIR / "execute_system.txt"),
        output_sections=[
            "TARGET", "PROJECT STRUCTURE", "FILES", "CODE",
            "COMMANDS", "SETUP NOTES", "HANDOFF",
        ],
        next_agent="review",
    ),
    "review": AgentConfig(
        name="review",
        system_prompt_file=str(PROMPTS_DIR / "review_system.txt"),
        output_sections=[
            "SUMMARY", "ISSUES", "RISKS", "IMPROVEMENTS", "DECISION",
        ],
        next_agent=None,
    ),
}


def get_agent_config(name: str) -> AgentConfig:
    """Get agent config by name. Raises KeyError if not found."""
    if name not in AGENT_REGISTRY:
        raise KeyError(f"Unknown agent: {name!r}. Available: {list(AGENT_REGISTRY)}")
    return AGENT_REGISTRY[name]


def resolve_pipeline_order(start_agent: str = "plan") -> list[str]:
    """Walk the next_agent chain from start_agent, returning ordered agent names.

    Raises KeyError if start_agent is not in AGENT_REGISTRY.
    Raises ValueError if a circular next_agent chain is detected.
    """
    order: list[str] = []
    seen: set[str] = set()
    current: str | None = start_agent

    while current is not None:
        if current in seen:
            raise ValueError("Circular next_agent chain detected")
        if current not in AGENT_REGISTRY:
            raise KeyError(f"Unknown agent: {current!r}. Available: {list(AGENT_REGISTRY)}")
        seen.add(current)
        order.append(current)
        current = AGENT_REGISTRY[current].next_agent

    return order
