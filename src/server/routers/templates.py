"""
Template management REST endpoints (read-only).

Provides listing and detail endpoints for builtin project templates.
"""
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
