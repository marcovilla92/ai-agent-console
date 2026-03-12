"""
FastAPI dependencies for dependency injection.
"""
import asyncpg
from fastapi import Request


async def get_pool(request: Request) -> asyncpg.Pool:
    """Extract the asyncpg connection pool from app state."""
    return request.app.state.pool
