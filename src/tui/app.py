"""
Main Textual application.

4-panel layout: Prompt (top-left), Plan (top-right),
Execute (bottom-left), Review (bottom-right).
Dark theme, keyboard-driven workflow.
"""
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Footer, Header

from src.tui.actions import prepare_agent_run, send_prompt
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
        ("ctrl+s", "send_prompt", "Send"),
        ("ctrl+p", "run_plan", "Plan"),
        ("ctrl+e", "run_execute", "Execute"),
        ("ctrl+r", "run_review", "Review"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, project_path: str = ".", **kwargs) -> None:
        super().__init__(**kwargs)
        self.project_path = project_path
        self._panel_ids = ["prompt-panel", "plan-panel", "execute-panel", "review-panel"]
        self._focus_index = 0

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

    def run_agent(self, agent_name: str) -> None:
        """Run a specific agent via action handlers."""
        prompt = prepare_agent_run(self, agent_name)
        if prompt is None:
            return
        # Actual agent execution is handled by streaming worker (Plan 03-03)
