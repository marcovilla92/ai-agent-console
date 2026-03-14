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
from src.pipeline.events import ProjectEvent, emit_event
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

    def __init__(
        self, pool: asyncpg.Pool, max_concurrent: int = 2, connection_manager=None
    ) -> None:
        self._pool = pool
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running: dict[int, RunningTask] = {}
        self._repo = TaskRepository(pool)
        self._connection_manager = connection_manager
        self._shutting_down = False

    async def submit(
        self,
        prompt: str,
        mode: str = "autonomous",
        project_path: str = ".",
        project_id: Optional[int] = None,
        enriched_prompt: Optional[str] = None,
    ) -> int:
        """Submit a new task for execution.

        Creates a DB row, starts an asyncio.Task for execution, and returns
        the task ID.

        Args:
            prompt: Original user prompt (stored in DB).
            enriched_prompt: Context-enriched prompt for pipeline (transient).
            project_id: Optional project FK for task-project linking.
        """
        now = datetime.now(timezone.utc)
        task = Task(
            name=prompt[:50],
            project_path=project_path,
            created_at=now,
            status="queued",
            mode=mode,
            prompt=prompt,
            project_id=project_id,
        )
        task_id = await self._repo.create(task)

        # Use enriched prompt for pipeline if provided, else original
        pipeline_prompt = enriched_prompt if enriched_prompt is not None else prompt
        handle = asyncio.create_task(
            self._execute(task_id, pipeline_prompt, mode, project_path),
            name=f"task-{task_id}",
        )
        ctx = WebTaskContext(
            task_id=task_id,
            pool=self._pool,
            mode=mode,
            project_path=project_path,
            connection_manager=self._connection_manager,
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
                await emit_event(ProjectEvent.TASK_STARTED, {"task_id": task_id})

                ctx = WebTaskContext(
                    task_id=task_id,
                    pool=self._pool,
                    mode=mode,
                    project_path=project_path,
                    connection_manager=self._connection_manager,
                )
                # Update the running task's ctx reference
                if task_id in self._running:
                    self._running[task_id].ctx = ctx

                await orchestrate_pipeline(ctx, prompt, self._pool, task_id)

                await self._repo.update_status(
                    task_id, "completed",
                    completed_at=datetime.now(timezone.utc),
                )
                await emit_event(ProjectEvent.TASK_COMPLETED, {"task_id": task_id, "name": prompt[:80]})
                if self._connection_manager:
                    await self._connection_manager.send_status(task_id, "completed")
        except asyncio.CancelledError:
            if self._shutting_down:
                # Server shutdown — mark as interrupted for resume on restart
                await self._repo.update_status(task_id, "interrupted")
                log.info("Task %d interrupted by server shutdown (will resume)", task_id)
                if self._connection_manager:
                    await self._connection_manager.send_status(task_id, "interrupted")
            else:
                # User-initiated cancellation
                await self._repo.update_status(
                    task_id, "cancelled",
                    completed_at=datetime.now(timezone.utc),
                )
                await emit_event(ProjectEvent.TASK_CANCELLED, {"task_id": task_id, "name": prompt[:80]})
                if self._connection_manager:
                    await self._connection_manager.send_status(task_id, "cancelled")
            raise
        except Exception as exc:
            log.exception("Task %d failed", task_id)
            await self._repo.update_status(
                task_id, "failed",
                error=str(exc),
                completed_at=datetime.now(timezone.utc),
            )
            await emit_event(ProjectEvent.TASK_FAILED, {"task_id": task_id, "name": prompt[:80], "error": str(exc)})
            if self._connection_manager:
                await self._connection_manager.send_status(task_id, "failed")
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

    async def approve(self, task_id: int, decision: str) -> bool:
        """Relay an approval decision to a running task's context.

        Returns True if the task was found and was awaiting approval.
        Returns False if the task is not running or not awaiting approval.
        """
        running = self._running.get(task_id)
        if running is None:
            return False

        ctx = running.ctx
        if ctx._approval_event is None or ctx._approval_event.is_set():
            return False

        ctx.set_approval(decision)
        return True

    async def get(self, task_id: int) -> Optional[Task]:
        """Get a task by ID from the database."""
        return await self._repo.get(task_id)

    async def list_all(self) -> list[Task]:
        """List all tasks from the database."""
        return await self._repo.list_all()

    async def resume_interrupted(self) -> list[int]:
        """Resume tasks left in 'interrupted' or 'running' status from a previous server session.

        Called during startup to pick up work that was cut short by a restart.
        Returns the list of task IDs that were re-submitted.
        """
        resumed: list[int] = []
        rows = await self._pool.fetch(
            "SELECT id, prompt, mode, project_path, project_id "
            "FROM tasks WHERE status IN ('interrupted', 'running') "
            "ORDER BY id"
        )
        for row in rows:
            task_id = row["id"]
            log.info("Resuming interrupted task %d: %s", task_id, row["prompt"][:80])

            # Re-enrich prompt with project context if project_id exists
            pipeline_prompt = row["prompt"]
            if row["project_id"]:
                try:
                    from src.context.assembler import assemble_full_context
                    from src.db.pg_repository import ProjectRepository

                    project_repo = ProjectRepository(self._pool)
                    project = await project_repo.get(row["project_id"])
                    if project:
                        ctx_data = await assemble_full_context(project.path, self._pool)
                        parts = []
                        for key in ("workspace", "claude_md", "git_log"):
                            if ctx_data.get(key):
                                parts.append(f"=== {key.upper()} ===\n{ctx_data[key]}")
                        for doc_name, doc_content in ctx_data.get("planning_docs", {}).items():
                            if doc_content:
                                parts.append(f"=== {doc_name} ===\n{doc_content}")
                        if parts:
                            prefix = "\n\n".join(parts) + "\n\n"
                            pipeline_prompt = prefix + row["prompt"]
                except Exception:
                    log.exception("Failed to re-enrich prompt for task %d, using original", task_id)

            # Mark as running and re-submit
            await self._repo.update_status(task_id, "running")

            handle = asyncio.create_task(
                self._execute(task_id, pipeline_prompt, row["mode"], row["project_path"]),
                name=f"task-{task_id}-resume",
            )
            ctx = WebTaskContext(
                task_id=task_id,
                pool=self._pool,
                mode=row["mode"],
                project_path=row["project_path"],
                connection_manager=self._connection_manager,
            )
            self._running[task_id] = RunningTask(
                handle=handle, task_id=task_id, ctx=ctx,
            )
            resumed.append(task_id)

        if resumed:
            log.info("Resumed %d interrupted tasks: %s", len(resumed), resumed)
        return resumed

    async def shutdown(self) -> None:
        """Gracefully interrupt all running tasks for server shutdown.

        Marks tasks as 'interrupted' (not 'cancelled') so they can be
        resumed on the next server startup.
        """
        self._shutting_down = True
        task_ids = list(self._running.keys())
        for task_id in task_ids:
            log.info("Interrupting task %d for shutdown", task_id)
            running = self._running.get(task_id)
            if running is None:
                continue

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
                    pass

            # Cancel the asyncio.Task — the CancelledError handler will
            # check self._shutting_down to decide status
            running.handle.cancel()
            try:
                await running.handle
            except (asyncio.CancelledError, Exception):
                pass
        self._running.clear()
