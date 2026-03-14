"""
Agent discovery and frontmatter parsing for project-defined agents.

Scans a project's `.claude/agents/` directory for `.md` files,
parses YAML frontmatter (if present), and returns AgentConfig objects.
"""
import logging
import re
from pathlib import Path

import frontmatter

from src.agents.config import AgentConfig

log = logging.getLogger(__name__)

CLAUDE_AGENTS_DIR = ".claude/agents"

_BROAD_TRANSITIONS = ("plan", "execute", "test", "review", "approved")


def discover_project_agents(project_path: str) -> dict[str, AgentConfig]:
    """Discover project-defined agents from .claude/agents/*.md files.

    Args:
        project_path: Root directory of the project.

    Returns:
        Dict mapping agent name to AgentConfig. Empty if no agents directory.
    """
    agents_dir = Path(project_path) / CLAUDE_AGENTS_DIR
    if not agents_dir.is_dir():
        return {}

    agents: dict[str, AgentConfig] = {}
    for md_path in sorted(agents_dir.glob("*.md")):
        try:
            config = _parse_agent_md(md_path)
            if config is not None:
                agents[config.name] = config
        except Exception:
            log.warning("Skipping broken agent file: %s", md_path, exc_info=True)

    return agents


def _parse_agent_md(md_path: Path) -> AgentConfig | None:
    """Parse a single .md file into an AgentConfig.

    Returns None (with warning) for empty files.
    """
    content = md_path.read_text(encoding="utf-8", errors="replace")
    if not content.strip():
        log.warning("Skipping empty agent file: %s", md_path)
        return None

    post = frontmatter.loads(content)
    meta: dict = post.metadata or {}

    name = meta.get("name") or _sanitize_name(md_path.stem)
    description = meta.get("description") or f"Project agent: {name}"
    output_sections = meta.get("output_sections") or []
    next_agent = meta.get("next_agent")
    allowed_transitions = tuple(
        meta.get("allowed_transitions", _BROAD_TRANSITIONS)
    )

    return AgentConfig(
        name=name,
        system_prompt_file="",
        system_prompt_inline=post.content,
        description=description,
        output_sections=output_sections,
        next_agent=next_agent,
        allowed_transitions=allowed_transitions,
        source="project",
        file_path=str(md_path.resolve()),
    )


def _sanitize_name(stem: str) -> str:
    """Convert a filename stem to a valid agent name.

    'My Agent File' -> 'my-agent-file'
    """
    result = stem.lower().replace(" ", "-")
    result = re.sub(r"[^a-z0-9-]", "", result)
    return result.strip("-")
