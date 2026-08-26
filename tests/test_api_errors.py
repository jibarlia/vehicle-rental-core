import logging
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from vehicle_rental_core.domain.errors import VehicleNotFoundError


@pytest.fixture
def app_with_failing_routes(app: FastAPI) -> FastAPI:
    @app.get("/boom")
    async def boom() -> None:
        raise ValueError("a leaky internal detail")

    @app.get("/rejected")
    async def rejected() -> None:
        raise VehicleNotFoundError("Vehicle 1 not found.")

    return app


@pytest.fixture
async def tolerant_client(
    app_with_failing_routes: FastAPI,
) -> AsyncIterator[AsyncClient]:
    """Starlette re-raises after the handler runs, which the default would surface."""
    transport = ASGITransport(app=app_with_failing_routes, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _api_record(caplog: pytest.LogCaptureFixture) -> logging.LogRecord:
    """The last record from our handlers — httpx logs the response after them."""
    records = [
        record
        for record in caplog.records
        if record.name == "vehicle_rental_core.api.errors"
    ]
    assert records
    return records[-1]


class TestUnexpectedErrors:
    async def test_should_answer_with_a_generic_500(
        self, tolerant_client: AsyncClient
    ) -> None:
        response = await tolerant_client.get("/boom")

        assert response.status_code == 500
        assert response.json() == {
            "detail": "Internal server error",
            "error": "InternalServerError",
        }

    async def test_should_not_leak_the_exception_text(
        self, tolerant_client: AsyncClient
    ) -> None:
        response = await tolerant_client.get("/boom")

        assert "a leaky internal detail" not in response.text

    async def test_should_log_the_traceback(
        self, tolerant_client: AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.ERROR)

        await tolerant_client.get("/boom")

        record = _api_record(caplog)
        assert record.message == "Unhandled error serving the request"
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None
        assert record.__dict__["error"] == "ValueError"


class TestRejectedRules:
    async def test_should_log_the_rejection_with_its_status(
        self, tolerant_client: AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)

        response = await tolerant_client.get("/rejected")

        assert response.status_code == 404
        record = _api_record(caplog)
        assert record.message == "A rule rejected the request"
        assert record.__dict__["error"] == "VehicleNotFoundError"
        assert record.__dict__["status_code"] == 404
