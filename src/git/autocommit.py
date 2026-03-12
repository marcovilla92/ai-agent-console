"""
Git auto-commit module.

After an approved execution cycle, generated files are automatically
committed to git with a descriptive message. Silently skips if the
project path is not inside a git repository.
"""
import asyncio
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_git_lock = asyncio.Lock()


async def auto_commit(project_path: str, session_name: str) -> bool:
    """
    Stage all changes and commit in the given project directory.

    Returns True on successful commit, False otherwise.
    Silently returns False if the path is not a git repository.
    Uses an asyncio lock to prevent concurrent git operations.
    """
    git_dir = Path(project_path) / ".git"
    if not git_dir.exists():
        log.debug("No .git directory at %s, skipping auto-commit", project_path)
        return False

    async with _git_lock:
        try:
            # Stage only tracked files and new files in src/tests dirs
            # (avoid staging unrelated files like logs, .env, etc.)
            for pattern in ["src/", "tests/"]:
                proc = await asyncio.create_subprocess_exec(
                    "git", "add", pattern,
                    cwd=project_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
            # Also stage tracked files that were modified
            proc = await asyncio.create_subprocess_exec(
                "git", "add", "-u",
                cwd=project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Check if there are staged changes (exit 0 = nothing staged)
            proc = await asyncio.create_subprocess_exec(
                "git", "diff", "--cached", "--quiet",
                cwd=project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            if proc.returncode == 0:
                log.debug("No staged changes, skipping commit")
                return False

            # Commit
            message = f"auto: {session_name} - execution cycle approved"
            proc = await asyncio.create_subprocess_exec(
                "git", "commit", "-m", message,
                cwd=project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            if proc.returncode != 0:
                log.warning("git commit failed with code %d", proc.returncode)
                return False

            log.info("Auto-committed: %s", message)
            return True

        except Exception:
            log.exception("auto_commit failed for %s", project_path)
            return False
