"""
Task management REST endpoints.

Provides CRUD and cancel operations for tasks, protected by HTTP Basic Auth.
"""
import logging
from datetime import datetime
from typing import Literal, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.context.assembler import MAX_CONTEXT_CHARS, assemble_full_context
from src.db.pg_repository import AgentOutputRepository, ProjectRepository
from src.engine.manager import TaskManager
from src.server.config import get_settings
from src.server.dependencies import get_pool, get_task_manager, verify_credentials

log = logging.getLogger(__name__)

task_router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
    dependencies=[Depends(verify_credentials)],
)


class TaskCreate(BaseModel):
    """Request body for creating a new task."""
    prompt: str
    mode: str = "autonomous"
    project_id: Optional[int] = None


class TaskResponse(BaseModel):
    """Response model for a single task."""
    id: Optional[int] = None
    name: str
    project_path: str
    status: str
    mode: str
    prompt: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    project_id: Optional[int] = None


class TaskListResponse(BaseModel):
    """Response model for listing tasks."""
    tasks: list[TaskResponse]
    count: int


class ApprovalRequest(BaseModel):
    """Request body for approving or rejecting a task decision point."""
    decision: Literal["approve", "reject", "continue"]


class ApprovalResponse(BaseModel):
    """Response for approval endpoint."""
    status: str
    decision: str


class AgentOutputResponse(BaseModel):
    """Response model for a single agent output record."""
    id: Optional[int] = None
    agent_type: str
    raw_output: str
    created_at: datetime


class AgentOutputListResponse(BaseModel):
    """Response model for listing agent outputs."""
    outputs: list[AgentOutputResponse]
    count: int


def format_context_prefix(ctx: dict) -> str:
    """Format assembled context dict into a readable string prefix for prompts.

    Sections: workspace, CLAUDE.md, planning docs, git log, recent tasks.
    Truncated to MAX_CONTEXT_CHARS.
    """
    parts: list[str] = []

    if ctx.get("workspace"):
        parts.append(f"=== WORKSPACE ===\n{ctx['workspace']}")

    if ctx.get("claude_md"):
        parts.append(f"=== CLAUDE.md ===\n{ctx['claude_md']}")

    planning = ctx.get("planning_docs", {})
    if planning:
        for doc_name, content in planning.items():
            parts.append(f"=== {doc_name} ===\n{content}")

    if ctx.get("git_log"):
        parts.append(f"=== GIT LOG ===\n{ctx['git_log']}")

    if ctx.get("recent_tasks"):
        task_lines = []
        for t in ctx["recent_tasks"]:
            task_lines.append(f"  - [{t.get('status', '?')}] {t.get('prompt', '')}")
        parts.append(f"=== RECENT TASKS ===\n" + "\n".join(task_lines))

    prefix = "\n\n".join(parts)
    if len(prefix) > MAX_CONTEXT_CHARS:
        prefix = prefix[:MAX_CONTEXT_CHARS] + "\n...[truncated]"

    return prefix + "\n\n" if prefix else ""


