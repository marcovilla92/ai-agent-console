"""
ProjectService -- business logic for project lifecycle operations.

Provides list_projects (with auto-registration of untracked workspace folders)
and delete_project (DB-only, does not touch filesystem).
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import asyncpg

from src.context.assembler import detect_stack
from src.db.pg_repository import ProjectRepository
from src.db.pg_schema import Project
from src.pipeline.events import ProjectEvent, emit_event

log = logging.getLogger(__name__)


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
            self._workspace = self.WORKSPACE_ROOT

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
                await self._repo.upsert_by_path(project)

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
