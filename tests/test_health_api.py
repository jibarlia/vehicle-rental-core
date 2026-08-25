from unittest.mock import AsyncMock

from httpx import AsyncClient


class TestHealthEndpoints:
    async def test_liveness_should_return_ok(self, client: AsyncClient) -> None:
        response = await client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    async def test_liveness_should_not_touch_the_database(
        self, client: AsyncClient, session: AsyncMock
    ) -> None:
        await client.get("/health")

        # Liveness must stay answerable while Postgres is down.
        session.execute.assert_not_called()

    async def test_readiness_should_report_database_reachable(
        self, client: AsyncClient, session: AsyncMock
    ) -> None:
        response = await client.get("/health/ready")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "reachable"}
        session.execute.assert_awaited_once()

    async def test_readiness_should_return_503_when_the_query_fails(
        self, client: AsyncClient, session: AsyncMock
    ) -> None:
        session.execute.side_effect = ConnectionError("connection refused")

        response = await client.get("/health/ready")

        assert response.status_code == 503
        assert response.json() == {"status": "unavailable", "database": "unreachable"}
