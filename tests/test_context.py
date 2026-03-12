import pytest


@pytest.mark.skip(reason="stub -- implement in plan 03")
def test_context_includes_project_path(tmp_path):
    """INFR-09: assembled context includes project path."""
    pass


@pytest.mark.skip(reason="stub -- implement in plan 03")
def test_context_detects_stack(tmp_path):
    """INFR-09: detected stack appears in context string."""
    pass


@pytest.mark.skip(reason="stub -- implement in plan 03")
def test_context_excludes_ignored_dirs(tmp_path):
    """INFR-09: .git, node_modules, __pycache__ excluded from file list."""
    pass


@pytest.mark.skip(reason="stub -- implement in plan 03")
def test_context_caps_at_200_files(tmp_path):
    """INFR-09: file list capped at 200 entries."""
    pass
