"""
Command discovery for project-defined slash commands.

Scans a project's `.claude/commands/` directory for `.md` files
and returns CommandInfo objects with name, description, and file path.
"""
import logging
import re
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

CLAUDE_COMMANDS_DIR = ".claude/commands"


@dataclass(frozen=True)
class CommandInfo:
    """Metadata for a discovered project command."""

    name: str
    description: str
    file_path: str


def discover_project_commands(project_path: str) -> dict[str, CommandInfo]:
    """Discover project commands from .claude/commands/*.md files.

    Args:
        project_path: Root directory of the project.

    Returns:
        Dict mapping command name to CommandInfo. Empty if no commands directory.
    """
    cmds_dir = Path(project_path) / CLAUDE_COMMANDS_DIR
    if not cmds_dir.is_dir():
        return {}

    commands: dict[str, CommandInfo] = {}
    for md_path in sorted(cmds_dir.glob("*.md")):
        try:
            info = _parse_command_md(md_path)
            if info is not None:
                commands[info.name] = info
        except Exception:
            log.warning("Skipping broken command file: %s", md_path, exc_info=True)

    return commands


def _parse_command_md(md_path: Path) -> CommandInfo | None:
    """Parse a single .md command file into a CommandInfo.

    Returns None (with warning) for empty files.
    """
    content = md_path.read_text(encoding="utf-8", errors="replace")
    if not content.strip():
        log.warning("Skipping empty command file: %s", md_path)
        return None

    name = _sanitize_name(md_path.stem)
    description = content[:200]

    return CommandInfo(
        name=name,
        description=description,
        file_path=str(md_path.resolve()),
    )


def _sanitize_name(stem: str) -> str:
    """Convert a filename stem to a valid command name.

    'My Command File' -> 'my-command-file'
    """
    result = stem.lower().replace(" ", "-")
    result = re.sub(r"[^a-z0-9-]", "", result)
    return result.strip("-")
