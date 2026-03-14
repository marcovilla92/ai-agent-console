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
    description: str = ""
    output_sections: list[str] = field(default_factory=list)
    next_agent: str | None = None
    allowed_transitions: tuple[str, ...] = ()
    # v2.4: Extended fields for project-defined agents
    system_prompt_inline: str | None = None
    source: str = "default"
    file_path: str | None = None


AGENT_REGISTRY: dict[str, AgentConfig] = {
    "plan": AgentConfig(
        name="plan",
        system_prompt_file=str(PROMPTS_DIR / "plan_system.txt"),
        description="Creates a structured development plan from the task prompt",
        output_sections=[
            "GOAL", "ASSUMPTIONS", "CONSTRAINTS", "TASKS",
            "ARCHITECTURE", "FILES TO CREATE", "HANDOFF",
        ],
        next_agent="execute",
        allowed_transitions=("execute",),
    ),
    "execute": AgentConfig(
        name="execute",
        system_prompt_file=str(PROMPTS_DIR / "execute_system.txt"),
        description="Implements the plan by writing complete, working code",
        output_sections=[
            "TARGET", "PROJECT STRUCTURE", "FILES", "CODE",
            "COMMANDS", "SETUP NOTES", "HANDOFF",
        ],
        next_agent="test",
        allowed_transitions=("test", "review"),
    ),
    "test": AgentConfig(
        name="test",
        system_prompt_file=str(PROMPTS_DIR / "test_system.txt"),
        description="Reviews code quality via static analysis (no subprocess execution)",
        output_sections=[
            "SCOPE", "FINDINGS", "SEVERITY", "SUGGESTIONS", "VERDICT",
        ],
        next_agent="review",
        allowed_transitions=("review", "execute"),
    ),
    "review": AgentConfig(
        name="review",
        system_prompt_file=str(PROMPTS_DIR / "review_system.txt"),
        description="Reviews the execution output for quality and decides next step",
        output_sections=[
            "SUMMARY", "ISSUES", "RISKS", "IMPROVEMENTS", "DECISION",
        ],
        next_agent=None,
        allowed_transitions=("plan", "execute", "approved"),
    ),
}


# Sections the orchestrator should consider when making routing decisions
# after each agent type. Unlisted sections are excluded from the routing prompt.
ROUTING_SECTIONS: dict[str, list[str]] = {
    "plan": ["GOAL", "ASSUMPTIONS", "CONSTRAINTS", "TASKS", "HANDOFF"],
    "execute": ["TARGET", "SETUP NOTES", "HANDOFF"],
    "test": ["FINDINGS", "SEVERITY", "VERDICT"],
    "review": ["SUMMARY", "ISSUES", "IMPROVEMENTS", "DECISION"],
}


def build_agent_enum() -> list[str]:
    """Build the list of valid routing targets from the registry.

    Returns agent names + "approved" for the orchestrator schema enum.
    """
    return sorted(list(AGENT_REGISTRY.keys()) + ["approved"])


def build_agent_descriptions() -> str:
    """Build a dynamic agent description block for the orchestrator prompt."""
    lines = []
    for name, config in AGENT_REGISTRY.items():
        desc = config.description or f"Agent: {name}"
        lines.append(f"- {name.upper()}: {desc}")
    return "\n".join(lines)


def validate_transition(from_agent: str, to_agent: str) -> str:
    """Validate a routing transition and return the target agent.

    If the transition is not allowed, falls back to the from_agent's
    configured next_agent. If that is also None, returns "approved".
    """
    if to_agent == "approved":
        return "approved"

    config = AGENT_REGISTRY.get(from_agent)
    if not config:
        return to_agent

    if config.allowed_transitions and to_agent not in config.allowed_transitions:
        fallback = config.next_agent or "approved"
        import logging
        logging.getLogger(__name__).warning(
            "Invalid transition %s -> %s, falling back to %s",
            from_agent, to_agent, fallback,
        )
        return fallback

    return to_agent


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
