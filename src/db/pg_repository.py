"""
PostgreSQL repository classes for v2.0 web platform.

Uses asyncpg Pool for all database operations.
Mirrors the aiosqlite repository pattern from src/db/repository.py.
"""
from datetime import datetime
from typing import Optional

import asyncpg

from src.db.pg_schema import Task, Project, AgentOutput, AgentUsage, OrchestratorDecisionRecord


class TaskRepository:
    """CRUD operations for the tasks table (renamed from sessions in v2.0)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, task: Task) -> int:
        return await self._pool.fetchval(
            "INSERT INTO tasks (name, project_path, created_at, status, mode, prompt, project_id) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id",
            task.name, task.project_path, task.created_at,
            task.status, task.mode, task.prompt, task.project_id,
        )

    async def get(self, task_id: int) -> Optional[Task]:
        row = await self._pool.fetchrow(
            "SELECT id, name, project_path, created_at, "
            "status, mode, prompt, completed_at, error, project_id "
            "FROM tasks WHERE id = $1",
            task_id,
        )
        if row is None:
            return None
        return Task(
            id=row["id"],
            name=row["name"],
            project_path=row["project_path"],
            created_at=row["created_at"],
            status=row["status"],
            mode=row["mode"],
            prompt=row["prompt"],
            completed_at=row["completed_at"],
            error=row["error"],
            project_id=row["project_id"],
        )

    async def list_all(self) -> list[Task]:
        rows = await self._pool.fetch(
            "SELECT id, name, project_path, created_at, "
            "status, mode, prompt, completed_at, error, project_id "
            "FROM tasks ORDER BY id DESC"
        )
        return [
            Task(
                id=r["id"],
                name=r["name"],
                project_path=r["project_path"],
                created_at=r["created_at"],
                status=r["status"],
                mode=r["mode"],
                prompt=r["prompt"],
                completed_at=r["completed_at"],
                error=r["error"],
                project_id=r["project_id"],
            )
            for r in rows
        ]

    async def update_status(
        self,
        task_id: int,
        status: str,
        error: Optional[str] = None,
        completed_at: Optional[datetime] = None,
    ) -> None:
        """Update task status, optionally setting error and completed_at."""
        await self._pool.execute(
            "UPDATE tasks SET status = $1, error = $2, completed_at = $3 "
            "WHERE id = $4",
            status, error, completed_at, task_id,
        )


class ProjectRepository:
    """CRUD operations for the projects table (v2.1)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def insert(self, project: Project) -> int:
        return await self._pool.fetchval(
            "INSERT INTO projects (name, slug, path, description, created_at) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING id",
            project.name, project.slug, project.path,
            project.description, project.created_at,
        )

    async def get(self, project_id: int) -> Optional[Project]:
        row = await self._pool.fetchrow(
            "SELECT id, name, slug, path, description, created_at, last_used_at "
            "FROM projects WHERE id = $1", project_id
        )
        if row is None:
            return None
        return Project(
            id=row["id"], name=row["name"], slug=row["slug"],
            path=row["path"], description=row["description"],
            created_at=row["created_at"], last_used_at=row["last_used_at"],
        )

    async def list_all(self) -> list[Project]:
        rows = await self._pool.fetch(
            "SELECT id, name, slug, path, description, created_at, last_used_at "
            "FROM projects ORDER BY last_used_at DESC NULLS LAST, created_at DESC"
        )
        return [
            Project(
                id=r["id"], name=r["name"], slug=r["slug"],
                path=r["path"], description=r["description"],
                created_at=r["created_at"], last_used_at=r["last_used_at"],
            )
            for r in rows
        ]

    async def upsert_by_path(self, project: Project) -> Optional[int]:
        """Insert a project if path doesn't exist, otherwise do nothing.

        Returns the new id if inserted, None if path already exists.
        """
        return await self._pool.fetchval(
            "INSERT INTO projects (name, slug, path, description, created_at) "
            "VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (path) DO NOTHING RETURNING id",
            project.name, project.slug, project.path,
            project.description, project.created_at,
        )

    async def upsert_by_path_safe(self, project: Project) -> Optional[int]:
        """Insert a project if path doesn't exist, handling name conflicts.

        If a name conflict occurs, appends a numeric suffix to make it unique.
        Returns the new id if inserted, None if path already exists.
        """
        # First check if path already exists
        existing = await self._pool.fetchval(
            "SELECT id FROM projects WHERE path = $1", project.path
        )
        if existing is not None:
            return None

        # Try insert, handle name conflicts
        base_name = project.name
        base_slug = project.slug
        for i in range(10):
            name = base_name if i == 0 else f"{base_name}-{i}"
            slug = base_slug if i == 0 else f"{base_slug}-{i}"
            try:
                return await self._pool.fetchval(
                    "INSERT INTO projects (name, slug, path, description, created_at) "
                    "VALUES ($1, $2, $3, $4, $5) "
                    "ON CONFLICT (path) DO NOTHING RETURNING id",
                    name, slug, project.path,
                    project.description, project.created_at,
                )
            except Exception as e:
                if "projects_name_key" in str(e) or "projects_slug_key" in str(e):
                    continue
                raise
        return None

    async def delete(self, project_id: int) -> None:
        await self._pool.execute(
            "UPDATE tasks SET project_id = NULL WHERE project_id = $1", project_id
        )
        await self._pool.execute("DELETE FROM projects WHERE id = $1", project_id)

    async def update_last_used(self, project_id: int) -> None:
        await self._pool.execute(
            "UPDATE projects SET last_used_at = NOW() WHERE id = $1", project_id
        )


