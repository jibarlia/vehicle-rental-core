from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vehicle_rental_core.api.app import create_app
from vehicle_rental_core.api.dependencies import get_session
from vehicle_rental_core.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    # _env_file=None so a developer's local .env can never change a result.
    return Settings(
        environment="test",
        log_level="WARNING",
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def session() -> AsyncMock:
    """Stand-in for AsyncSession — the suite never opens a connection.

    Every test that needs different behaviour (a failing query, a returned
    row) configures this mock rather than reaching for a real database.
    """
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def app(settings: Settings, session: AsyncMock) -> Iterator[FastAPI]:
    app = create_app(settings)

    async def override_get_session() -> AsyncIterator[AsyncMock]:
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    # ASGITransport drives the app in-process: no socket, no lifespan, so the
    # engine is never built and no database is contacted.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
