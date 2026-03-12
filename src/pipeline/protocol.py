"""
TaskContext Protocol for decoupling the orchestrator from the TUI.

Enables the orchestrator to serve both TUI (v1.0) and web (v2.0) frontends
via structural subtyping. Any class implementing these methods satisfies the
Protocol without explicit inheritance.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class TaskContext(Protocol):
    """Protocol defining what the orchestrator needs from its UI layer."""

    @property
    def project_path(self) -> str:
        """Path to the project being worked on."""
        ...

    async def update_status(
        self, agent: str, state: str, step: str, next_action: str
    ) -> None:
        """Update the status display (status bar, progress indicator, etc.)."""
        ...

    async def stream_output(
        self, agent_name: str, prompt: str, sections: dict
    ) -> dict[str, str]:
        """Stream agent output to the UI and return collected sections."""
        ...

    async def confirm_reroute(self, next_agent: str, reasoning: str) -> bool:
        """Ask user to confirm re-routing to a different agent."""
        ...

    async def handle_halt(self, iteration_count: int) -> str:
        """Handle iteration limit reached. Returns 'continue', 'approve', or 'stop'."""
        ...
