from functools import lru_cache
from pathlib import Path
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

    # Opt-in: unset means stdout only, which is what containers want.
    log_file: Path | None = None
    log_file_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    log_file_backup_count: int = Field(default=5, ge=0)

    # Must carry an async driver. Port 55432 is what docker-compose publishes
    # to the host; inside compose the services override this with 5432.
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:55432/vehicle_rental"
    )
    db_echo: bool = False
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)

    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)

    # Where the CLI connects, not where the API binds: 0.0.0.0 is not dialable.
    api_base_url: str = "http://localhost:8000"

    metrics_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    """Cached so the process shares one instance; tests use ``cache_clear()``."""
    return Settings()
