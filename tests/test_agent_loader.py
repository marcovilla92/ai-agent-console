"""Tests for agent loader -- discovery and parsing of project agents."""
import os
from pathlib import Path

import pytest

from src.agents.loader import discover_project_agents


def _write_md(base: Path, filename: str, content: str) -> Path:
    """Helper: write a .md file under base/.claude/agents/."""
    agents_dir = base / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    md = agents_dir / filename
    md.write_text(content, encoding="utf-8")
    return md


class TestDiscoverAgents:
    def test_discover_agents_from_directory(self, tmp_path: Path):
        """Two .md files produce dict with 2 AgentConfig entries."""
        _write_md(tmp_path, "alpha.md", "---\nname: alpha\ndescription: Agent A\n---\nDo alpha things.")
        _write_md(tmp_path, "beta.md", "---\nname: beta\ndescription: Agent B\n---\nDo beta things.")
        result = discover_project_agents(str(tmp_path))
        assert len(result) == 2
        assert "alpha" in result
        assert "beta" in result
        assert result["alpha"].description == "Agent A"
        assert result["beta"].description == "Agent B"

    def test_discover_no_agents_dir(self, tmp_path: Path):
        """Non-existent .claude/agents/ returns empty dict."""
        result = discover_project_agents(str(tmp_path))
        assert result == {}

    def test_parse_with_frontmatter(self, tmp_path: Path):
        """Frontmatter populates name, description, allowed_transitions; body becomes system_prompt_inline."""
        _write_md(tmp_path, "coder.md", (
            "---\n"
            "name: coder\n"
            "description: Writes code\n"
            "allowed_transitions:\n"
            "  - test\n"
            "  - review\n"
            "---\n"
            "You are a code writer."
        ))
        result = discover_project_agents(str(tmp_path))
        cfg = result["coder"]
        assert cfg.name == "coder"
        assert cfg.description == "Writes code"
        assert cfg.system_prompt_inline == "You are a code writer."
        assert cfg.allowed_transitions == ("test", "review")
        assert cfg.source == "project"
        assert cfg.file_path is not None and cfg.file_path.endswith("coder.md")

    def test_parse_without_frontmatter(self, tmp_path: Path):
        """Plain .md file gets name from filename, default description, broad transitions."""
        _write_md(tmp_path, "helper.md", "Just a plain helper agent prompt.")
        result = discover_project_agents(str(tmp_path))
        cfg = result["helper"]
        assert cfg.name == "helper"
        assert cfg.description == "Project agent: helper"
        assert cfg.system_prompt_inline == "Just a plain helper agent prompt."
        assert len(cfg.allowed_transitions) == 5  # broad defaults
        assert cfg.source == "project"

    def test_skip_broken_files(self, tmp_path: Path):
        """Empty file and binary file are skipped without raising."""
        _write_md(tmp_path, "empty.md", "")
        agents_dir = tmp_path / ".claude" / "agents"
        binary_file = agents_dir / "binary.md"
        binary_file.write_bytes(b"\x00\x01\x02\xff\xfe")
        # Also add one valid file to ensure it's returned
        _write_md(tmp_path, "valid.md", "I am valid.")
        result = discover_project_agents(str(tmp_path))
        assert "empty" not in result
        assert "valid" in result

    def test_name_sanitization(self, tmp_path: Path):
        """'My Agent File.md' becomes 'my-agent-file'."""
        _write_md(tmp_path, "My Agent File.md", "Hello")
        result = discover_project_agents(str(tmp_path))
        assert "my-agent-file" in result

    def test_all_agents_have_project_source(self, tmp_path: Path):
        """Every discovered agent has source='project' and a file_path."""
        _write_md(tmp_path, "a.md", "---\nname: a\n---\nBody A")
        _write_md(tmp_path, "b.md", "Plain B")
        result = discover_project_agents(str(tmp_path))
        for name, cfg in result.items():
            assert cfg.source == "project", f"{name} should have source='project'"
            assert cfg.file_path is not None, f"{name} should have file_path set"
            assert os.path.isabs(cfg.file_path), f"{name} file_path should be absolute"

    def test_system_prompt_file_is_empty_string(self, tmp_path: Path):
        """Project agents use inline prompts, so system_prompt_file is empty."""
        _write_md(tmp_path, "x.md", "prompt text")
        result = discover_project_agents(str(tmp_path))
        assert result["x"].system_prompt_file == ""
