"""
TUI panel widgets.

PromptPanel: editable text area for user input.
OutputPanel: read-only scrolling log for agent output (Plan, Execute, Review).
"""
from textual.widgets import RichLog, TextArea


class PromptPanel(TextArea):
    """Editable text area for the user prompt."""

    DEFAULT_CSS = """
    PromptPanel {
        height: 1fr;
        border: solid $accent;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            id="prompt-panel",
            language="markdown",
            **kwargs,
        )
        self.border_title = "Prompt"


class OutputPanel(RichLog):
    """Read-only scrolling output panel for an agent."""

    DEFAULT_CSS = """
    OutputPanel {
        height: 1fr;
        border: solid $secondary;
    }
    """

    def __init__(self, panel_id: str, title: str, **kwargs) -> None:
        super().__init__(id=panel_id, wrap=True, markup=True, **kwargs)
        self.border_title = title

    def clear_output(self) -> None:
        """Clear all content from the panel."""
        self.clear()
