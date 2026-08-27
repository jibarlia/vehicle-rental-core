from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vehicle_rental_core.api.app import create_app
from vehicle_rental_core.api.dependencies import get_fleet_metrics_service, get_session
from vehicle_rental_core.application.fleet_metrics_service import FleetMetricsService
from vehicle_rental_core.application.views import FleetMetrics
from vehicle_rental_core.core.config import Settings
from vehicle_rental_core.domain.enums import VehicleStatus


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
def fleet_metrics_service() -> AsyncMock:
    """Stand-in for the service /metrics scrapes the gauges from.

    Overridden rather than driven through the mock session, because the
    repositories would hand back mocks the service cannot tally.
    """
    service = AsyncMock(spec=FleetMetricsService)
    service.collect.return_value = FleetMetrics(
        vehicle_counts=dict.fromkeys(VehicleStatus, 0),
        ongoing_rentals=0,
    )
    return service


def override_dependencies(
    app: FastAPI, session: AsyncMock, fleet_metrics_service: AsyncMock
) -> None:
    """Sever the app's two database seams. Shared with tests building their own."""

    async def override_get_session() -> AsyncIterator[AsyncMock]:
        yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_fleet_metrics_service] = lambda: fleet_metrics_service


@pytest.fixture
def app(
    settings: Settings, session: AsyncMock, fleet_metrics_service: AsyncMock
) -> Iterator[FastAPI]:
    app = create_app(settings)
    override_dependencies(app, session, fleet_metrics_service)
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    # In-process: no socket, no lifespan, so no database is contacted.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[httpx.Request]]:
    """Stub the CLI's HTTP boundary and record what it sent.

    Returns an installer: call it with the response the API should give (or an
    exception it should raise), and it hands back the list the requests land in.
    No socket is opened — httpx.MockTransport stands in for the network.
    """

    def install(
        response: httpx.Response | None = None,
        *,
        raises: Exception | None = None,
    ) -> list[httpx.Request]:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            if raises is not None:
                raise raises
            assert response is not None
            return response

        def fake_request(method: str, url: str, **kwargs: Any) -> httpx.Response:
            # timeout is a real-transport concern the mock does not accept.
            kwargs.pop("timeout", None)
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                return client.request(method, url, **kwargs)

        # _client calls httpx.request, so the module attribute is the seam.
        monkeypatch.setattr(httpx, "request", fake_request)
        return seen

    return install
