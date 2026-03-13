"""Database schema and migrations."""

SCHEMA_SQL = """
-- Add your CREATE TABLE statements here
-- Use IF NOT EXISTS for idempotency
"""


async def apply_schema(pool):
    """Apply schema migrations."""
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
