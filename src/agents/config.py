"""
Agent configuration registry.

Each agent is defined declaratively with a name, system prompt path,
expected output sections, and optional next agent in the pipeline.
Adding a new agent requires only a new entry here -- no code changes.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

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


# Canonical registry -- never mutate this dict at runtime.
DEFAULT_REGISTRY: dict[str, AgentConfig] = {
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

# Backward-compatible alias
AGENT_REGISTRY = DEFAULT_REGISTRY

# Core agents that cannot be overridden by project agents
PROTECTED_AGENTS: frozenset[str] = frozenset({"plan", "execute", "test", "review"})


# Sections the orchestrator should consider when making routing decisions
# after each agent type. Unlisted sections are excluded from the routing prompt.
ROUTING_SECTIONS: dict[str, list[str]] = {
    "plan": ["GOAL", "ASSUMPTIONS", "CONSTRAINTS", "TASKS", "HANDOFF"],
    "execute": ["TARGET", "SETUP NOTES", "HANDOFF"],
    "test": ["FINDINGS", "SEVERITY", "VERDICT"],
    "review": ["SUMMARY", "ISSUES", "IMPROVEMENTS", "DECISION"],
}


def merge_registries(
    default: dict[str, AgentConfig],
    project: dict[str, AgentConfig],
) -> dict[str, AgentConfig]:
    """Merge project agents into a copy of the default registry.

    Core agents (in PROTECTED_AGENTS) cannot be overridden -- a warning
    is logged and the project agent is skipped.

    Returns a new dict; neither input is mutated.
    """
    merged = dict(default)
    for name, config in project.items():
        if name in PROTECTED_AGENTS:
            log.warning(
                "Project agent %r conflicts with core agent -- skipped",
                name,
            )
            continue
        merged[name] = config
    return merged


def get_project_registry(project_path: str | None = None) -> dict[str, AgentConfig]:
    """Build an isolated registry for a specific project.

    If project_path is None/empty or has no agents directory, returns
    a plain copy of DEFAULT_REGISTRY.
    """
    if not project_path:
        return dict(DEFAULT_REGISTRY)

    # Lazy import to avoid circular dependency (loader imports AgentConfig)
    from src.agents.loader import discover_project_agents

    project_agents = discover_project_agents(project_path)
    if not project_agents:
        return dict(DEFAULT_REGISTRY)

    return merge_registries(DEFAULT_REGISTRY, project_agents)


def build_agent_enum(registry: dict[str, AgentConfig] | None = None) -> list[str]:
    """Build the list of valid routing targets from the registry.

    Returns agent names + "approved" for the orchestrator schema enum.
    """
    reg = registry if registry is not None else AGENT_REGISTRY
    return sorted(list(reg.keys()) + ["approved"])


def build_agent_descriptions(registry: dict[str, AgentConfig] | None = None) -> str:
    """Build a dynamic agent description block for the orchestrator prompt."""
    reg = registry if registry is not None else AGENT_REGISTRY
    lines = []
    for name, config in reg.items():
        desc = config.description or f"Agent: {name}"
        lines.append(f"- {name.upper()}: {desc}")
    return "\n".join(lines)


def validate_transition(
    from_agent: str,
    to_agent: str,
    registry: dict[str, AgentConfig] | None = None,
) -> str:
    """Validate a routing transition and return the target agent.

    If the transition is not allowed, falls back to the from_agent's
    configured next_agent. If that is also None, returns "approved".
    """
    reg = registry if registry is not None else AGENT_REGISTRY

    if to_agent == "approved":
        return "approved"

    config = reg.get(from_agent)
    if not config:
        return to_agent

    if config.allowed_transitions and to_agent not in config.allowed_transitions:
        fallback = config.next_agent or "approved"
        log.warning(
            "Invalid transition %s -> %s, falling back to %s",
            from_agent, to_agent, fallback,
        )
        return fallback

    return to_agent


def get_agent_config(
    name: str,
    registry: dict[str, AgentConfig] | None = None,
) -> AgentConfig:
    """Get agent config by name. Raises KeyError if not found."""
    reg = registry if registry is not None else AGENT_REGISTRY
    if name not in reg:
        raise KeyError(f"Unknown agent: {name!r}. Available: {list(reg)}")
    return reg[name]


def resolve_pipeline_order(
    start_agent: str = "plan",
    registry: dict[str, AgentConfig] | None = None,
) -> list[str]:
    """Walk the next_agent chain from start_agent, returning ordered agent names.

    Raises KeyError if start_agent is not in the registry.
    Raises ValueError if a circular next_agent chain is detected.
    """
    reg = registry if registry is not None else AGENT_REGISTRY
    order: list[str] = []
    seen: set[str] = set()
    current: str | None = start_agent

    while current is not None:
        if current in seen:
            raise ValueError("Circular next_agent chain detected")
        if current not in reg:
            raise KeyError(f"Unknown agent: {current!r}. Available: {list(reg)}")
        seen.add(current)
        order.append(current)
        current = reg[current].next_agent

    return order
