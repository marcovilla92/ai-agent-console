"""
Modal confirmation dialogs for orchestrator routing decisions.

RerouteConfirmDialog: shown when the orchestrator wants to re-route
to a different agent. User confirms (Enter) or cancels (Escape).

HaltDialog: shown when iteration limit reached. Offers Continue,
Approve Now, or Stop options.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class RerouteConfirmDialog(ModalScreen[bool]):
    """Modal asking user to confirm agent re-routing."""

    DEFAULT_CSS = """
    RerouteConfirmDialog {
        align: center middle;
    }

    RerouteConfirmDialog > Vertical {
        width: 60;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    RerouteConfirmDialog Label {
        width: 100%;
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    RerouteConfirmDialog Static {
        width: 100%;
        margin-bottom: 1;
    }

    RerouteConfirmDialog Horizontal {
        width: 100%;
        align: center middle;
        height: auto;
    }

    RerouteConfirmDialog Button {
        margin: 0 1;
    }
    """

    def __init__(self, agent: str, reasoning: str) -> None:
        super().__init__()
        self.agent = agent
        self.reasoning = reasoning

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"Re-route to {self.agent.upper()}?")
            yield Static(self.reasoning)
            with Horizontal():
                yield Button("Confirm", id="confirm", variant="primary")
                yield Button("Cancel", id="cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")

    def key_enter(self) -> None:
        self.dismiss(True)

    def key_escape(self) -> None:
        self.dismiss(False)


class HaltDialog(ModalScreen[str]):
    """Modal shown when iteration limit reached."""

    DEFAULT_CSS = """
    HaltDialog {
        align: center middle;
    }

    HaltDialog > Vertical {
        width: 70;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }

    HaltDialog Label {
        width: 100%;
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    HaltDialog Static {
        width: 100%;
        margin-bottom: 1;
    }

    HaltDialog Horizontal {
        width: 100%;
        align: center middle;
        height: auto;
    }

    HaltDialog Button {
        margin: 0 1;
    }
    """

    def __init__(self, iterations: int) -> None:
        super().__init__()
        self.iterations = iterations

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"Reached {self.iterations} iterations without APPROVED")
            yield Static("What would you like to do?")
            with Horizontal():
                yield Button("Continue (3 more)", id="continue", variant="primary")
                yield Button("Approve Now", id="approve", variant="success")
                yield Button("Stop", id="stop", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id)
