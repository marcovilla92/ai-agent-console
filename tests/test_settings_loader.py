"""Tests for settings loader -- loading and merging project settings."""
import json
from pathlib import Path

import pytest

from src.settings.loader import load_project_settings, merge_settings


def _write_settings(base: Path, data: dict | str) -> Path:
    """Helper: write .claude/settings.local.json under base."""
    claude_dir = base / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    f = claude_dir / "settings.local.json"
    content = data if isinstance(data, str) else json.dumps(data)
    f.write_text(content, encoding="utf-8")
    return f


class TestLoadSettings:
    def test_returns_empty_dict_when_no_file(self, tmp_path: Path):
        """Missing .claude/settings.local.json returns empty dict."""
        result = load_project_settings(str(tmp_path))
        assert result == {}

    def test_returns_parsed_json_when_valid(self, tmp_path: Path):
        """Valid JSON file is parsed and returned as dict."""
        _write_settings(tmp_path, {"permissions": {"allow": ["Bash", "WebSearch"]}})
        result = load_project_settings(str(tmp_path))
        assert result == {"permissions": {"allow": ["Bash", "WebSearch"]}}

    def test_returns_empty_dict_on_invalid_json(self, tmp_path: Path):
        """Invalid JSON returns empty dict with warning (no crash)."""
        _write_settings(tmp_path, "{not valid json!!!")
        result = load_project_settings(str(tmp_path))
        assert result == {}


class TestMergeSettings:
    def test_empty_project_returns_global_unchanged(self):
        """Empty project settings returns copy of global."""
        global_s = {"permissions": {"allow": ["Read"]}, "system_flags": {"debug": True}}
        result = merge_settings(global_s, {})
        assert result == global_s
        # Must be a copy, not same object
        assert result is not global_s

    def test_project_overrides_whitelisted_permissions(self):
        """Project permissions.allow overrides global permissions.allow."""
        global_s = {"permissions": {"allow": ["Read"]}}
        project_s = {"permissions": {"allow": ["Bash", "WebSearch"]}}
        result = merge_settings(global_s, project_s)
        assert result["permissions"]["allow"] == ["Bash", "WebSearch"]

    def test_non_whitelisted_keys_preserved(self):
        """Project cannot override non-whitelisted keys like system_flags."""
        global_s = {"permissions": {"allow": ["Read"]}, "system_flags": {"debug": True}}
        project_s = {"permissions": {"allow": ["Bash"]}, "system_flags": {"debug": False}}
        result = merge_settings(global_s, project_s)
        # permissions overridden (whitelisted)
        assert result["permissions"]["allow"] == ["Bash"]
        # system_flags preserved from global (NOT whitelisted)
        assert result["system_flags"]["debug"] is True

    def test_nested_permissions_merge(self):
        """Nested permission keys merge correctly -- project values win for whitelisted."""
        global_s = {"permissions": {"allow": ["Read"], "deny": ["Write"]}}
        project_s = {"permissions": {"allow": ["Bash", "Read"], "extra": "value"}}
        result = merge_settings(global_s, project_s)
        assert result["permissions"]["allow"] == ["Bash", "Read"]
        assert result["permissions"]["extra"] == "value"
        # deny from global is preserved since project didn't have deny
        # (deep merge within whitelisted key)
        assert result["permissions"]["deny"] == ["Write"]

    def test_global_not_mutated(self):
        """merge_settings does not mutate the global_settings dict."""
        global_s = {"permissions": {"allow": ["Read"]}}
        project_s = {"permissions": {"allow": ["Bash"]}}
        merge_settings(global_s, project_s)
        assert global_s["permissions"]["allow"] == ["Read"]
