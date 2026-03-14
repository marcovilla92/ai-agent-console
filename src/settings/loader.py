"""
Settings loading and merging for project-defined settings.

Reads `.claude/settings.local.json` from a project directory and
merges project settings with global defaults using a whitelist
to prevent project overrides of security-sensitive keys.
"""
import copy
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

CLAUDE_SETTINGS_FILE = ".claude/settings.local.json"

# Top-level keys that project settings are allowed to override.
# This is the security boundary -- anything not listed here stays
# from global and cannot be changed by project settings.
SETTINGS_WHITELIST: set[str] = {"permissions"}


def load_project_settings(project_path: str) -> dict:
    """Read and parse .claude/settings.local.json from a project.

    Args:
        project_path: Root directory of the project.

    Returns:
        Parsed settings dict. Empty dict if file missing or invalid JSON.
    """
    settings_file = Path(project_path) / CLAUDE_SETTINGS_FILE
    if not settings_file.is_file():
        return {}

    try:
        content = settings_file.read_text(encoding="utf-8", errors="replace")
        return json.loads(content)
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("Invalid JSON in %s: %s", settings_file, exc)
        return {}


def merge_settings(global_settings: dict, project_settings: dict) -> dict:
    """Deep-merge project settings into global, respecting whitelist.

    Only top-level keys in SETTINGS_WHITELIST can be overridden by
    project settings. Non-whitelisted keys from global are preserved.

    For whitelisted keys, a deep merge is performed: project values
    override global values at the leaf level.

    Args:
        global_settings: Global/default settings dict.
        project_settings: Project-specific settings dict.

    Returns:
        New merged dict (neither input is mutated).
    """
    result = copy.deepcopy(global_settings)

    for key, value in project_settings.items():
        if key not in SETTINGS_WHITELIST:
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            # Deep merge for dict values within whitelisted keys
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)

    return result


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    merged = base.copy()
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged
