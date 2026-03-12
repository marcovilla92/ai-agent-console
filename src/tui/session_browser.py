"""
Session browser modal for viewing and resuming past sessions.

Lists sessions in a DataTable with ID, Name, Project, and Date columns.
User can select a session to resume or cancel.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Label

from src.db.schema import Session


class SessionBrowser(ModalScreen[int | None]):
    """Modal screen listing past sessions for resume."""

    DEFAULT_CSS = """
    SessionBrowser {
        align: center middle;
    }

    SessionBrowser > Vertical {
        width: 80;
        height: 24;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    SessionBrowser Label {
        width: 100%;
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    SessionBrowser DataTable {
        height: 1fr;
        margin-bottom: 1;
    }

    SessionBrowser Horizontal {
        width: 100%;
        align: center middle;
        height: auto;
    }

    SessionBrowser Button {
        margin: 0 1;
    }
    """

    def __init__(self, sessions: list[Session]) -> None:
        super().__init__()
        self.sessions = sessions

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Past Sessions")
            yield DataTable(id="session-table")
            with Horizontal():
                yield Button("Resume", id="resume", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        """Populate the DataTable with session data."""
        table = self.query_one("#session-table", DataTable)
        table.add_columns("ID", "Name", "Project", "Date")
        for session in self.sessions:
            table.add_row(
                str(session.id),
                session.name,
                session.project_path,
                session.created_at,
                key=str(session.id),
            )
        table.cursor_type = "row"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "resume":
            self._resume_selected()
        elif event.button.id == "cancel":
            self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)

    def key_enter(self) -> None:
        self._resume_selected()

    def _resume_selected(self) -> None:
        """Dismiss with the selected session's ID, or None if nothing selected."""
        table = self.query_one("#session-table", DataTable)
        if table.row_count == 0:
            self.dismiss(None)
            return
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        try:
            session_id = int(str(row_key.value))
        except (ValueError, TypeError, AttributeError):
            self.dismiss(None)
            return
        self.dismiss(session_id)
