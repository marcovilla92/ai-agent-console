"""
FastAPI application factory with lifespan-managed asyncpg pool.

Usage:
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import FileResponse

from src.db.migrations import apply_schema
from src.engine.manager import TaskManager
from src.server.config import get_settings
from src.server.connection_manager import ConnectionManager
from src.server.dependencies import verify_credentials
from src.server.routers.tasks import task_router
from src.server.routers.projects import project_router
from src.server.routers.templates import template_router
from src.server.routers.ws import ws_router

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"

log = logging.getLogger(__name__)

health_router = APIRouter()


@health_router.get("/health")
async def health_check(request: Request):
    """Health check endpoint that verifies database connectivity."""
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
    return {"status": "ok", "database": "connected"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage asyncpg pool lifecycle."""
    settings = get_settings()
    log.info("Creating asyncpg pool (min=%d, max=%d)", settings.pool_min_size, settings.pool_max_size)
    app.state.pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=settings.pool_min_size,
        max_size=settings.pool_max_size,
        command_timeout=60.0,
    )
    try:
        await apply_schema(app.state.pool)
        app.state.connection_manager = ConnectionManager()
        app.state.task_manager = TaskManager(
            pool=app.state.pool,
            max_concurrent=2,
            connection_manager=app.state.connection_manager,
        )
        log.info("Schema applied, TaskManager created, server ready")
        yield
    finally:
        await app.state.task_manager.shutdown()
        log.info("TaskManager shut down")
        await app.state.pool.close()
        log.info("asyncpg pool closed")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="AI Agent Console", lifespan=lifespan)

    @app.get("/")
    async def root(_=Depends(verify_credentials)):
        """Serve the Alpine.js SPA."""
        return FileResponse(STATIC_DIR / "index.html")

    app.include_router(health_router)
    app.include_router(task_router)
    app.include_router(ws_router)
    app.include_router(template_router)
    app.include_router(project_router)
    return app
