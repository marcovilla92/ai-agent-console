"""
WebTaskContext: TaskContext Protocol implementation for web-based task execution.

Bridges the orchestrator pipeline to the web platform. Handles agent output
streaming via Claude CLI subprocess, section parsing, and DB persistence.
Broadcasts output chunks via ConnectionManager for WebSocket streaming.

In supervised mode, confirm_reroute and handle_halt pause execution via
asyncio.Event and broadcast approval_required events over WebSocket. The user
approves or rejects via the REST API, which calls set_approval() to resume.
In autonomous mode, these methods auto-approve immediately.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

import asyncpg

from src.db.pg_repository import AgentOutputRepository
from src.db.pg_schema import AgentOutput
from src.parser.extractor import extract_sections
from src.agents.config import get_agent_config
from src.runner.runner import stream_claude

if TYPE_CHECKING:
    from src.server.connection_manager import ConnectionManager

log = logging.getLogger(__name__)


class WebTaskContext:
    """TaskContext implementation for the web execution engine.

    Satisfies the TaskContext Protocol from src/pipeline/protocol.py via
    structural subtyping (duck typing).
    """

    def __init__(
        self,
        task_id: int,
        pool: asyncpg.Pool,
        mode: str,
        project_path: str = ".",
        connection_manager: Optional[ConnectionManager] = None,
    ) -> None:
        self._task_id = task_id
        self._pool = pool
        self._mode = mode
        self._project_path = project_path
        self._connection_manager = connection_manager
        self.proc: Optional[asyncio.subprocess.Process] = None
        self._approval_event: Optional[asyncio.Event] = None
        self._approval_decision: Optional[str] = None

    @property
    def project_path(self) -> str:
        return self._project_path

    @property
    def mode(self) -> str:
        return self._mode

    async def update_status(
        self, agent: str, state: str, step: str, next_action: str
    ) -> None:
        """Update status display. Broadcasts via ConnectionManager if available."""
        log.debug(
            "status: agent=%s state=%s step=%s next=%s",
            agent, state, step, next_action,
        )
        if self._connection_manager:
            await self._connection_manager.send_status(
                self._task_id, f"{agent}:{state}:{step}"
            )

    async def stream_output(
        self, agent_name: str, prompt: str, sections: dict
    ) -> dict[str, str]:
        """Stream agent output via Claude CLI, parse sections, persist to DB.

        Collects all output text, extracts sections, stores raw output in
        agent_outputs table. Sets self.proc for subprocess termination support.
        """
        from datetime import datetime, timezone

        system_prompt = None
        try:
            config = get_agent_config(agent_name)
            system_prompt = config.system_prompt_file
            log.info("stream_output: agent=%s system_prompt=%s", agent_name, system_prompt)
        except KeyError:
            log.warning("stream_output: no config for agent %r, running without system prompt", agent_name)

        raw_parts: list[str] = []

        def _capture_proc(p):
            self.proc = p

        async for event in stream_claude(prompt, system_prompt_file=system_prompt, on_process=_capture_proc):
            if isinstance(event, str):
                raw_parts.append(event)
                if self._connection_manager:
                    await self._connection_manager.send_chunk(self._task_id, event)
            elif isinstance(event, dict):
                # result event -- extract text if present
                if "result" in event:
                    raw_parts.append(str(event["result"]))

        raw_output = "".join(raw_parts)
        parsed_sections = extract_sections(raw_output)

        # Persist to DB
        try:
            repo = AgentOutputRepository(self._pool)
            output = AgentOutput(
                session_id=self._task_id,
                agent_type=agent_name,
                raw_output=raw_output,
                created_at=datetime.now(timezone.utc),
            )
            await repo.create(output)
        except Exception:
            log.exception("Failed to persist agent output for task %d", self._task_id)

        return parsed_sections

    def set_approval(self, decision: str) -> None:
        """Set the approval decision and unblock the waiting gate.

        Called by TaskManager.approve() when the user submits a decision
        via the REST API.
        """
        self._approval_decision = decision
        if self._approval_event is not None:
            self._approval_event.set()

    async def _wait_for_approval(self, action: str, context: dict) -> str:
        """Pause execution and wait for user approval via asyncio.Event.

        Broadcasts approval_required WS event, updates task status to
        awaiting_approval, and blocks until set_approval() is called.
        Returns the decision string.
        """
        from src.db.pg_repository import TaskRepository

        self._approval_event = asyncio.Event()
        self._approval_decision = None

        # Update DB status and broadcast
        repo = TaskRepository(self._pool)
        await repo.update_status(self._task_id, "awaiting_approval")
        if self._connection_manager:
            await self._connection_manager.send_approval_required(
                self._task_id, action, context,
            )
            await self._connection_manager.send_status(
                self._task_id, "awaiting_approval",
            )

        log.info(
            "Task %d awaiting approval: action=%s context=%s",
            self._task_id, action, context,
        )

        # Block until approved/rejected
        await self._approval_event.wait()

        decision = self._approval_decision or "reject"

        # Restore running status
        await repo.update_status(self._task_id, "running")
        if self._connection_manager:
            await self._connection_manager.send_status(self._task_id, "running")

        # Clean up gate state
        self._approval_event = None
        self._approval_decision = None

        return decision

    async def confirm_reroute(self, next_agent: str, reasoning: str) -> bool:
        """Confirm agent re-routing.

        In autonomous mode, auto-approves immediately.
        In supervised mode, pauses execution and waits for user approval.
        """
        if self._mode != "supervised":
            log.debug(
                "auto-approve reroute: next=%s reasoning=%s mode=%s",
                next_agent, reasoning, self._mode,
            )
            return True

        decision = await self._wait_for_approval(
            "reroute",
            {"next_agent": next_agent, "reasoning": reasoning},
        )
        return decision == "approve"

    async def handle_halt(self, iteration_count: int) -> str:
        """Handle iteration limit decision.

        In autonomous mode, auto-approves immediately.
        In supervised mode, pauses execution and waits for user decision.
        Returns the decision string: "approve", "reject", or "continue".
        """
        if self._mode != "supervised":
            log.debug("auto-approve halt at iteration %d", iteration_count)
            return "approve"

        return await self._wait_for_approval(
            "halt",
            {"iteration_count": iteration_count},
        )
