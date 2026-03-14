"""
Projects router with CRUD and context/phase suggestion endpoints.

Exposes project listing, creation, deletion, plus the assembler and phase
suggestion logic from the context module as REST endpoints for the SPA frontend.
"""
from __future__ import annotations

from datetime import datetime

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.context.assembler import assemble_full_context, suggest_next_phase
from src.db.pg_repository import ProjectRepository
from src.pipeline.project_service import ProjectService
from src.server.dependencies import get_pool, verify_credentials


# --- Pydantic response models ---


class ProjectSummary(BaseModel):
    id: int
    name: str
    slug: str
    path: str
    description: str
    stack: str
    created_at: str | None
    last_used_at: str | None


class ProjectListResponse(BaseModel):
    projects: list[ProjectSummary]
    count: int


class ProjectCreateRequest(BaseModel):
    name: str
    description: str = ""
    template: str = "blank"


class ProjectCreateResponse(BaseModel):
    id: int
    name: str
    slug: str
    path: str
    description: str
    created_at: datetime


class RecentTaskResponse(BaseModel):
    id: int
    prompt: str
    status: str
    created_at: str


class ContextResponse(BaseModel):
    workspace: str
    claude_md: str
    planning_docs: dict[str, str]
    git_log: str
    recent_tasks: list[RecentTaskResponse]


class PhaseSuggestion(BaseModel):
    phase_id: str
    phase_name: str
    status: str
    reason: str


class PhaseSuggestionResponse(BaseModel):
    suggestion: PhaseSuggestion | None
    all_phases: list[dict]


# --- Router ---


project_router = APIRouter(
    prefix="/projects",
    tags=["projects"],
    dependencies=[Depends(verify_credentials)],
)


# --- Collection endpoints (MUST be before /{project_id}/ routes) ---


@project_router.get("", response_model=ProjectListResponse)
async def list_projects(pool: asyncpg.Pool = Depends(get_pool)):
    """Return all projects with stack detection and auto-registration."""
    svc = ProjectService(pool)
    projects = await svc.list_projects()
    return ProjectListResponse(projects=projects, count=len(projects))


@project_router.post("", response_model=ProjectCreateResponse, status_code=201)
async def create_project(
    req: ProjectCreateRequest,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Create a new project from a template with folder scaffolding and git init."""
    svc = ProjectService(pool)
    try:
        project = await svc.create_project(req.name, req.description, req.template)
    except FileExistsError:
        raise HTTPException(status_code=409, detail="Project folder already exists")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ProjectCreateResponse(
        id=project.id,
        name=project.name,
        slug=project.slug,
        path=project.path,
        description=project.description,
        created_at=project.created_at,
    )


@project_router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Delete a project record from the database (filesystem untouched)."""
    svc = ProjectService(pool)
    try:
        await svc.delete_project(project_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "deleted", "id": project_id}


# --- Per-project endpoints ---


@project_router.get("/{project_id}/context", response_model=ContextResponse)
async def get_project_context(
    project_id: int,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Return assembled context for a project."""
    repo = ProjectRepository(pool)
    project = await repo.get(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    context = await assemble_full_context(project.path, pool)
    return ContextResponse(**context)


@project_router.get(
    "/{project_id}/suggested-phase", response_model=PhaseSuggestionResponse
)
async def get_suggested_phase(
    project_id: int,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Return next phase suggestion for a project."""
    repo = ProjectRepository(pool)
    project = await repo.get(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    result = await suggest_next_phase(project.path)
    if result is None:
        return PhaseSuggestionResponse(suggestion=None, all_phases=[])
    return PhaseSuggestionResponse(
        suggestion=result["suggestion"],
        all_phases=result["all_phases"],
    )
