"""
Project event system.

Defines the ProjectEvent enum and an emit_event function that logs at DEBUG
level and, for terminal task events, sends a webhook notification to n8n
which forwards to WhatsApp via Evolution API.
"""
import logging
import os
from enum import Enum

import httpx

log = logging.getLogger(__name__)

_WEBHOOK_URL = os.getenv(
    "N8N_TASK_WEBHOOK_URL",
    "https://amcsystem.uk/webhook/task-notification",
)

_STATUS_EMOJI = {
    "completed": "\u2705",
    "failed": "\u274c",
    "cancelled": "\u26d4",
}


class ProjectEvent(str, Enum):
    """Lifecycle events emitted during project and task operations."""

    PROJECT_CREATED = "project.created"
    PROJECT_DELETED = "project.deleted"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"
    PHASE_SUGGESTED = "phase.suggested"


_TERMINAL_EVENTS = {
    ProjectEvent.TASK_COMPLETED,
    ProjectEvent.TASK_FAILED,
    ProjectEvent.TASK_CANCELLED,
}


async def emit_event(event: ProjectEvent, payload: dict) -> None:
    """Emit a project lifecycle event.

    For terminal task events (completed, failed, cancelled) sends a webhook
    POST to n8n which forwards the notification to WhatsApp.
    """
    log.debug("Event %s: %s", event.value, payload)
    if event in _TERMINAL_EVENTS:
        await _notify_webhook(event, payload)


async def _notify_webhook(event: ProjectEvent, payload: dict) -> None:
    """Fire-and-forget POST to the n8n task-notification webhook."""
    status = event.value.split(".")[-1]  # "completed" / "failed" / "cancelled"
    body = {
        "task_id": payload.get("task_id"),
        "status": status,
        "name": payload.get("name", ""),
        "error": payload.get("error", ""),
        "emoji": _STATUS_EMOJI.get(status, ""),
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(_WEBHOOK_URL, json=body)
            resp.raise_for_status()
            log.info("Webhook notification sent for task %s (%s)", payload.get("task_id"), status)
    except Exception:
        log.exception("Failed to send webhook notification for task %s", payload.get("task_id"))
