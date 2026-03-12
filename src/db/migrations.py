"""
Schema migration for PostgreSQL.

Applies CREATE TABLE IF NOT EXISTS statements using an asyncpg pool.
Safe to run multiple times (idempotent).
"""
import asyncpg

from src.db.pg_schema import PG_SCHEMA_SQL, ALTER_TASKS_SQL


async def apply_schema(pool: asyncpg.Pool) -> None:
    """Apply the PostgreSQL schema using the provided connection pool."""
    async with pool.acquire() as conn:
        await conn.execute(PG_SCHEMA_SQL)
        await conn.execute(ALTER_TASKS_SQL)
