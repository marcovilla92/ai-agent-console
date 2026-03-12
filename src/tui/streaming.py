"""
Streaming worker for piping agent output into TUI panels in real-time.

Uses Textual's worker system to run async agent invocation
in the background while updating the output panel line-by-line.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from textual.worker import Worker, WorkerState

from src.agents.config import get_agent_config
from src.context.assembler import assemble_workspace_context
from src.db.repository import AgentOutputRepository
from src.db.schema import AgentOutput
from src.parser.extractor import extract_sections
from src.runner.runner import stream_claude
from src.tui.actions import AGENT_PANEL_MAP, complete_agent_run

if TYPE_CHECKING:
    from src.tui.app import AgentConsoleApp
    from src.tui.panels import OutputPanel

import aiosqlite


async def stream_agent_to_panel(
    app: AgentConsoleApp,
    agent_name: str,
    prompt: str,
    panel: OutputPanel,
    db: aiosqlite.Connection | None = None,
    session_id: int | None = None,
) -> dict[str, str]:
    """
    Stream Claude CLI output for an agent directly into a TUI panel.

    Returns the parsed sections dict when complete.
    """
    config = get_agent_config(agent_name)

    # Build full prompt with workspace context
    context = assemble_workspace_context(app.project_path)
    full_prompt = f"{context}\n{prompt}"

    # Stream output line by line into the panel
    chunks: list[str] = []
    async for chunk in stream_claude(
        full_prompt,
        system_prompt_file=config.system_prompt_file,
    ):
        chunks.append(chunk)
        # Write each chunk to the panel for real-time display
        panel.write(chunk)

    raw_output = "".join(chunks)
    sections = extract_sections(raw_output)

    # Persist to DB if connection available
    if db is not None and session_id is not None:
        repo = AgentOutputRepository(db)
        await repo.create(AgentOutput(
            session_id=session_id,
            agent_type=agent_name,
            raw_output=raw_output,
            created_at=datetime.now(timezone.utc).isoformat(),
        ))

    return sections


def start_agent_worker(
    app: AgentConsoleApp,
    agent_name: str,
    prompt: str,
    db: aiosqlite.Connection | None = None,
    session_id: int | None = None,
) -> Worker:
    """
    Launch an agent as a Textual background worker.

    The worker streams output into the corresponding panel and
    updates the status bar on completion.
    """
    panel_id = AGENT_PANEL_MAP[agent_name]
    panel = app.get_panel(panel_id)

    async def _run_agent() -> dict[str, str]:
        app.status_bar.set_status(
            agent=agent_name,
            state="streaming",
            step="receiving output",
            next_action="Streaming...",
        )
        sections = await stream_agent_to_panel(
            app, agent_name, prompt, panel, db, session_id,
        )
        complete_agent_run(app, agent_name, success=True)
        return sections

    return app.run_worker(_run_agent, exclusive=True)


def start_orchestrator_worker(
    app: AgentConsoleApp,
    prompt: str,
    db: aiosqlite.Connection | None = None,
    session_id: int | None = None,
) -> Worker:
    """
    Launch the orchestrator pipeline as a Textual background worker.

    Runs orchestrate_pipeline which handles the full agent routing loop
    including re-route confirmations and halt dialogs.
    """

    async def _run_orchestrator() -> None:
        # Local import to avoid circular dependency
        from src.pipeline.orchestrator import orchestrate_pipeline

        app.status_bar.set_status(
            agent="orchestrator",
            state="starting",
            step="initializing pipeline",
            next_action="Starting orchestrator...",
        )

        try:
            state = await orchestrate_pipeline(app, prompt, db, session_id)

            if state.approved:
                app.status_bar.set_status(
                    agent="orchestrator",
                    state="complete",
                    step="pipeline approved",
                    next_action="Pipeline complete",
                )
            elif state.halted:
                app.status_bar.set_status(
                    agent="orchestrator",
                    state="halted",
                    step="pipeline halted by user",
                    next_action="Enter a new prompt",
                )
        except Exception as exc:
            app.status_bar.set_status(
                agent="orchestrator",
                state="error",
                step=str(exc)[:80],
                next_action="Fix and retry Ctrl+S",
            )

    return app.run_worker(_run_orchestrator, exclusive=True)
