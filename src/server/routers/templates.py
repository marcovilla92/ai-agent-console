"""
Template management REST endpoints (full CRUD + AI generation).

Provides listing, detail, create, update, delete, and AI-generate endpoints
for project templates.  Builtin templates are protected from mutation (403).
"""
import asyncio
import json
import logging
import re
import shutil
import tempfile
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.agents.config import PROTECTED_AGENTS
from src.agents.loader import discover_project_agents
from src.commands.loader import discover_project_commands
from src.runner.runner import call_orchestrator_claude
from src.server.dependencies import verify_credentials

log = logging.getLogger(__name__)

TEMPLATES_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "templates"
REGISTRY_PATH = TEMPLATES_ROOT / "registry.yaml"
EXCLUDE_DIRS = {".git", "__pycache__", "node_modules", ".mypy_cache"}

# --- AI generation constants ---

_gen_lock = asyncio.Lock()

TEMPLATE_GEN_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "files": {"type": "object", "additionalProperties": {"type": "string"}},
        },
        "required": ["id", "name", "description", "files"],
    }
)

_GEN_SYSTEM_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "agents"
    / "prompts"
    / "template_gen_system.txt"
)


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


class GenerateTemplateRequest(BaseModel):
    description: str  # Natural language project description (max 2000 chars)
    stack: str | None = None  # Optional stack hint


class TemplateFilesResponse(BaseModel):
    files: dict[str, str]  # {relative_path: content}


class GenerateTemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    files: dict[str, str]
    validation_errors: list[str]


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


@template_router.get("/{template_id}/files", response_model=TemplateFilesResponse)
async def get_template_files(template_id: str):
    """Return all file contents for a template as a flat dict."""
    data = load_registry()
    _get_entry_or_404(data, template_id)
    template_dir = TEMPLATES_ROOT / template_id
    files: dict[str, str] = {}
    for file_path in sorted(template_dir.rglob("*")):
        if not file_path.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in file_path.parts):
            continue
        rel = str(file_path.relative_to(template_dir))
        try:
            files[rel] = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            files[rel] = "[binary file]"
    return TemplateFilesResponse(files=files)


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


# --- AI template generation ---


def _validate_generated_files(files: dict[str, str]) -> list[str]:
    """Validate generated template files through existing loaders."""
    errors: list[str] = []
    tmp_dir = tempfile.mkdtemp(prefix="tmpl-validate-")
    try:
        for rel_path, content in files.items():
            # Check path safety
            if rel_path.startswith("/") or ".." in rel_path:
                errors.append(f"Invalid path: {rel_path}")
                continue
            target = Path(tmp_dir) / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        # Check reserved agent names
        agents_dir = Path(tmp_dir) / ".claude" / "agents"
        if agents_dir.is_dir():
            for md in agents_dir.glob("*.md"):
                stem = md.stem.lower().replace(" ", "-")
                if stem in PROTECTED_AGENTS:
                    errors.append(f"Agent '{stem}' uses reserved core agent name")

        # Run full agent loader to catch parse errors
        try:
            discover_project_agents(tmp_dir)
        except Exception as exc:
            errors.append(f"Agent validation error: {exc}")

        # Run command loader to catch parse errors
        try:
            discover_project_commands(tmp_dir)
        except Exception as exc:
            errors.append(f"Command validation error: {exc}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return errors


@template_router.post("/generate", response_model=GenerateTemplateResponse)
async def generate_template(req: GenerateTemplateRequest):
    """Generate a project template from a natural language description using AI."""
    # AIGEN-03: Non-blocking lock check
    if _gen_lock.locked():
        raise HTTPException(
            status_code=429,
            detail="Template generation already in progress",
            headers={"Retry-After": "30"},
        )

    async with _gen_lock:
        # Cap description length
        description = req.description[:2000]

        # Build prompt
        prompt = f"Generate a project template for: {description}"
        if req.stack:
            prompt += f"\nPreferred stack: {req.stack}"

        # Load system prompt
        system_prompt_text = _GEN_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

        log.info("Template generation requested: %.100s...", description)

        # Call Claude CLI with structured output + timeout
        try:
            raw = await asyncio.wait_for(
                call_orchestrator_claude(
                    prompt=prompt,
                    schema=TEMPLATE_GEN_SCHEMA,
                    system_prompt=system_prompt_text,
                    extra_args=["--max-turns", "1"],
                ),
                timeout=600,
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Template generation timed out",
            )

        # Parse response — Claude CLI returns various formats
        try:
            log.info("AI generation raw response length: %d, preview: %.500s", len(raw), raw[:500])
            response = json.loads(raw)
            # Try multiple extraction paths
            if isinstance(response, dict):
                data = response.get("structured_output") or response.get("result") or response
                if isinstance(data, str):
                    data = json.loads(data)
            elif isinstance(response, list):
                # Sometimes returns array of messages — find the structured output
                for item in response:
                    if isinstance(item, dict) and item.get("type") == "result":
                        data = item.get("result") or item.get("structured_output")
                        if isinstance(data, str):
                            data = json.loads(data)
                        break
                else:
                    data = response
            else:
                data = response
            if not isinstance(data, dict):
                raise ValueError(f"Expected dict, got {type(data).__name__}: {str(data)[:200]}")
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            log.error("AI generation produced invalid response: %s", exc)
            raise HTTPException(
                status_code=502,
                detail="AI generation produced invalid response",
            )

        # AIGEN-02: Validate generated files
        generated_files = data.get("files", {})
        validation_errors = _validate_generated_files(generated_files)

        # Extract fields with fallbacks
        tmpl_name = data.get("name") or data.get("project_name") or data.get("template_name") or "ai-generated"
        tmpl_id = data.get("id") or data.get("slug") or data.get("template_id") or re.sub(r"[^a-z0-9-]", "", tmpl_name.lower().replace(" ", "-"))
        tmpl_desc = data.get("description") or data.get("project_description") or description[:200]

        log.info(
            "Template generated: id=%s name=%s files=%d errors=%d keys=%s",
            tmpl_id, tmpl_name,
            len(generated_files),
            len(validation_errors),
            list(data.keys()),
        )

        return GenerateTemplateResponse(
            id=tmpl_id,
            name=tmpl_name,
            description=tmpl_desc,
            files=generated_files,
            validation_errors=validation_errors,
        )
