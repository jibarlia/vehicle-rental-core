from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from vehicle_rental_core.api.dependencies import get_rental_service
from vehicle_rental_core.application.rental_service import RentalService
from vehicle_rental_core.domain.errors import (
    CustomerNotFoundError,
    InvalidRentalPeriodError,
    RentalAlreadyEndedError,
    RentalNotFoundError,
    VehicleHasActiveRentalError,
    VehicleNotRentableError,
)
from vehicle_rental_core.domain.rental import Rental

NOW = datetime(2026, 6, 1, tzinfo=UTC)
VEHICLE_ID = uuid4()
CUSTOMER_ID = uuid4()


@pytest.fixture
def rental_service() -> AsyncMock:
    return AsyncMock(spec=RentalService)


@pytest.fixture
def client(app: FastAPI, rental_service: AsyncMock) -> AsyncClient:
    app.dependency_overrides[get_rental_service] = lambda: rental_service
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _rental(**overrides: object) -> Rental:
    defaults: dict[str, object] = {
        "vehicle_id": VEHICLE_ID,
        "customer_id": CUSTOMER_ID,
        "customer_name": "Ada Lovelace",
        "start_at": NOW,
        "created_at": NOW,
        "updated_at": NOW,
    }
    return Rental(**{**defaults, **overrides})  # type: ignore[arg-type]


class TestStartRental:
    async def test_should_return_201_with_an_open_rental(
        self, client: AsyncClient, rental_service: AsyncMock
    ) -> None:
        rental_service.start.return_value = _rental()

        response = await client.post(
            "/rentals",
            json={"vehicle_id": str(VEHICLE_ID), "customer_id": str(CUSTOMER_ID)},
        )

        assert response.status_code == 201
        assert response.json()["end_at"] is None

    async def test_should_return_409_when_the_vehicle_is_already_rented(
        self, client: AsyncClient, rental_service: AsyncMock
    ) -> None:
        rental_service.start.side_effect = VehicleHasActiveRentalError("busy")

        response = await client.post(
            "/rentals",
            json={"vehicle_id": str(VEHICLE_ID), "customer_id": str(CUSTOMER_ID)},
        )

        assert response.status_code == 409
        assert response.json()["error"] == "VehicleHasActiveRentalError"

    async def test_should_return_409_when_the_vehicle_is_in_maintenance(
        self, client: AsyncClient, rental_service: AsyncMock
    ) -> None:
        rental_service.start.side_effect = VehicleNotRentableError("maintenance")

        response = await client.post(
            "/rentals",
            json={"vehicle_id": str(VEHICLE_ID), "customer_id": str(CUSTOMER_ID)},
        )

        assert response.status_code == 409

    async def test_should_reject_a_malformed_customer_id(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/rentals", json={"vehicle_id": str(VEHICLE_ID), "customer_id": "nope"}
        )

        assert response.status_code == 422

    async def test_should_return_404_for_an_unknown_customer(
        self, client: AsyncClient, rental_service: AsyncMock
    ) -> None:
        rental_service.start.side_effect = CustomerNotFoundError("nope")

        response = await client.post(
            "/rentals",
            json={"vehicle_id": str(VEHICLE_ID), "customer_id": str(CUSTOMER_ID)},
        )

        assert response.status_code == 404
        assert response.json()["error"] == "CustomerNotFoundError"


class TestCompleteRental:
    async def test_should_return_the_closed_rental(
        self, client: AsyncClient, rental_service: AsyncMock
    ) -> None:
        ended = datetime(2026, 6, 5, tzinfo=UTC)
        rental_service.complete.return_value = _rental(end_at=ended)

        response = await client.post(f"/rentals/{uuid4()}/complete", json={})

        assert response.status_code == 200
        # Pydantic renders UTC as "Z"; compare instants, not spellings.
        assert datetime.fromisoformat(response.json()["end_at"]) == ended

    async def test_should_complete_without_a_body(
        self, client: AsyncClient, rental_service: AsyncMock
    ) -> None:
        rental_service.complete.return_value = _rental(end_at=NOW)

        response = await client.post(f"/rentals/{uuid4()}/complete")

        assert response.status_code == 200
        assert rental_service.complete.await_args.kwargs["end_at"] is None

    async def test_should_still_accept_an_explicit_end_at(
        self, client: AsyncClient, rental_service: AsyncMock
    ) -> None:
        ended = datetime(2026, 6, 5, tzinfo=UTC)
        rental_service.complete.return_value = _rental(end_at=ended)

        response = await client.post(
            f"/rentals/{uuid4()}/complete", json={"end_at": ended.isoformat()}
        )

        assert response.status_code == 200
        assert rental_service.complete.await_args.kwargs["end_at"] == ended

    async def test_should_return_422_for_a_naive_end_at(
        self, client: AsyncClient, rental_service: AsyncMock
    ) -> None:
        response = await client.post(
            f"/rentals/{uuid4()}/complete", json={"end_at": "2026-06-05T10:00:00"}
        )

        assert response.status_code == 422
        rental_service.complete.assert_not_awaited()

    async def test_should_return_404_for_an_unknown_rental(
        self, client: AsyncClient, rental_service: AsyncMock
    ) -> None:
        rental_service.complete.side_effect = RentalNotFoundError("nope")

        response = await client.post(f"/rentals/{uuid4()}/complete", json={})

        assert response.status_code == 404

    async def test_should_return_409_when_the_rental_already_ended(
        self, client: AsyncClient, rental_service: AsyncMock
    ) -> None:
        rental_service.complete.side_effect = RentalAlreadyEndedError("done")

        response = await client.post(f"/rentals/{uuid4()}/complete", json={})

        assert response.status_code == 409

    async def test_should_return_422_when_end_precedes_start(
        self, client: AsyncClient, rental_service: AsyncMock
    ) -> None:
        rental_service.complete.side_effect = InvalidRentalPeriodError("before start")

        response = await client.post(
            f"/rentals/{uuid4()}/complete", json={"end_at": "2020-01-01T00:00:00Z"}
        )

        assert response.status_code == 422
