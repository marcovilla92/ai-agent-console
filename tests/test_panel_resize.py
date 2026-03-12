"""Tests for panel resize and collapse behavior."""
import pytest

from src.tui.app import AgentConsoleApp
from src.tui.panels import OutputPanel, PromptPanel


# --- Panel Collapse Tests ---


async def test_toggle_panel_hides_panel():
    """action_toggle_panel sets panel display to False."""
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        panel = app.query_one("#plan-panel", OutputPanel)
        assert panel.display is True
        app.action_toggle_panel("plan-panel")
        assert panel.display is False


async def test_toggle_panel_restores_panel():
    """Toggling a collapsed panel restores visibility."""
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        panel = app.query_one("#plan-panel", OutputPanel)
        app.action_toggle_panel("plan-panel")
        assert panel.display is False
        app.action_toggle_panel("plan-panel")
        assert panel.display is True


async def test_collapsed_panel_others_visible():
    """When a panel is collapsed, remaining panels are still visible."""
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        app.action_toggle_panel("plan-panel")
        assert app.query_one("#prompt-panel").display is True
        assert app.query_one("#execute-panel").display is True
        assert app.query_one("#review-panel").display is True


async def test_bindings_include_toggle_keys():
    """Ctrl+1 through Ctrl+4 are bound to toggle_panel actions."""
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        binding_keys = [b.key for b in app.BINDINGS]
        assert "ctrl+1" in binding_keys
        assert "ctrl+2" in binding_keys
        assert "ctrl+3" in binding_keys
        assert "ctrl+4" in binding_keys
