from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from vehicle_rental_core.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Build the process-wide AsyncEngine from validated settings."""
    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory for request-scoped sessions.

    ``expire_on_commit=False`` keeps entities readable after commit.
    """
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
