"""Tests for git auto-commit module."""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.git.autocommit import auto_commit


class _FakeProc:
    """Minimal fake for asyncio subprocess."""

    def __init__(self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr


@pytest.mark.asyncio
async def test_auto_commit_success(tmp_path):
    """auto_commit returns True when git add + commit succeed."""
    # Create a fake .git directory
    (tmp_path / ".git").mkdir()

    call_count = 0

    async def fake_exec(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Calls: git add src/, git add tests/, git add -u, git diff --cached --quiet, git commit
        if call_count <= 3:
            # git add src/ + git add tests/ + git add -u
            return _FakeProc(returncode=0)
        elif call_count == 4:
            # git diff --cached --quiet -> exit 1 means there ARE staged changes
            return _FakeProc(returncode=1)
        elif call_count == 5:
            # git commit
            return _FakeProc(returncode=0)
        return _FakeProc(returncode=0)

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        result = await auto_commit(str(tmp_path), "test-session")

    assert result is True
    assert call_count == 5


@pytest.mark.asyncio
async def test_auto_commit_no_git_dir(tmp_path):
    """auto_commit returns False when project_path has no .git directory."""
    result = await auto_commit(str(tmp_path), "test-session")
    assert result is False


@pytest.mark.asyncio
async def test_auto_commit_nothing_staged(tmp_path):
    """auto_commit returns False when git diff --cached --quiet succeeds (nothing to commit)."""
    (tmp_path / ".git").mkdir()

    call_count = 0

    async def fake_exec(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Calls: git add src/, git add tests/, git add -u, git diff --cached --quiet
        if call_count <= 3:
            # git add src/ + git add tests/ + git add -u
            return _FakeProc(returncode=0)
        elif call_count == 4:
            # git diff --cached --quiet -> exit 0 means nothing staged
            return _FakeProc(returncode=0)
        return _FakeProc(returncode=0)

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        result = await auto_commit(str(tmp_path), "test-session")

    assert result is False
    assert call_count == 4  # Should stop after diff check
