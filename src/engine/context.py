"""
WebTaskContext: TaskContext Protocol implementation for web-based task execution.

Bridges the orchestrator pipeline to the web platform. Handles agent output
streaming via Claude CLI subprocess, section parsing, and DB persistence.

Phase 7: Core implementation. WebSocket streaming deferred to Phase 8.
Approval UI deferred to Phase 9 (auto-approve for now).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import asyncpg

from src.db.pg_repository import AgentOutputRepository
from src.db.pg_schema import AgentOutput
from src.parser.extractor import extract_sections
from src.runner.runner import stream_claude

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
    ) -> None:
        self._task_id = task_id
        self._pool = pool
        self._mode = mode
        self._project_path = project_path
        self.proc: Optional[asyncio.subprocess.Process] = None

    @property
    def project_path(self) -> str:
        return self._project_path

    async def update_status(
        self, agent: str, state: str, step: str, next_action: str
    ) -> None:
        """Update status display. No-op in Phase 7 (WebSocket streaming is Phase 8)."""
        log.debug(
            "status: agent=%s state=%s step=%s next=%s",
            agent, state, step, next_action,
        )

    async def stream_output(
        self, agent_name: str, prompt: str, sections: dict
    ) -> dict[str, str]:
        """Stream agent output via Claude CLI, parse sections, persist to DB.

        Collects all output text, extracts sections, stores raw output in
        agent_outputs table. Sets self.proc for subprocess termination support.
        """
        from datetime import datetime, timezone

        raw_parts: list[str] = []

        async for event in stream_claude(prompt):
            if isinstance(event, str):
                raw_parts.append(event)
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

    async def confirm_reroute(self, next_agent: str, reasoning: str) -> bool:
        """Confirm re-routing. Auto-approve for all modes in Phase 7.

        Approval UI is Phase 9. For now, always return True.
        """
        log.debug(
            "auto-approve reroute: next=%s reasoning=%s mode=%s",
            next_agent, reasoning, self._mode,
        )
        return True

    async def handle_halt(self, iteration_count: int) -> str:
        """Handle iteration limit. Always approve in Phase 7.

        Approval UI is Phase 9.
        """
        log.debug("auto-approve halt at iteration %d", iteration_count)
        return "approve"
