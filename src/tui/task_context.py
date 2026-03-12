"""
TUI adapter implementing TaskContext Protocol for the orchestrator.

Bridges the AgentConsoleApp to the orchestrator's expected interface.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.tui.streaming import stream_agent_to_panel
from src.tui.actions import AGENT_PANEL_MAP

if TYPE_CHECKING:
    from src.tui.app import AgentConsoleApp

log = logging.getLogger(__name__)


class TuiTaskContext:
    """Adapts AgentConsoleApp to satisfy the TaskContext Protocol."""

    def __init__(self, app: AgentConsoleApp) -> None:
        self._app = app
        log.info("TuiTaskContext created, project_path=%s", app.project_path)

    @property
    def project_path(self) -> str:
        return self._app.project_path

    async def update_status(
        self, agent: str, state: str, step: str, next_action: str
    ) -> None:
        log.info("update_status: agent=%s state=%s step=%s next=%s", agent, state, step, next_action)
        self._app.status_bar.set_status(
            agent=agent, state=state, step=step, next_action=next_action,
        )

    async def stream_output(
        self, agent_name: str, prompt: str, sections: dict
    ) -> dict[str, str]:
        log.info("stream_output: agent=%s prompt_len=%d", agent_name, len(prompt))
        panel_id = AGENT_PANEL_MAP[agent_name]
        panel = self._app.get_panel(panel_id)
        panel.clear_output()
        result = await stream_agent_to_panel(
            self._app, agent_name, prompt, panel,
        )
        log.info("stream_output complete: agent=%s sections=%s", agent_name, list(result.keys()))
        return result

    async def confirm_reroute(self, next_agent: str, reasoning: str) -> bool:
        log.info("confirm_reroute: next_agent=%s reasoning=%s", next_agent, reasoning)
        from src.tui.confirm_dialog import RerouteConfirmDialog

        confirmed = await self._app.push_screen_wait(
            RerouteConfirmDialog(next_agent, reasoning)
        )
        log.info("confirm_reroute result: %s", confirmed)
        return confirmed

    async def handle_halt(self, iteration_count: int) -> str:
        log.info("handle_halt: iteration_count=%d", iteration_count)
        from src.tui.confirm_dialog import HaltDialog

        result = await self._app.push_screen_wait(HaltDialog(iteration_count))
        log.info("handle_halt result: %s", result)
        return result
