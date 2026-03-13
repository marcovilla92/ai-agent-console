"""
Template management REST endpoints (full CRUD).

Provides listing, detail, create, update, and delete endpoints for project templates.
Builtin templates are protected from mutation (403 Forbidden).
"""
import shutil
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.server.dependencies import verify_credentials

TEMPLATES_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "templates"
REGISTRY_PATH = TEMPLATES_ROOT / "registry.yaml"
EXCLUDE_DIRS = {".git", "__pycache__", "node_modules", ".mypy_cache"}


# --- Pydantic models ---


class TemplateFile(BaseModel):
    path: str
    type: str  # "jinja2" or "static"
    size: int


class TemplateSummary(BaseModel):
    id: str
    name: str
    description: str
    builtin: bool


class TemplateListResponse(BaseModel):
    templates: list[TemplateSummary]


class TemplateDetail(BaseModel):
    id: str
    name: str
    description: str
    builtin: bool
    files: list[TemplateFile]


class TemplateCreateRequest(BaseModel):
    id: str
    name: str
    description: str = ""
    files: dict[str, str] = {}  # {relative_path: content}


class TemplateCreateResponse(BaseModel):
    id: str
    name: str
    description: str
    builtin: bool
    file_count: int


class TemplateUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    files_upsert: dict[str, str] | None = None  # {relative_path: content}
    files_delete: list[str] | None = None  # [relative_path]


# --- Helpers ---


def load_registry() -> dict:
    """Load the template registry from YAML."""
    if not REGISTRY_PATH.exists():
        return {"templates": []}
    return yaml.safe_load(REGISTRY_PATH.read_text()) or {"templates": []}


def save_registry(data: dict) -> None:
    """Save the template registry to YAML."""
    REGISTRY_PATH.write_text(yaml.safe_dump(data, default_flow_style=False))


def get_file_manifest(template_id: str) -> list[TemplateFile]:
    """Walk template directory and return file manifest."""
    template_dir = TEMPLATES_ROOT / template_id
    files = []
    for file_path in sorted(template_dir.rglob("*")):
        if not file_path.is_file():
            continue
        # Skip excluded directories
        if any(part in EXCLUDE_DIRS for part in file_path.parts):
            continue
        rel = str(file_path.relative_to(template_dir))
        file_type = "jinja2" if file_path.suffix == ".j2" else "static"
        files.append(TemplateFile(path=rel, type=file_type, size=file_path.stat().st_size))
    return files


def safe_write_template_file(
    template_dir: Path, rel_path: str, content: str
) -> None:
    """Write a file inside template_dir, rejecting path traversal."""
    target = (template_dir / rel_path).resolve()
    if not target.is_relative_to(template_dir.resolve()):
        raise ValueError(f"Path traversal attempt: {rel_path!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _get_entry_or_404(data: dict, template_id: str) -> dict:
    """Find a registry entry by id or raise 404."""
    entry = next((t for t in data["templates"] if t["id"] == template_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return entry


def _count_files(template_dir: Path) -> int:
    """Count files in a template directory (excluding EXCLUDE_DIRS)."""
    count = 0
    if template_dir.is_dir():
        for f in template_dir.rglob("*"):
            if f.is_file() and not any(part in EXCLUDE_DIRS for part in f.parts):
                count += 1
    return count


# --- Router ---


template_router = APIRouter(
    prefix="/templates",
    tags=["templates"],
    dependencies=[Depends(verify_credentials)],
)


@template_router.get("", response_model=TemplateListResponse)
async def list_templates():
    """List all available templates."""
    registry = load_registry()
    templates = [TemplateSummary(**t) for t in registry["templates"]]
    return TemplateListResponse(templates=templates)


@template_router.get("/{template_id}", response_model=TemplateDetail)
async def get_template(template_id: str):
    """Get template detail with file manifest."""
    registry = load_registry()
    entry = None
    for t in registry["templates"]:
        if t["id"] == template_id:
            entry = t
            break
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_id}' not found",
        )
    files = get_file_manifest(template_id)
    return TemplateDetail(
        id=entry["id"],
        name=entry["name"],
        description=entry["description"],
        builtin=entry["builtin"],
        files=files,
    )


@template_router.post(
    "",
    response_model=TemplateCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(req: TemplateCreateRequest):
    """Create a new custom template."""
    data = load_registry()
    # Check for duplicate id
    if any(t["id"] == req.id for t in data["templates"]):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Template '{req.id}' already exists",
        )
    template_dir = TEMPLATES_ROOT / req.id
    template_dir.mkdir(parents=True, exist_ok=True)
    try:
        for rel_path, content in req.files.items():
            try:
                safe_write_template_file(template_dir, rel_path, content)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
                ) from exc
        # Add to registry
        data["templates"].append(
            {
                "id": req.id,
                "name": req.name,
                "description": req.description,
                "builtin": False,
            }
        )
        save_registry(data)
    except Exception:
        # Clean up on failure
        if template_dir.exists():
            shutil.rmtree(template_dir)
        raise
    return TemplateCreateResponse(
        id=req.id,
        name=req.name,
        description=req.description,
        builtin=False,
        file_count=_count_files(template_dir),
    )


@template_router.put("/{template_id}", response_model=TemplateCreateResponse)
async def update_template(template_id: str, req: TemplateUpdateRequest):
    """Update an existing custom template."""
    data = load_registry()
    entry = _get_entry_or_404(data, template_id)
    if entry.get("builtin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify builtin template",
        )
    # Update metadata
    if req.name is not None:
        entry["name"] = req.name
    if req.description is not None:
        entry["description"] = req.description
    template_dir = TEMPLATES_ROOT / template_id
    # Upsert files
    if req.files_upsert:
        for rel_path, content in req.files_upsert.items():
            try:
                safe_write_template_file(template_dir, rel_path, content)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
                ) from exc
    # Delete files
    if req.files_delete:
        for rel_path in req.files_delete:
            target = template_dir / rel_path
            if target.exists():
                target.unlink()
    save_registry(data)
    return TemplateCreateResponse(
        id=template_id,
        name=entry["name"],
        description=entry["description"],
        builtin=False,
        file_count=_count_files(template_dir),
    )


@template_router.delete("/{template_id}")
async def delete_template(template_id: str):
    """Delete a custom template."""
    data = load_registry()
    entry = _get_entry_or_404(data, template_id)
    if entry.get("builtin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete builtin template",
        )
    template_dir = TEMPLATES_ROOT / template_id
    if template_dir.exists():
        shutil.rmtree(template_dir)
    data["templates"] = [t for t in data["templates"] if t["id"] != template_id]
    save_registry(data)
    return {"status": "deleted", "id": template_id}
