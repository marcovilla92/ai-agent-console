"""Application settings via pydantic-settings."""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://user:pass@localhost:5432/dbname"
    pool_min_size: int = 2
    pool_max_size: int = 10

    class Config:
        env_prefix = "APP_"


@lru_cache
def get_settings() -> Settings:
    return Settings()
