"""
FastAPI dependencies for dependency injection.

Provides database pool, auth verification, WebSocket token auth, and TaskManager access.
"""
import base64
import secrets

import asyncpg
from fastapi import Depends, HTTPException, Query, Request, WebSocket, status
from fastapi.exceptions import WebSocketException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from src.engine.manager import TaskManager
from src.server.config import get_settings

security = HTTPBasic(auto_error=False)


async def get_pool(request: Request) -> asyncpg.Pool:
    """Extract the asyncpg connection pool from app state."""
    return request.app.state.pool


def verify_credentials(
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> str:
    """Verify HTTP Basic Auth credentials.

    Returns the username on success.
    Raises 401 without WWW-Authenticate header (to prevent browser popup).
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
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
            detail="Not authenticated",
        )
    return credentials.username


def verify_ws_token(
    websocket: WebSocket,
    token: str = Query(...),
) -> str:
    """Verify WebSocket authentication via query parameter token.

    Token is base64-encoded "username:password" string (same credentials
    as HTTP Basic Auth).

    Returns the username on success.
    Raises WebSocketException with code 1008 (Policy Violation) on failure.
    """
    try:
        decoded = base64.b64decode(token).decode("utf-8")
        username, password = decoded.split(":", 1)
    except Exception:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    settings = get_settings()
    username_ok = secrets.compare_digest(
        username.encode("utf-8"),
        settings.auth_username.encode("utf-8"),
    )
    password_ok = secrets.compare_digest(
        password.encode("utf-8"),
        settings.auth_password.encode("utf-8"),
    )
    if not (username_ok and password_ok):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    return username


async def get_task_manager(request: Request) -> TaskManager:
    """Extract the TaskManager from app state."""
    return request.app.state.task_manager
