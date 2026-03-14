"""Tests for command loader -- discovery of project commands from .claude/commands/*.md."""
import os
from pathlib import Path

import pytest

from src.commands.loader import discover_project_commands, CommandInfo


def _write_cmd(base: Path, filename: str, content: str) -> Path:
    """Helper: write a file under base/.claude/commands/."""
    cmds_dir = base / ".claude" / "commands"
    cmds_dir.mkdir(parents=True, exist_ok=True)
    f = cmds_dir / filename
    f.write_text(content, encoding="utf-8")
    return f


class TestDiscoverCommands:
    def test_empty_dict_when_no_commands_dir(self, tmp_path: Path):
        """Non-existent .claude/commands/ returns empty dict."""
        result = discover_project_commands(str(tmp_path))
        assert result == {}

    def test_returns_command_info_for_md_files(self, tmp_path: Path):
        """Each .md file produces a CommandInfo entry keyed by sanitized name."""
        _write_cmd(tmp_path, "migrate.md", "Run database migration.")
        _write_cmd(tmp_path, "deploy.md", "Deploy to production server.")
        result = discover_project_commands(str(tmp_path))
        assert len(result) == 2
        assert "migrate" in result
        assert "deploy" in result
        assert isinstance(result["migrate"], CommandInfo)
        assert result["migrate"].description == "Run database migration."
        assert result["deploy"].description == "Deploy to production server."

    def test_skips_empty_md_files(self, tmp_path: Path):
        """Empty .md files are skipped gracefully."""
        _write_cmd(tmp_path, "empty.md", "")
        _write_cmd(tmp_path, "valid.md", "A valid command.")
        result = discover_project_commands(str(tmp_path))
        assert "empty" not in result
        assert "valid" in result

    def test_skips_non_md_files(self, tmp_path: Path):
        """Non-.md files in the commands directory are ignored."""
        _write_cmd(tmp_path, "readme.txt", "Not a command.")
        _write_cmd(tmp_path, "script.sh", "#!/bin/bash")
        _write_cmd(tmp_path, "actual.md", "A real command.")
        result = discover_project_commands(str(tmp_path))
        assert len(result) == 1
        assert "actual" in result

    def test_command_info_fields(self, tmp_path: Path):
        """CommandInfo has name, description, file_path fields."""
        _write_cmd(tmp_path, "test-cmd.md", "Run all tests.")
        result = discover_project_commands(str(tmp_path))
        info = result["test-cmd"]
        assert info.name == "test-cmd"
        assert info.description == "Run all tests."
        assert os.path.isabs(info.file_path)
        assert info.file_path.endswith("test-cmd.md")

    def test_description_truncated_to_200_chars(self, tmp_path: Path):
        """Description is truncated to first 200 chars of file content."""
        long_content = "A" * 300
        _write_cmd(tmp_path, "long.md", long_content)
        result = discover_project_commands(str(tmp_path))
        assert len(result["long"].description) == 200

    def test_name_sanitized_lowercase_hyphens(self, tmp_path: Path):
        """Name is sanitized: lowercase, hyphens, strip special chars."""
        _write_cmd(tmp_path, "My Command File.md", "Hello")
        _write_cmd(tmp_path, "UPPER_CASE.md", "World")
        result = discover_project_commands(str(tmp_path))
        assert "my-command-file" in result
        assert "uppercase" in result
