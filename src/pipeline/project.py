"""
Project creation.

Creates a dedicated workspace folder for a new project.
"""
import re
from pathlib import Path


def sanitize_project_name(name: str) -> str:
    """Convert a project name to a safe directory name (lowercase, hyphens)."""
    sanitized = re.sub(r"[^a-zA-Z0-9\s-]", "", name)
    sanitized = re.sub(r"\s+", "-", sanitized.strip())
    sanitized = sanitized.lower()
    if not sanitized:
        raise ValueError(f"Project name produces empty directory name: {name!r}")
    return sanitized


def create_project(name: str, workspace_root: str) -> str:
    """
    Create a project folder under workspace_root.

    Returns the absolute path to the created project directory.
    Raises FileExistsError if the project folder already exists.
    """
    dir_name = sanitize_project_name(name)
    project_path = Path(workspace_root) / dir_name

    if project_path.exists():
        raise FileExistsError(f"Project folder already exists: {project_path}")

    project_path.mkdir(parents=True)
    (project_path / "src").mkdir()

    return str(project_path)
