from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError

from tests.conftest import override_dependencies
from vehicle_rental_core.api.app import create_app
from vehicle_rental_core.application.views import FleetMetrics
from vehicle_rental_core.core.config import Settings
from vehicle_rental_core.domain.enums import VehicleStatus


class TestMetricsEndpoint:
    async def test_metrics_should_expose_prometheus_text_format(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/metrics")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")

    async def test_metrics_should_count_handled_requests(
        self, client: AsyncClient
    ) -> None:
        await client.get("/health")

        body = (await client.get("/metrics")).text

        assert 'http_requests_total{method="GET",path="/health",status="200"}' in body

    async def test_metrics_should_label_unmatched_routes_without_the_raw_path(
        self, client: AsyncClient
    ) -> None:
        # Guards the cardinality rule: an unrouted URL must not become a label.
        await client.get("/does-not-exist")

        body = (await client.get("/metrics")).text

        assert 'path="__unmatched__"' in body
        assert "/does-not-exist" not in body


class TestFleetGauges:
    async def test_metrics_should_expose_every_status_including_empty_ones(
        self, client: AsyncClient, fleet_metrics_service: AsyncMock
    ) -> None:
        # Maintenance is absent from the tally, so it must still render as 0 —
        # an unwritten gauge label would keep whatever a prior scrape set.
        fleet_metrics_service.collect.return_value = FleetMetrics(
            vehicle_counts={
                VehicleStatus.AVAILABLE: 12,
                VehicleStatus.IN_USE: 5,
                VehicleStatus.MAINTENANCE: 0,
                VehicleStatus.RETIRED: 1,
            },
            ongoing_rentals=5,
        )

        body = (await client.get("/metrics")).text

        assert 'fleet_vehicles{status="available"} 12.0' in body
        assert 'fleet_vehicles{status="in_use"} 5.0' in body
        assert 'fleet_vehicles{status="maintenance"} 0.0' in body
        assert 'fleet_vehicles{status="retired"} 1.0' in body

    async def test_metrics_should_expose_the_ongoing_rental_count(
        self, client: AsyncClient, fleet_metrics_service: AsyncMock
    ) -> None:
        fleet_metrics_service.collect.return_value = FleetMetrics(
            vehicle_counts=dict.fromkeys(VehicleStatus, 0),
            ongoing_rentals=7,
        )

        body = (await client.get("/metrics")).text

        assert "fleet_rentals_ongoing 7.0" in body

    async def test_metrics_should_still_serve_http_metrics_when_the_database_fails(
        self, client: AsyncClient, fleet_metrics_service: AsyncMock
    ) -> None:
        fleet_metrics_service.collect.side_effect = OperationalError(
            "SELECT 1", {}, Exception("connection refused")
        )

        response = await client.get("/metrics")

        assert response.status_code == 200
        assert "http_requests_total" in response.text

    async def test_metrics_should_be_absent_when_disabled(self) -> None:
        settings = Settings(
            environment="test",
            log_level="WARNING",
            metrics_enabled=False,
            _env_file=None,  # type: ignore[call-arg]
        )
        app = create_app(settings)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/metrics")

        assert response.status_code == 404


class TestMetricsOnUnhandledErrors:
    async def test_should_count_an_unhandled_exception_as_a_500(
        self,
        settings: Settings,
        session: AsyncMock,
        fleet_metrics_service: AsyncMock,
    ) -> None:
        app = create_app(settings)
        override_dependencies(app, session, fleet_metrics_service)

        @app.get("/boom")
        async def boom() -> None:
            raise RuntimeError("kaboom")

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/boom")
            body = (await client.get("/metrics")).text

        assert 'http_requests_total{method="GET",path="/boom",status="500"}' in body
