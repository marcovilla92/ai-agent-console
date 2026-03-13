"""
Projects router with context assembly and phase suggestion endpoints.

Exposes the assembler and phase suggestion logic from the context module
as REST endpoints for the SPA frontend.
"""
from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.context.assembler import assemble_full_context, suggest_next_phase
from src.db.pg_repository import ProjectRepository
from src.server.dependencies import get_pool, verify_credentials


# --- Pydantic response models ---


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
