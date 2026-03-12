"""
Main Textual application.

4-panel layout: Prompt (top-left), Plan (top-right),
Execute (bottom-left), Review (bottom-right).
Dark theme, keyboard-driven workflow.
"""
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header

from src.tui.actions import prepare_agent_run, send_prompt
from src.tui.streaming import start_agent_worker
from src.tui.panels import OutputPanel, PromptPanel
from src.tui.status_bar import StatusBar

CSS_PATH = Path(__file__).parent / "theme.tcss"


class AgentConsoleApp(App):
    """AI Agent Workflow Console TUI."""

    TITLE = "AI Agent Console"
    CSS_PATH = CSS_PATH
    THEME = "textual-dark"

    BINDINGS = [
        ("tab", "cycle_focus", "Next Panel"),
        Binding("ctrl+s", "send_prompt", "Send", priority=True),
        Binding("ctrl+p", "run_plan", "Plan", priority=True),
        Binding("ctrl+e", "run_execute", "Execute", priority=True),
        Binding("ctrl+r", "run_review", "Review", priority=True),
        ("ctrl+1", "toggle_panel('prompt-panel')", "Toggle Prompt"),
        ("ctrl+2", "toggle_panel('plan-panel')", "Toggle Plan"),
        ("ctrl+3", "toggle_panel('execute-panel')", "Toggle Execute"),
        ("ctrl+4", "toggle_panel('review-panel')", "Toggle Review"),
        ("ctrl+up", "resize_row('up')", "Grow Top"),
        ("ctrl+down", "resize_row('down')", "Grow Bottom"),
        ("ctrl+left", "resize_col('left')", "Grow Left"),
        ("ctrl+right", "resize_col('right')", "Grow Right"),
        ("ctrl+b", "browse_sessions", "Sessions"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, project_path: str = ".", **kwargs) -> None:
        super().__init__(**kwargs)
        self.project_path = project_path
        self._panel_ids = ["prompt-panel", "plan-panel", "execute-panel", "review-panel"]
        self._focus_index = 0
        self._db = None  # aiosqlite.Connection, set externally if available
        self._row_top: int = 1
        self._row_bottom: int = 1
        self._col_left: int = 1
        self._col_right: int = 1

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="app-grid"):
            yield PromptPanel()
            yield OutputPanel("plan-panel", "Plan")
            yield OutputPanel("execute-panel", "Execute")
            yield OutputPanel("review-panel", "Review")
        yield StatusBar()
        yield Footer()

    def get_panel(self, panel_id: str) -> OutputPanel:
        """Get an output panel by ID."""
        return self.query_one(f"#{panel_id}", OutputPanel)

    @property
    def prompt_panel(self) -> PromptPanel:
        return self.query_one("#prompt-panel", PromptPanel)

    @property
    def plan_panel(self) -> OutputPanel:
        return self.query_one("#plan-panel", OutputPanel)

    @property
    def execute_panel(self) -> OutputPanel:
        return self.query_one("#execute-panel", OutputPanel)

    @property
    def review_panel(self) -> OutputPanel:
        return self.query_one("#review-panel", OutputPanel)

    @property
    def status_bar(self) -> StatusBar:
        return self.query_one("#status-bar", StatusBar)

    def action_cycle_focus(self) -> None:
        """Cycle focus between panels with Tab."""
        self._focus_index = (self._focus_index + 1) % len(self._panel_ids)
        panel_id = self._panel_ids[self._focus_index]
        widget = self.query_one(f"#{panel_id}")
        widget.focus()

    def action_send_prompt(self) -> None:
        """Send prompt to the full pipeline (plan -> execute -> review)."""
        import logging
        logging.getLogger(__name__).info("action_send_prompt triggered")
        send_prompt(self)

    def action_run_plan(self) -> None:
        """Trigger PLAN agent."""
        self.run_agent("plan")

    def action_run_execute(self) -> None:
        """Trigger EXECUTE agent."""
        self.run_agent("execute")

    def action_run_review(self) -> None:
        """Trigger REVIEW agent."""
        self.run_agent("review")

    def action_resize_row(self, direction: str) -> None:
        """Resize grid row proportions (Ctrl+Up/Down)."""
        if direction == "up":
            self._row_top = min(self._row_top + 1, 4)
            self._row_bottom = max(self._row_bottom - 1, 1)
        elif direction == "down":
            self._row_bottom = min(self._row_bottom + 1, 4)
            self._row_top = max(self._row_top - 1, 1)
        grid = self.query_one("#app-grid")
        grid.styles.grid_rows = f"{self._row_top}fr {self._row_bottom}fr"

    def action_resize_col(self, direction: str) -> None:
        """Resize grid column proportions (Ctrl+Left/Right)."""
        if direction == "left":
            self._col_left = min(self._col_left + 1, 4)
            self._col_right = max(self._col_right - 1, 1)
        elif direction == "right":
            self._col_right = min(self._col_right + 1, 4)
            self._col_left = max(self._col_left - 1, 1)
        grid = self.query_one("#app-grid")
        grid.styles.grid_columns = f"{self._col_left}fr {self._col_right}fr"

    def action_toggle_panel(self, panel_id: str) -> None:
        """Toggle visibility of a panel (collapse/expand)."""
        panel = self.query_one(f"#{panel_id}")
        panel.display = not panel.display

    def action_browse_sessions(self) -> None:
        """Open session browser modal (Ctrl+B)."""
        if self._db is None:
            self.notify("No database connection", severity="warning")
            return

        async def _load_and_show() -> None:
            from src.db.repository import SessionRepository
            from src.tui.session_browser import SessionBrowser

            repo = SessionRepository(self._db)
            sessions = await repo.list_all()
            self.push_screen(
                SessionBrowser(sessions), callback=self._on_session_selected
            )

        self.run_worker(_load_and_show, exclusive=False)

    def _on_session_selected(self, session_id: int | None) -> None:
        """Callback after session browser dismisses."""
        if session_id is None:
            return

        from src.tui.actions import AGENT_PANEL_MAP

        async def _load_session() -> None:
            from src.db.repository import AgentOutputRepository, SessionRepository

            if self._db is None:
                return

            # Load session info
            session_repo = SessionRepository(self._db)
            session = await session_repo.get(session_id)

            # Load agent outputs
            output_repo = AgentOutputRepository(self._db)
            outputs = await output_repo.get_by_session(session_id)

            for output in outputs:
                panel_id = AGENT_PANEL_MAP.get(output.agent_type)
                if panel_id:
                    panel = self.get_panel(panel_id)
                    panel.clear_output()
                    panel.write(output.raw_output)

            # Update status
            session_name = session.name if session else f"#{session_id}"
            self.status_bar.set_status(
                agent="session",
                state="resumed",
                step=f"Session #{session_id}: {session_name}",
                next_action="Session loaded",
            )

        self.run_worker(_load_session, exclusive=False)

    def run_agent(self, agent_name: str) -> None:
        """Run a specific agent via action handlers."""
        prompt = prepare_agent_run(self, agent_name)
        if prompt is None:
            return
        start_agent_worker(self, agent_name, prompt)
