from httpx import ASGITransport, AsyncClient

from vehicle_rental_core.api.app import create_app
from vehicle_rental_core.core.config import Settings


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


class TestMetricsOnUnhandledErrors:
    async def test_should_count_an_unhandled_exception_as_a_500(
        self, settings: Settings
    ) -> None:
        app = create_app(settings)

        @app.get("/boom")
        async def boom() -> None:
            raise RuntimeError("kaboom")

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/boom")
            body = (await client.get("/metrics")).text

        assert 'http_requests_total{method="GET",path="/boom",status="500"}' in body
