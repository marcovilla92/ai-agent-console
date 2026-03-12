"""
Status bar widget.

Shows current agent name, workflow state, step description, and next action.
"""
from textual.widgets import Static


class StatusBar(Static):
    """Footer status bar showing workflow state."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="status-bar")
        self._agent = "none"
        self._state = "idle"
        self._step = ""
        self._next_action = "Enter a prompt and press Ctrl+S"
        self._display_text = ""

    def set_status(
        self,
        *,
        agent: str | None = None,
        state: str | None = None,
        step: str | None = None,
        next_action: str | None = None,
    ) -> None:
        """Update status bar fields and refresh display."""
        if agent is not None:
            self._agent = agent
        if state is not None:
            self._state = state
        if step is not None:
            self._step = step
        if next_action is not None:
            self._next_action = next_action
        self._refresh_text()

    @property
    def display_text(self) -> str:
        """Current status bar text."""
        return self._display_text

    def _refresh_text(self) -> None:
        parts = [
            f"Agent: {self._agent.upper()}",
            f"State: {self._state}",
        ]
        if self._step:
            parts.append(f"Step: {self._step}")
        parts.append(f"Next: {self._next_action}")
        self._display_text = " | ".join(parts)
        self.update(self._display_text)

    def on_mount(self) -> None:
        self._refresh_text()
