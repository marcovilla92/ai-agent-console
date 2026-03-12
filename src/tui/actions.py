"""
Action handlers that bridge TUI events to the pipeline.

These functions coordinate between user input, agent execution,
and panel output display.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.tui.app import AgentConsoleApp


AGENT_PANEL_MAP = {
    "plan": "plan-panel",
    "execute": "execute-panel",
    "review": "review-panel",
}


def get_prompt_text(app: AgentConsoleApp) -> str | None:
    """Extract and validate prompt text from the prompt panel."""
    text = app.prompt_panel.text.strip()
    if not text:
        app.notify("Enter a prompt first", severity="warning")
        return None
    return text


def prepare_agent_run(app: AgentConsoleApp, agent_name: str) -> str | None:
    """
    Prepare to run an agent: validate prompt, update status bar,
    clear the target panel. Returns prompt text or None if invalid.
    """
    prompt = get_prompt_text(app)
    if prompt is None:
        return None

    panel_id = AGENT_PANEL_MAP.get(agent_name)
    if panel_id:
        app.get_panel(panel_id).clear_output()

    app.status_bar.set_status(
        agent=agent_name,
        state="running",
        step="invoking Claude CLI",
        next_action=f"Waiting for {agent_name} output...",
    )

    return prompt


def send_prompt(app: AgentConsoleApp) -> str | None:
    """
    Handle Ctrl+S: validate prompt and kick off the orchestrator pipeline.

    Clears all output panels and launches the AI-driven orchestrator
    which routes agents through iterative cycles.
    Returns the prompt text or None if empty.
    """
    prompt = get_prompt_text(app)
    if prompt is None:
        return None

    # Clear all output panels before starting
    for panel_id in AGENT_PANEL_MAP.values():
        app.get_panel(panel_id).clear_output()

    app.status_bar.set_status(
        agent="orchestrator",
        state="starting",
        step="preparing pipeline",
        next_action="Starting orchestrator...",
    )

    # Local import to avoid circular dependency (streaming imports from actions)
    from src.tui.streaming import start_orchestrator_worker
    start_orchestrator_worker(app, prompt)

    return prompt


def complete_agent_run(app: AgentConsoleApp, agent_name: str, success: bool = True) -> None:
    """Update status after an agent completes."""
    if success:
        next_agents = {"plan": "execute", "execute": "review", "review": None}
        next_agent = next_agents.get(agent_name)
        next_action = f"Press Ctrl+{'E' if next_agent == 'execute' else 'R'} for {next_agent}" if next_agent else "Pipeline complete"

        app.status_bar.set_status(
            agent=agent_name,
            state="complete",
            step="done",
            next_action=next_action,
        )
    else:
        app.status_bar.set_status(
            agent=agent_name,
            state="error",
            step="failed",
            next_action=f"Fix and retry Ctrl+{'P' if agent_name == 'plan' else 'E' if agent_name == 'execute' else 'R'}",
        )
