"""
Task management REST endpoints.

Provides CRUD and cancel operations for tasks, protected by HTTP Basic Auth.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.engine.manager import TaskManager
from src.server.config import get_settings
from src.server.dependencies import get_task_manager, verify_credentials

task_router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
    dependencies=[Depends(verify_credentials)],
)


class TaskCreate(BaseModel):
    """Request body for creating a new task."""
    prompt: str
    mode: str = "autonomous"


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


class TaskListResponse(BaseModel):
    """Response model for listing tasks."""
    tasks: list[TaskResponse]
    count: int


@task_router.post("", status_code=status.HTTP_201_CREATED, response_model=TaskResponse)
async def create_task(
    body: TaskCreate,
    manager: TaskManager = Depends(get_task_manager),
):
    """Create and submit a new task."""
    settings = get_settings()
    task_id = await manager.submit(
        prompt=body.prompt,
        mode=body.mode,
        project_path=settings.project_path,
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
    )
