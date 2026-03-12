"""
Workspace context assembler.

Scans the project directory, detects the tech stack from indicator files,
assembles a formatted context block for injection into Claude system prompts.

Limits:
- File listing capped at MAX_FILES = 200
- Excluded: .git, node_modules, __pycache__, .venv, dist, build
"""
import itertools
from pathlib import Path

MAX_FILES = 200
EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}

STACK_INDICATORS: dict[str, list[str]] = {
    "Python": ["requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"],
    "Node.js": ["package.json"],
    "Rust": ["Cargo.toml"],
    "Go": ["go.mod"],
    "Java": ["pom.xml", "build.gradle"],
    "Ruby": ["Gemfile"],
    "Docker": ["Dockerfile", "docker-compose.yml"],
}


def assemble_workspace_context(project_path: str) -> str:
    """
    Return a formatted workspace context string for system prompt injection.

    Example output:
        === WORKSPACE CONTEXT ===
        Project path: /home/user/myproject
        Detected stack: Python, Docker
        Files (12 shown):
          - src/main.py
          - Dockerfile
        =========================
    """
    root = Path(project_path)

    stacks = [
        name
        for name, indicators in STACK_INDICATORS.items()
        if any((root / f).exists() for f in indicators)
    ]

    def _iter_files():
        for p in root.rglob("*"):
            if any(excl in p.parts for excl in EXCLUDE_DIRS):
                continue
            if p.is_file():
                yield str(p.relative_to(root))

    files = list(itertools.islice(_iter_files(), MAX_FILES))
    stack_str = ", ".join(stacks) if stacks else "unknown"

    lines = [
        "=== WORKSPACE CONTEXT ===",
        f"Project path: {project_path}",
        f"Detected stack: {stack_str}",
        f"Files ({len(files)} shown):",
    ]
    lines.extend(f"  - {f}" for f in files)
    lines.append("=========================")

    return "\n".join(lines) + "\n"