class AgentOutputRepository:
    """Persistence for agent output records linked to tasks."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, output: AgentOutput) -> int:
        return await self._pool.fetchval(
            "INSERT INTO agent_outputs (session_id, agent_type, raw_output, created_at) "
            "VALUES ($1, $2, $3, $4) RETURNING id",
            output.session_id, output.agent_type, output.raw_output, output.created_at,
        )

    async def get_by_session(self, session_id: int) -> list[AgentOutput]:
        rows = await self._pool.fetch(
            "SELECT id, session_id, agent_type, raw_output, created_at "
            "FROM agent_outputs WHERE session_id = $1 ORDER BY id",
            session_id,
        )
        return [
            AgentOutput(
                id=r["id"],
                session_id=r["session_id"],
                agent_type=r["agent_type"],
                raw_output=r["raw_output"],
                created_at=r["created_at"],
            )
            for r in rows
        ]


class OrchestratorDecisionRepository:
    """Persistence for orchestrator decision records linked to tasks."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, record: OrchestratorDecisionRecord) -> int:
        return await self._pool.fetchval(
            "INSERT INTO orchestrator_decisions "
            "(session_id, next_agent, reasoning, confidence, full_response, iteration_count, created_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id",
            record.session_id,
            record.next_agent,
            record.reasoning,
            record.confidence,
            record.full_response,
            record.iteration_count,
            record.created_at,
        )

    async def get_by_session(self, session_id: int) -> list[OrchestratorDecisionRecord]:
        rows = await self._pool.fetch(
            "SELECT id, session_id, next_agent, reasoning, confidence, "
            "full_response, iteration_count, created_at "
            "FROM orchestrator_decisions WHERE session_id = $1 ORDER BY id",
            session_id,
        )
        return [
            OrchestratorDecisionRecord(
                id=r["id"],
                session_id=r["session_id"],
                next_agent=r["next_agent"],
                reasoning=r["reasoning"],
                confidence=r["confidence"],
                full_response=r["full_response"],
                iteration_count=r["iteration_count"],
                created_at=r["created_at"],
            )
            for r in rows
        ]


class UsageRepository:
    """Persistence for agent usage/cost tracking records linked to tasks."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, usage: AgentUsage) -> int:
        return await self._pool.fetchval(
            "INSERT INTO agent_usage "
            "(session_id, agent_type, input_tokens, output_tokens, "
            "cache_read_tokens, cache_creation_tokens, cost_usd, created_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id",
            usage.session_id,
            usage.agent_type,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_tokens,
            usage.cache_creation_tokens,
            usage.cost_usd,
            usage.created_at,
        )

    async def get_by_session(self, session_id: int) -> list[AgentUsage]:
        rows = await self._pool.fetch(
            "SELECT id, session_id, agent_type, input_tokens, output_tokens, "
            "cache_read_tokens, cache_creation_tokens, cost_usd, created_at "
            "FROM agent_usage WHERE session_id = $1 ORDER BY id",
            session_id,
        )
        return [
            AgentUsage(
                id=r["id"],
                session_id=r["session_id"],
                agent_type=r["agent_type"],
                input_tokens=r["input_tokens"],
                output_tokens=r["output_tokens"],
                cache_read_tokens=r["cache_read_tokens"],
                cache_creation_tokens=r["cache_creation_tokens"],
                cost_usd=r["cost_usd"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
