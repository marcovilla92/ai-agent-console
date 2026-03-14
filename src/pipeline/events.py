"""
Project event system stub.

Defines the ProjectEvent enum and an emit_event no-op that logs at DEBUG level.
Future phases will wire this to WebSocket broadcast or n8n webhooks.
"""
import logging
from enum import Enum

log = logging.getLogger(__name__)


class ProjectEvent(str, Enum):
    """Lifecycle events emitted during project and task operations."""

    PROJECT_CREATED = "project.created"
    PROJECT_DELETED = "project.deleted"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    PHASE_SUGGESTED = "phase.suggested"


async def emit_event(event: ProjectEvent, payload: dict) -> None:
    """Emit a project lifecycle event (no-op stub, logs at DEBUG)."""
    log.debug("Event %s: %s", event.value, payload)