@task_router.post("", status_code=status.HTTP_201_CREATED, response_model=TaskResponse)
async def create_task(
    body: TaskCreate,
    manager: TaskManager = Depends(get_task_manager),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Create and submit a new task.

    When project_id is provided: validates the project exists, assembles
    project context and prepends it to the prompt for the pipeline,
    updates the project's last_used_at, and links the task to the project.
    """
    settings = get_settings()
    project_path = settings.project_path
    enriched_prompt: str | None = None

    if body.project_id is not None:
        # Validate project exists
        project_repo = ProjectRepository(pool)
        project = await project_repo.get(body.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        # Use project's path for task
        project_path = project.path

        # Assemble context -- failure must not block task creation
        try:
            ctx = await assemble_full_context(project.path, pool)
            prefix = format_context_prefix(ctx)
            if prefix:
                enriched_prompt = prefix + body.prompt
        except Exception:
            log.warning(
                "Context assembly failed for project %d, using original prompt",
                body.project_id,
                exc_info=True,
            )

        # Update last_used_at
        await project_repo.update_last_used(body.project_id)

    task_id = await manager.submit(
        prompt=body.prompt,
        mode=body.mode,
        project_path=project_path,
        project_id=body.project_id,
        enriched_prompt=enriched_prompt,
    )
    task = await manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=500, detail="Task creation failed")
    return TaskResponse(
        id=task.id,
        name=task.name,
        project_path=task.project_path,
        status=task.status,
        mode=task.mode,
        prompt=task.prompt,
        created_at=task.created_at,
        completed_at=task.completed_at,
        error=task.error,
        project_id=task.project_id,
    )


@task_router.get("", response_model=TaskListResponse)
async def list_tasks(
    manager: TaskManager = Depends(get_task_manager),
):
    """List all tasks."""
    tasks = await manager.list_all()
    return TaskListResponse(
        tasks=[
            TaskResponse(
                id=t.id,
                name=t.name,
                project_path=t.project_path,
                status=t.status,
                mode=t.mode,
                prompt=t.prompt,
                created_at=t.created_at,
                completed_at=t.completed_at,
                error=t.error,
                project_id=t.project_id,
            )
            for t in tasks
        ],
        count=len(tasks),
    )


@task_router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    manager: TaskManager = Depends(get_task_manager),
):
    """Get a single task by ID."""
    task = await manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(
        id=task.id,
        name=task.name,
        project_path=task.project_path,
        status=task.status,
        mode=task.mode,
        prompt=task.prompt,
        created_at=task.created_at,
        completed_at=task.completed_at,
        error=task.error,
        project_id=task.project_id,
    )


@task_router.get("/{task_id}/outputs", response_model=AgentOutputListResponse)
async def get_task_outputs(
    task_id: int,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Get agent output history for a task."""
    repo = AgentOutputRepository(pool)
    outputs = await repo.get_by_session(task_id)
    return AgentOutputListResponse(
        outputs=[
            AgentOutputResponse(
                id=o.id,
                agent_type=o.agent_type,
                raw_output=o.raw_output,
                created_at=o.created_at,
            )
            for o in outputs
        ],
        count=len(outputs),
    )


@task_router.post("/{task_id}/approve", response_model=ApprovalResponse)
async def approve_task(
    task_id: int,
    body: ApprovalRequest,
    manager: TaskManager = Depends(get_task_manager),
):
    """Approve or reject a task awaiting approval.

    Returns 404 if task does not exist, 409 if task exists but is not
    awaiting approval, 200 with decision on success.
    """
    # Check if task exists at all
    task = await manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Try to relay the approval
    relayed = await manager.approve(task_id, body.decision)
    if not relayed:
        raise HTTPException(
            status_code=409,
            detail="Task not awaiting approval",
        )

    return ApprovalResponse(status="ok", decision=body.decision)


@task_router.post("/{task_id}/retry", response_model=TaskResponse)
async def retry_task(
    task_id: int,
    manager: TaskManager = Depends(get_task_manager),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Retry an interrupted, cancelled, or failed task.

    Re-submits the original prompt to the pipeline with fresh context.
    """
    task = await manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in ("interrupted", "cancelled", "failed"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot retry task with status '{task.status}'",
        )

    # Re-enrich prompt if project-linked
    enriched_prompt: str | None = None
    project_path = task.project_path
    if task.project_id:
        try:
            project_repo = ProjectRepository(pool)
            project = await project_repo.get(task.project_id)
            if project:
                project_path = project.path
                ctx = await assemble_full_context(project.path, pool)
                prefix = format_context_prefix(ctx)
                if prefix:
                    enriched_prompt = prefix + task.prompt
                await project_repo.update_last_used(task.project_id)
        except Exception:
            log.warning("Context assembly failed for retry of task %d", task_id, exc_info=True)

    new_task_id = await manager.submit(
        prompt=task.prompt,
        mode=task.mode,
        project_path=project_path,
        project_id=task.project_id,
        enriched_prompt=enriched_prompt,
    )
    new_task = await manager.get(new_task_id)
    if new_task is None:
        raise HTTPException(status_code=500, detail="Task retry failed")
    return TaskResponse(
        id=new_task.id,
        name=new_task.name,
        project_path=new_task.project_path,
        status=new_task.status,
        mode=new_task.mode,
        prompt=new_task.prompt,
        created_at=new_task.created_at,
        completed_at=new_task.completed_at,
        error=new_task.error,
        project_id=new_task.project_id,
    )


@task_router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    task_id: int,
    manager: TaskManager = Depends(get_task_manager),
):
    """Cancel a running task."""
    cancelled = await manager.cancel(task_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Task not found or not running")
    task = await manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(
        id=task.id,
        name=task.name,
        project_path=task.project_path,
        status=task.status,
        mode=task.mode,
        prompt=task.prompt,
        created_at=task.created_at,
        completed_at=task.completed_at,
        error=task.error,
        project_id=task.project_id,
    )
