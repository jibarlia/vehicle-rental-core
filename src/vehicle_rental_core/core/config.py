from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of truth for environment configuration.

    Never read ``os.environ`` elsewhere — depend on ``get_settings()`` instead.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "vehicle-rental-core"
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # SQLAlchemy async URL. Must carry an async driver — psycopg 3 in every
    # real environment (``postgresql+psycopg://``).
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/vehicle_rental"
    )
    db_echo: bool = False
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)

    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)

    metrics_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    """Cached so the whole process shares one validated Settings instance.

    ``cache_clear()`` is the supported way for tests to re-read the environment.
    """
    return Settings()
