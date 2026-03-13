"""
Workspace context assembler.

Scans the project directory, detects the tech stack from indicator files,
assembles a formatted context block for injection into Claude system prompts.

Limits:
- File listing capped at MAX_FILES = 200
- Excluded: .git, node_modules, __pycache__, .venv, dist, build
- CLAUDE.md capped at MAX_CLAUDE_MD_CHARS = 2000
- Planning docs capped at MAX_PLANNING_DOC_CHARS = 500 each
- Total assembled context budgeted to MAX_CONTEXT_CHARS = 6000
"""
import asyncio
import itertools
import logging
from pathlib import Path
from typing import Any

import asyncpg

log = logging.getLogger(__name__)

MAX_FILES = 200
MAX_CONTEXT_CHARS = 6000
MAX_CLAUDE_MD_CHARS = 2000
MAX_PLANNING_DOC_CHARS = 500
GIT_LOG_COUNT = 10
RECENT_TASKS_LIMIT = 5
PLANNING_FILES = ["PROJECT.md", "STATE.md", "ROADMAP.md", "REQUIREMENTS.md"]
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


# ---------------------------------------------------------------------------
# Context assembly helpers (Phase 14)
# ---------------------------------------------------------------------------

def read_file_truncated(project_path: str, rel_path: str, max_chars: int) -> str:
    """Read a file relative to project_path, truncating at max_chars.

    Returns empty string if file does not exist.
    Uses errors='replace' for encoding safety.
    """
    target = Path(project_path) / rel_path
    if not target.is_file():
        return ""
    content = target.read_text(encoding="utf-8", errors="replace")
    if len(content) > max_chars:
        return content[:max_chars] + "\n...[truncated]"
    return content


async def get_recent_git_log(project_path: str, count: int = GIT_LOG_COUNT) -> str:
    """Return recent git log as a string.

    Returns empty string when .git directory is missing or on any error/timeout.
    Uses a 5-second timeout to prevent blocking.
    """
    git_dir = Path(project_path) / ".git"
    if not git_dir.exists():
        return ""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "log", "--oneline", "--no-pager", f"-{count}",
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        return stdout.decode("utf-8", errors="replace").strip()
    except (asyncio.TimeoutError, Exception) as exc:
        log.debug("get_recent_git_log failed for %s: %s", project_path, exc)
        return ""


async def get_recent_tasks(
    pool: asyncpg.Pool, project_path: str, limit: int = RECENT_TASKS_LIMIT
) -> list[dict[str, Any]]:
    """Fetch recent tasks for a project path from the database.

    Returns list of dicts with id, prompt (truncated to 200 chars), status, created_at.
    Returns empty list when no tasks match.
    """
    rows = await pool.fetch(
        "SELECT id, prompt, status, created_at "
        "FROM tasks WHERE project_path = $1 "
        "ORDER BY created_at DESC LIMIT $2",
        project_path, limit,
    )
    return [
        {
            "id": row["id"],
            "prompt": row["prompt"][:200] if row["prompt"] else "",
            "status": row["status"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]


async def assemble_full_context(
    project_path: str, pool: asyncpg.Pool
) -> dict[str, Any]:
    """Assemble full project context from 5 sources.

    Returns dict with keys:
    - workspace: formatted workspace context string
    - claude_md: CLAUDE.md content (max 2000 chars)
    - planning_docs: dict of planning doc name -> content (max 500 chars each)
    - git_log: recent git log string
    - recent_tasks: list of recent task dicts
    """
    # 1. Workspace context (existing function)
    workspace = assemble_workspace_context(project_path)

    # 2. CLAUDE.md
    claude_md = read_file_truncated(project_path, "CLAUDE.md", MAX_CLAUDE_MD_CHARS)

    # 3. Planning docs
    planning_docs: dict[str, str] = {}
    planning_dir = Path(project_path) / ".planning"
    if planning_dir.is_dir():
        for doc_name in PLANNING_FILES:
            content = read_file_truncated(
                str(planning_dir), doc_name, MAX_PLANNING_DOC_CHARS
            )
            if content:
                planning_docs[doc_name] = content

    # 4. Git log
    git_log = await get_recent_git_log(project_path)

    # 5. Recent tasks
    recent_tasks = await get_recent_tasks(pool, project_path)

    return {
        "workspace": workspace,
        "claude_md": claude_md,
        "planning_docs": planning_docs,
        "git_log": git_log,
        "recent_tasks": recent_tasks,
    }
