"""
FastAPI dependencies for dependency injection.

Provides database pool, auth verification, and TaskManager access.
"""
import secrets

import asyncpg
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from src.engine.manager import TaskManager
from src.server.config import get_settings

security = HTTPBasic()


async def get_pool(request: Request) -> asyncpg.Pool:
    """Extract the asyncpg connection pool from app state."""
    return request.app.state.pool


def verify_credentials(
    credentials: HTTPBasicCredentials = Depends(security),
) -> str:
    """Verify HTTP Basic Auth credentials.

    Returns the username on success.
    Raises 401 with WWW-Authenticate: Basic header on failure.
    """
    settings = get_settings()
    username_ok = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        settings.auth_username.encode("utf-8"),
    )
    password_ok = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        settings.auth_password.encode("utf-8"),
    )
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


async def get_task_manager(request: Request) -> TaskManager:
    """Extract the TaskManager from app state."""
    return request.app.state.task_manager
