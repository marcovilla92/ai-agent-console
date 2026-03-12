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
        binding_keys = [b[0] if isinstance(b, tuple) else b.key for b in app.BINDINGS]
        assert "ctrl+1" in binding_keys
        assert "ctrl+2" in binding_keys
        assert "ctrl+3" in binding_keys
        assert "ctrl+4" in binding_keys


# --- Panel Resize Tests ---


async def test_resize_row_up_increases_top():
    """action_resize_row('up') increases top row ratio."""
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        assert app._row_top == 1
        assert app._row_bottom == 1
        app.action_resize_row("up")
        assert app._row_top == 2
        assert app._row_bottom == 1


async def test_resize_row_down_increases_bottom():
    """action_resize_row('down') increases bottom row ratio."""
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        app.action_resize_row("down")
        assert app._row_bottom == 2
        assert app._row_top == 1


async def test_resize_row_clamp_max():
    """Row ratios are clamped at 4."""
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        for _ in range(5):
            app.action_resize_row("up")
        assert app._row_top == 4
        assert app._row_bottom == 1


async def test_resize_row_clamp_min():
    """Row ratios cannot go below 1."""
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        for _ in range(5):
            app.action_resize_row("down")
        assert app._row_top == 1
        assert app._row_bottom == 4


async def test_resize_col_left_increases_left():
    """action_resize_col('left') increases left column ratio."""
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        app.action_resize_col("left")
        assert app._col_left == 2
        assert app._col_right == 1


async def test_resize_col_right_increases_right():
    """action_resize_col('right') increases right column ratio."""
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        app.action_resize_col("right")
        assert app._col_right == 2
        assert app._col_left == 1


async def test_resize_col_clamp():
    """Column ratios are clamped between 1 and 4."""
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        for _ in range(5):
            app.action_resize_col("left")
        assert app._col_left == 4
        assert app._col_right == 1
