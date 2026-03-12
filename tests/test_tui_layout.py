"""Tests for TUI layout and panel structure."""
import pytest
from textual.widgets import Header, Footer

from src.tui.app import AgentConsoleApp
from src.tui.panels import PromptPanel, OutputPanel
from src.tui.status_bar import StatusBar


async def test_app_has_four_panels():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        assert app.query_one("#prompt-panel", PromptPanel)
        assert app.query_one("#plan-panel", OutputPanel)
        assert app.query_one("#execute-panel", OutputPanel)
        assert app.query_one("#review-panel", OutputPanel)


async def test_app_has_header_and_footer():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        assert app.query_one(Header)
        assert app.query_one(Footer)


async def test_app_has_status_bar():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        bar = app.query_one("#status-bar", StatusBar)
        assert bar is not None


async def test_app_dark_theme():
    async with AgentConsoleApp().run_test() as pilot:
        assert pilot.app.theme == "textual-dark"


async def test_panel_titles():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        assert app.prompt_panel.border_title == "Prompt"
        assert app.plan_panel.border_title == "Plan"
        assert app.execute_panel.border_title == "Execute"
        assert app.review_panel.border_title == "Review"


async def test_output_panel_clear():
    async with AgentConsoleApp().run_test() as pilot:
        app = pilot.app
        panel = app.plan_panel
        panel.write("test content")
        panel.clear_output()
        assert len(panel.lines) == 0


async def test_status_bar_default_text():
    async with AgentConsoleApp().run_test() as pilot:
        bar = pilot.app.status_bar
        # StatusBar stores its text via update(), check _content
        text = bar.display_text
        assert "Agent:" in text
        assert "idle" in text


async def test_status_bar_update():
    async with AgentConsoleApp().run_test() as pilot:
        bar = pilot.app.status_bar
        bar.set_status(agent="plan", state="running", step="1/3", next_action="Wait...")
        text = bar.display_text
        assert "PLAN" in text
        assert "running" in text
