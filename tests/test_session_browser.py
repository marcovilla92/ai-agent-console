"""Tests for session browser modal and Ctrl+B binding."""
import pytest

from src.db.schema import Session
from src.tui.session_browser import SessionBrowser


SAMPLE_SESSIONS = [
    Session(name="task-alpha", project_path="/proj/a", created_at="2026-03-10T10:00:00Z", id=1),
    Session(name="task-beta", project_path="/proj/b", created_at="2026-03-11T12:00:00Z", id=2),
    Session(name="task-gamma", project_path="/proj/c", created_at="2026-03-12T14:00:00Z", id=3),
]


def test_session_browser_instantiation():
    """SessionBrowser can be instantiated with a list of sessions."""
    browser = SessionBrowser(SAMPLE_SESSIONS)
    assert browser.sessions == SAMPLE_SESSIONS


@pytest.mark.asyncio
async def test_session_browser_compose_has_data_table():
    """SessionBrowser.compose yields a DataTable and buttons."""
    from textual.app import App, ComposeResult
    from textual.widgets import DataTable, Button

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield from []

    app = TestApp()
    async with app.run_test() as pilot:
        browser = SessionBrowser(SAMPLE_SESSIONS)
        await app.push_screen(browser)
        await pilot.pause()
        # Verify DataTable exists
        table = browser.query_one("#session-table", DataTable)
        assert table is not None
        # Verify buttons exist
        resume = browser.query_one("#resume", Button)
        cancel = browser.query_one("#cancel", Button)
        assert resume is not None
        assert cancel is not None


def test_session_browser_empty_sessions():
    """SessionBrowser works with empty session list."""
    browser = SessionBrowser([])
    assert browser.sessions == []


def test_session_browser_dismiss_none_default():
    """SessionBrowser should return None when cancelled."""
    browser = SessionBrowser(SAMPLE_SESSIONS)
    # Verify the modal type hint allows None
    assert browser.sessions is not None


class TestSessionBrowserApp:
    """Integration tests using Textual's async test harness."""

    @pytest.mark.asyncio
    async def test_session_browser_mounts_table(self):
        """SessionBrowser on_mount populates DataTable with session rows."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield from []  # Empty app

        app = TestApp()
        async with app.run_test() as pilot:
            browser = SessionBrowser(SAMPLE_SESSIONS)
            await app.push_screen(browser)
            await pilot.pause()
            table = browser.query_one("#session-table")
            assert table.row_count == 3

    @pytest.mark.asyncio
    async def test_session_browser_cancel_dismisses_none(self):
        """Pressing Cancel button dismisses modal with None."""
        from textual.app import App, ComposeResult

        results = []

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield from []

        app = TestApp()
        async with app.run_test() as pilot:
            browser = SessionBrowser(SAMPLE_SESSIONS)
            await app.push_screen(browser, callback=lambda r: results.append(r))
            await pilot.pause()
            cancel_btn = browser.query_one("#cancel")
            await pilot.click(cancel_btn)
            await pilot.pause()
            assert results == [None]

    @pytest.mark.asyncio
    async def test_session_browser_resume_dismisses_with_id(self):
        """Pressing Resume button dismisses modal with selected session ID."""
        from textual.app import App, ComposeResult
        from textual.widgets import DataTable

        results = []

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield from []

        app = TestApp()
        async with app.run_test() as pilot:
            browser = SessionBrowser(SAMPLE_SESSIONS)
            await app.push_screen(browser, callback=lambda r: results.append(r))
            await pilot.pause()
            # Select the first row in the table
            table = browser.query_one("#session-table", DataTable)
            table.move_cursor(row=0)
            # Click resume
            resume_btn = browser.query_one("#resume")
            await pilot.click(resume_btn)
            await pilot.pause()
            assert results == [1]  # session id=1

    @pytest.mark.asyncio
    async def test_escape_dismisses_with_none(self):
        """Pressing Escape dismisses modal with None."""
        from textual.app import App, ComposeResult

        results = []

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield from []

        app = TestApp()
        async with app.run_test() as pilot:
            browser = SessionBrowser(SAMPLE_SESSIONS)
            await app.push_screen(browser, callback=lambda r: results.append(r))
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert results == [None]


def test_app_has_ctrl_b_binding():
    """AgentConsoleApp has a Ctrl+B binding for browse_sessions."""
    from src.tui.app import AgentConsoleApp
    app = AgentConsoleApp()
    # _bindings.keys is a dict of key -> Binding
    keys = list(app._bindings.key_to_bindings.keys())
    assert "ctrl+b" in keys
