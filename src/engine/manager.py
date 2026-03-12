"""
TaskManager: Owns task lifecycle, concurrency control, and cancellation.

Uses asyncio.Semaphore to limit concurrent task execution (default: 2).
Each task runs in its own asyncio.Task, communicating status changes to
the database via TaskRepository.
"""
from __future__ import annotations

import asyncio
import logging
import signal
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import asyncpg

from src.db.pg_repository import TaskRepository
from src.db.pg_schema import Task
from src.engine.context import WebTaskContext
from src.pipeline.orchestrator import orchestrate_pipeline

log = logging.getLogger(__name__)


@dataclass
class RunningTask:
    """Tracks a running asyncio.Task and its associated context."""
    handle: asyncio.Task
    task_id: int
    ctx: WebTaskContext


class TaskManager:
    """Manages task submission, execution, concurrency, and cancellation.

    Args:
        pool: asyncpg connection pool for DB operations.
        max_concurrent: Maximum number of tasks that can run simultaneously.
    """

    def __init__(self, pool: asyncpg.Pool, max_concurrent: int = 2) -> None:
        self._pool = pool
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running: dict[int, RunningTask] = {}
        self._repo = TaskRepository(pool)

    async def submit(
        self,
        prompt: str,
        mode: str = "autonomous",
        project_path: str = ".",
    ) -> int:
        """Submit a new task for execution.

        Creates a DB row, starts an asyncio.Task for execution, and returns
        the task ID.
        """
        now = datetime.now(timezone.utc)
        task = Task(
            name=prompt[:50],
            project_path=project_path,
            created_at=now,
            status="queued",
            mode=mode,
            prompt=prompt,
        )
        task_id = await self._repo.create(task)

        handle = asyncio.create_task(
            self._execute(task_id, prompt, mode, project_path),
            name=f"task-{task_id}",
        )
        ctx = WebTaskContext(
            task_id=task_id,
            pool=self._pool,
            mode=mode,
            project_path=project_path,
        )
        self._running[task_id] = RunningTask(
            handle=handle, task_id=task_id, ctx=ctx,
        )
        return task_id

    async def _execute(
        self,
        task_id: int,
        prompt: str,
        mode: str,
        project_path: str,
    ) -> None:
        """Internal execution loop: acquire semaphore, run pipeline, update status."""
        try:
            async with self._semaphore:
                # Mark as running once semaphore acquired
                await self._repo.update_status(task_id, "running")

                ctx = WebTaskContext(
                    task_id=task_id,
                    pool=self._pool,
                    mode=mode,
                    project_path=project_path,
                )
                # Update the running task's ctx reference
                if task_id in self._running:
                    self._running[task_id].ctx = ctx

                await orchestrate_pipeline(ctx, prompt, self._pool, task_id)

                await self._repo.update_status(
                    task_id, "completed",
                    completed_at=datetime.now(timezone.utc),
                )
        except asyncio.CancelledError:
            await self._repo.update_status(
                task_id, "cancelled",
                completed_at=datetime.now(timezone.utc),
            )
            raise
        except Exception as exc:
            log.exception("Task %d failed", task_id)
            await self._repo.update_status(
                task_id, "failed",
                error=str(exc),
                completed_at=datetime.now(timezone.utc),
            )
        finally:
            self._running.pop(task_id, None)

    async def cancel(self, task_id: int) -> bool:
        """Cancel a running task.

        Cancels the asyncio.Task and terminates any subprocess via SIGTERM,
        falling back to SIGKILL after 5 seconds.

        Returns True if the task was found and cancelled, False otherwise.
        """
        running = self._running.get(task_id)
        if running is None:
            return False

        # Terminate subprocess if one exists
        proc = running.ctx.proc
        if proc is not None:
            try:
                proc.send_signal(signal.SIGTERM)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    proc.kill()
            except ProcessLookupError:
                pass  # Already dead

        # Cancel the asyncio.Task
        running.handle.cancel()
        try:
            await running.handle
        except (asyncio.CancelledError, Exception):
            pass

        return True

    async def get(self, task_id: int) -> Optional[Task]:
        """Get a task by ID from the database."""
        return await self._repo.get(task_id)

    async def list_all(self) -> list[Task]:
        """List all tasks from the database."""
        return await self._repo.list_all()

    async def shutdown(self) -> None:
        """Cancel all running tasks for clean server shutdown."""
        task_ids = list(self._running.keys())
        for task_id in task_ids:
            await self.cancel(task_id)
