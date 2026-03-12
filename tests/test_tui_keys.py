"""Tests for TUI keyboard bindings and actions."""
import pytest
from unittest.mock import patch, MagicMock

from src.tui.app import AgentConsoleApp
from src.tui.actions import get_prompt_text, prepare_agent_run, complete_agent_run, send_prompt, AGENT_PANEL_MAP


async def test_action_cycle_focus():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        # Directly call the action to test focus cycling logic
        app.action_cycle_focus()
        assert app._focus_index == 1
        app.action_cycle_focus()
        assert app._focus_index == 2


async def test_action_cycle_focus_wraps():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        for _ in range(4):
            app.action_cycle_focus()
        assert app._focus_index == 0


async def test_bindings_defined():
    # Check BINDINGS class attribute directly
    binding_keys = {b[0] for b in AgentConsoleApp.BINDINGS}
    assert "tab" in binding_keys
    assert "ctrl+q" in binding_keys
    assert "ctrl+p" in binding_keys
    assert "ctrl+e" in binding_keys
    assert "ctrl+r" in binding_keys


async def test_get_prompt_text_empty_returns_none():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        result = get_prompt_text(app)
        assert result is None


async def test_get_prompt_text_with_content():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        app.prompt_panel.load_text("Build an API")
        result = get_prompt_text(app)
        assert result == "Build an API"


async def test_prepare_agent_run_updates_status():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        app.prompt_panel.load_text("Build something")
        prepare_agent_run(app, "plan")
        assert "PLAN" in app.status_bar.display_text
        assert "running" in app.status_bar.display_text


async def test_prepare_agent_run_empty_prompt_returns_none():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        result = prepare_agent_run(app, "plan")
        assert result is None


async def test_complete_agent_run_success():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        complete_agent_run(app, "plan", success=True)
        assert "complete" in app.status_bar.display_text


async def test_complete_agent_run_failure():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        complete_agent_run(app, "plan", success=False)
        assert "error" in app.status_bar.display_text


async def test_send_prompt_with_content():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        app.prompt_panel.load_text("Build an API")
        result = send_prompt(app)
        assert result == "Build an API"
        # send_prompt starts with plan agent
        assert "PLAN" in app.status_bar.display_text


async def test_send_prompt_empty_returns_none():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        result = send_prompt(app)
        assert result is None


async def test_ctrl_s_binding_defined():
    binding_keys = {b[0] for b in AgentConsoleApp.BINDINGS}
    assert "ctrl+s" in binding_keys


async def test_run_agent_uses_prepare_agent_run():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        # Without prompt, run_agent should return without setting status
        app.run_agent("plan")
        # Status should not show "running" because prompt is empty
        assert "running" not in app.status_bar.display_text


async def test_agent_panel_map_complete():
    assert "plan" in AGENT_PANEL_MAP
    assert "execute" in AGENT_PANEL_MAP
    assert "review" in AGENT_PANEL_MAP


@patch("src.tui.app.start_agent_worker")
async def test_run_agent_calls_start_agent_worker(mock_worker):
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        app.prompt_panel.load_text("Build something")
        app.run_agent("plan")
        mock_worker.assert_called_once_with(app, "plan", "Build something")


@patch("src.tui.streaming.start_agent_worker")
async def test_send_prompt_calls_start_agent_worker(mock_worker):
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        app.prompt_panel.load_text("Build an API")
        send_prompt(app)
        mock_worker.assert_called_once_with(app, "plan", "Build an API")


async def test_status_bar_default_hint_says_ctrl_s():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        assert "Ctrl+S" in app.status_bar.display_text
        assert "Ctrl+Enter" not in app.status_bar.display_text
