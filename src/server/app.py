"""
FastAPI application factory with lifespan-managed asyncpg pool.

Usage:
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""
import logging
from contextlib import asynccontextmanager

import asyncpg
from fastapi import APIRouter, FastAPI, Request

from src.db.migrations import apply_schema
from src.engine.manager import TaskManager
from src.server.config import get_settings
from src.server.connection_manager import ConnectionManager
from src.server.routers.tasks import task_router
from src.server.routers.views import view_router
from src.server.routers.ws import ws_router

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
    app.include_router(health_router)
    app.include_router(task_router)
    app.include_router(ws_router)
    app.include_router(view_router)
    return app
