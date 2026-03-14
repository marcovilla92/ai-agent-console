"""
ProjectService -- business logic for project lifecycle operations.

Provides create_project (with template scaffolding + git init),
list_projects (with auto-registration of untracked workspace folders),
and delete_project (DB-only, does not touch filesystem).
"""
import asyncio
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import asyncpg
from jinja2 import Template

from src.context.assembler import detect_stack
from src.db.pg_repository import ProjectRepository
from src.db.pg_schema import Project
from src.pipeline.events import ProjectEvent, emit_event
from src.pipeline.project import sanitize_project_name
from src.server.routers.templates import TEMPLATES_ROOT, EXCLUDE_DIRS

log = logging.getLogger(__name__)


def scaffold_from_template(
    template_id: str, target_dir: Path, context: dict
) -> None:
    """Copy template files into target_dir, rendering .j2 files with Jinja2.

    Raises ValueError if template_id is not found.
    """
    template_dir = TEMPLATES_ROOT / template_id
    if not template_dir.is_dir():
        raise ValueError(f"Template '{template_id}' not found at {template_dir}")

    for src_file in sorted(template_dir.rglob("*")):
        if not src_file.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in src_file.parts):
            continue
        rel = src_file.relative_to(template_dir)
        if src_file.suffix == ".j2":
            # Render Jinja2 template, strip .j2 extension
            dest = target_dir / rel.with_suffix("")
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmpl = Template(src_file.read_text(encoding="utf-8"))
            dest.write_text(tmpl.render(**context), encoding="utf-8")
        else:
            dest = target_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest)


async def git_init_project(project_path: str) -> None:
    """Initialize a git repo and make an initial commit.

    Swallows errors -- git failure should not prevent project creation.
    """
    try:
        for cmd in [
            ["git", "init"],
            ["git", "add", "."],
            ["git", "-c", "user.name=Console", "-c", "user.email=console@local",
             "commit", "-m", "Initial scaffolding"],
        ]:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10.0)
    except Exception as exc:
        log.warning("git init failed for %s: %s", project_path, exc)


class ProjectService:
    """High-level project operations used by the router layer."""

    WORKSPACE_ROOT = Path.home() / "projects"

    def __init__(
        self,
        pool: asyncpg.Pool,
        workspace_root: Optional[Path] = None,
    ) -> None:
        self._pool = pool
        self._repo = ProjectRepository(pool)
        if workspace_root is not None:
            self._workspace = Path(workspace_root)
        else:
            # Check APP_PROJECT_PATH env var before falling back to ~/projects
            env_path = os.environ.get("APP_PROJECT_PATH", "")
            self._workspace = Path(env_path) if env_path else self.WORKSPACE_ROOT

    async def create_project(
        self, name: str, description: str = "", template: str = "blank"
    ) -> Project:
        """Create a new project: scaffold from template, git init, insert DB record.

        Raises FileExistsError if the project folder already exists.
        Raises ValueError if the template is not found.
        """
        slug = sanitize_project_name(name)
        project_dir = self._workspace / slug

        if project_dir.exists():
            raise FileExistsError(f"Project folder already exists: {project_dir}")

        project_dir.mkdir(parents=True, exist_ok=True)

        # Scaffold from template
        context = {
            "name": name,
            "slug": slug,
            "description": description,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "author": "ubuntu",
        }
        scaffold_from_template(template, project_dir, context)

        # git init + initial commit
        await git_init_project(str(project_dir))

        # Insert DB record
        now = datetime.now(timezone.utc)
        project = Project(
            name=name,
            slug=slug,
            path=str(project_dir),
            description=description,
            created_at=now,
        )
        project.id = await self._repo.insert(project)

        # Emit event
        await emit_event(
            ProjectEvent.PROJECT_CREATED,
            {"id": project.id, "name": name, "path": str(project_dir)},
        )
        return project

    async def list_projects(self) -> list[dict]:
        """Scan workspace, auto-register untracked folders, return enriched list.

        Steps:
        1. Scan top-level dirs in workspace (skip hidden dirs)
        2. Auto-register unknown dirs via upsert_by_path (idempotent)
        3. Fetch all projects from DB
        4. Enrich each with detected stack
        """
        # 1. Scan filesystem
        if self._workspace.is_dir():
            for child in sorted(self._workspace.iterdir()):
                if not child.is_dir() or child.name.startswith("."):
                    continue
                # 2. Auto-register via upsert (ON CONFLICT DO NOTHING)
                project = Project(
                    name=child.name,
                    slug=child.name,
                    path=str(child),
                    description="",
                    created_at=datetime.now(timezone.utc),
                )
                await self._repo.upsert_by_path_safe(project)

        # 3. Fetch all from DB
        all_projects = await self._repo.list_all()

        # Filter to only projects whose path is under our workspace
        workspace_str = str(self._workspace)
        projects = [
            p for p in all_projects
            if p.path.startswith(workspace_str)
        ]

        # 4. Enrich with stack detection
        result = []
        for p in projects:
            result.append({
                "id": p.id,
                "name": p.name,
                "slug": p.slug,
                "path": p.path,
                "description": p.description,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "last_used_at": p.last_used_at.isoformat() if p.last_used_at else None,
                "stack": detect_stack(p.path),
            })

        return result

    async def delete_project(self, project_id: int) -> None:
        """Delete a project record from DB. Does NOT touch the filesystem.

        Raises ValueError if project does not exist.
        """
        existing = await self._repo.get(project_id)
        if existing is None:
            raise ValueError(f"Project {project_id} not found")

        await self._repo.delete(project_id)
        await emit_event(ProjectEvent.PROJECT_DELETED, {"id": project_id})
