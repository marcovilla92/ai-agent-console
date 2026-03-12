"""
Server configuration using pydantic-settings.

Environment variables are prefixed with APP_ (e.g., APP_DATABASE_URL).
"""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    database_url: str = "postgresql://postgres:postgres@localhost:5432/agent_console"
    pool_min_size: int = 2
    pool_max_size: int = 5
    host: str = "0.0.0.0"
    port: int = 8000
    auth_username: str = "admin"
    auth_password: str = "changeme"
    project_path: str = "."

    model_config = {"env_prefix": "APP_"}


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
