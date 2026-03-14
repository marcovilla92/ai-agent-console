"""
Projects router with CRUD, context/phase suggestion, and file browsing endpoints.

Exposes project listing, creation, deletion, plus the assembler and phase
suggestion logic from the context module as REST endpoints for the SPA frontend.
"""
from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
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


@project_router.get("/{project_id}")
async def get_project(
    project_id: int,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Return a single project by ID."""
    repo = ProjectRepository(pool)
    project = await repo.get(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    from src.context.assembler import detect_stack

    return ProjectSummary(
        id=project.id,
        name=project.name,
        slug=project.slug,
        path=project.path,
        description=project.description,
        stack=detect_stack(project.path),
        created_at=project.created_at.isoformat() if project.created_at else None,
        last_used_at=project.last_used_at.isoformat() if project.last_used_at else None,
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


# --- File browsing endpoints ---

# Directories to skip when listing project files
_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", ".tox", ".mypy_cache",
    ".pytest_cache", "coverage", ".eggs", "*.egg-info",
}

# Max file size we'll serve as text (512 KB)
_MAX_FILE_SIZE = 512 * 1024


class FileEntry(BaseModel):
    name: str
    path: str  # relative to project root
    is_dir: bool
    size: int | None = None
    children: list["FileEntry"] | None = None


class FileTreeResponse(BaseModel):
    tree: list[FileEntry]
    project_path: str


class FileContentResponse(BaseModel):
    path: str
    content: str
    size: int
    language: str


def _build_tree(root: Path, base: Path, depth: int = 0, max_depth: int = 6) -> list[dict]:
    """Recursively build a file tree, skipping ignored dirs."""
    if depth > max_depth:
        return []
    entries = []
    try:
        items = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return []
    for item in items:
        if item.name.startswith(".") and item.name != ".env.example":
            if item.is_dir():
                continue
        if item.is_dir() and item.name in _SKIP_DIRS:
            continue
        rel = str(item.relative_to(base))
        if item.is_dir():
            children = _build_tree(item, base, depth + 1, max_depth)
            entries.append({
                "name": item.name,
                "path": rel,
                "is_dir": True,
                "size": None,
                "children": children,
            })
        else:
            try:
                size = item.stat().st_size
            except OSError:
                size = 0
            entries.append({
                "name": item.name,
                "path": rel,
                "is_dir": False,
                "size": size,
                "children": None,
            })
    return entries


def _guess_language(filename: str) -> str:
    """Map file extension to a language identifier for syntax highlighting."""
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".tsx": "tsx", ".jsx": "jsx", ".json": "json", ".yaml": "yaml",
        ".yml": "yaml", ".toml": "toml", ".md": "markdown", ".html": "html",
        ".css": "css", ".scss": "scss", ".sql": "sql", ".sh": "bash",
        ".bash": "bash", ".zsh": "bash", ".dockerfile": "dockerfile",
        ".xml": "xml", ".svg": "xml", ".go": "go", ".rs": "rust",
        ".java": "java", ".c": "c", ".cpp": "cpp", ".h": "c",
        ".rb": "ruby", ".php": "php", ".env": "bash", ".gitignore": "bash",
        ".txt": "text", ".cfg": "ini", ".ini": "ini", ".conf": "ini",
    }
    name_lower = filename.lower()
    if name_lower == "dockerfile":
        return "dockerfile"
    if name_lower == "makefile":
        return "makefile"
    ext = Path(filename).suffix.lower()
    return ext_map.get(ext, "text")


@project_router.get("/{project_id}/files", response_model=FileTreeResponse)
async def get_file_tree(
    project_id: int,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Return recursive file tree for a project."""
    repo = ProjectRepository(pool)
    project = await repo.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    project_path = Path(project.path)
    if not project_path.is_dir():
        raise HTTPException(status_code=404, detail="Project directory not found on disk")
    tree = _build_tree(project_path, project_path)
    return FileTreeResponse(tree=tree, project_path=project.path)


@project_router.get("/{project_id}/files/content", response_model=FileContentResponse)
async def get_file_content(
    project_id: int,
    path: str = Query(..., description="Relative path within the project"),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Return the text content of a file within a project."""
    repo = ProjectRepository(pool)
    project = await repo.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    project_root = Path(project.path).resolve()
    file_path = (project_root / path).resolve()
    # Security: ensure the file is within the project directory
    if not str(file_path).startswith(str(project_root)):
        raise HTTPException(status_code=403, detail="Access denied: path traversal detected")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    size = file_path.stat().st_size
    if size > _MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large ({size} bytes, max {_MAX_FILE_SIZE})")
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cannot read file: {e}")
    return FileContentResponse(
        path=path,
        content=content,
        size=size,
        language=_guess_language(file_path.name),
    )
