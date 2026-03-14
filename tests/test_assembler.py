"""Tests for context assembler -- commands and settings integration."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def project_with_commands(tmp_path):
    """Create a project dir with .claude/commands/*.md files."""
    cmds_dir = tmp_path / ".claude" / "commands"
    cmds_dir.mkdir(parents=True)

    (cmds_dir / "migrate.md").write_text(
        "Analyze the current database schema and generate migration files"
    )
    (cmds_dir / "deploy.md").write_text(
        "Deploy the application to the production environment"
    )
    return tmp_path


@pytest.fixture
def project_with_settings(tmp_path):
    """Create a project dir with .claude/settings.local.json."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)

    settings = {"permissions": {"allow_exec": True}, "model": "opus"}
    (claude_dir / "settings.local.json").write_text(json.dumps(settings))
    return tmp_path


@pytest.fixture
def project_with_both(tmp_path):
    """Create a project dir with both commands and settings."""
    cmds_dir = tmp_path / ".claude" / "commands"
    cmds_dir.mkdir(parents=True)

    (cmds_dir / "migrate.md").write_text(
        "Analyze the current database schema and generate migration files"
    )

    settings = {"permissions": {"allow_exec": True}}
    (tmp_path / ".claude" / "settings.local.json").write_text(json.dumps(settings))
    return tmp_path


@pytest.fixture
def empty_project(tmp_path):
    """Create a bare project dir with no .claude directory."""
    return tmp_path


@pytest.fixture
def mock_pool():
    """Create a mock asyncpg pool that returns empty results."""
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[])
    return pool


class TestAssembleFullContextCommandsAndSettings:
    """Test that assemble_full_context includes commands and settings."""

    @pytest.mark.asyncio
    async def test_returns_available_commands_key(self, project_with_commands, mock_pool):
        from src.context.assembler import assemble_full_context

        with patch("src.context.assembler.get_recent_git_log", new_callable=AsyncMock, return_value=""):
            result = await assemble_full_context(str(project_with_commands), mock_pool)

        assert "available_commands" in result

    @pytest.mark.asyncio
    async def test_returns_project_settings_key(self, project_with_settings, mock_pool):
        from src.context.assembler import assemble_full_context

        with patch("src.context.assembler.get_recent_git_log", new_callable=AsyncMock, return_value=""):
            result = await assemble_full_context(str(project_with_settings), mock_pool)

        assert "project_settings" in result

    @pytest.mark.asyncio
    async def test_available_commands_formatted_string(self, project_with_commands, mock_pool):
        from src.context.assembler import assemble_full_context

        with patch("src.context.assembler.get_recent_git_log", new_callable=AsyncMock, return_value=""):
            result = await assemble_full_context(str(project_with_commands), mock_pool)

        cmds = result["available_commands"]
        assert isinstance(cmds, str)
        assert "- /deploy:" in cmds
        assert "- /migrate:" in cmds

    @pytest.mark.asyncio
    async def test_no_commands_returns_empty_string(self, empty_project, mock_pool):
        from src.context.assembler import assemble_full_context

        with patch("src.context.assembler.get_recent_git_log", new_callable=AsyncMock, return_value=""):
            result = await assemble_full_context(str(empty_project), mock_pool)

        assert result["available_commands"] == ""

    @pytest.mark.asyncio
    async def test_no_settings_returns_empty_dict(self, empty_project, mock_pool):
        from src.context.assembler import assemble_full_context

        with patch("src.context.assembler.get_recent_git_log", new_callable=AsyncMock, return_value=""):
            result = await assemble_full_context(str(empty_project), mock_pool)

        assert result["project_settings"] == {}

    @pytest.mark.asyncio
    async def test_existing_keys_unchanged(self, project_with_both, mock_pool):
        from src.context.assembler import assemble_full_context

        with patch("src.context.assembler.get_recent_git_log", new_callable=AsyncMock, return_value=""):
            result = await assemble_full_context(str(project_with_both), mock_pool)

        # Original 5 keys must still be present
        assert "workspace" in result
        assert "claude_md" in result
        assert "planning_docs" in result
        assert "git_log" in result
        assert "recent_tasks" in result
        # Plus the new 2
        assert "available_commands" in result
        assert "project_settings" in result
        assert len(result) == 7


class TestFormatAvailableCommands:
    """Test the format_available_commands helper."""

    def test_formats_commands_with_slash_prefix(self, project_with_commands):
        from src.context.assembler import format_available_commands

        result = format_available_commands(str(project_with_commands))
        lines = result.strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            assert line.startswith("- /")

    def test_empty_when_no_commands_dir(self, empty_project):
        from src.context.assembler import format_available_commands

        result = format_available_commands(str(empty_project))
        assert result == ""

    def test_truncates_long_descriptions(self, tmp_path):
        from src.context.assembler import format_available_commands

        cmds_dir = tmp_path / ".claude" / "commands"
        cmds_dir.mkdir(parents=True)
        (cmds_dir / "long.md").write_text("A" * 200)

        result = format_available_commands(str(tmp_path))
        # Description part should be truncated to 100 chars
        assert len(result.split(": ", 1)[1].strip()) <= 100
