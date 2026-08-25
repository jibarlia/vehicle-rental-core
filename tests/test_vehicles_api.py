from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from vehicle_rental_core.api.dependencies import get_vehicle_service
from vehicle_rental_core.application.vehicle_service import VehicleService
from vehicle_rental_core.domain.enums import VehicleStatus
from vehicle_rental_core.domain.errors import (
    RegistrationNumberAlreadyExistsError,
    VehicleHasActiveRentalError,
    VehicleNotFoundError,
    VehicleRetiredError,
)
from vehicle_rental_core.domain.vehicle import Vehicle

NOW = datetime(2026, 6, 1, tzinfo=UTC)
PAYLOAD = {"registration_number": "AA-111", "model": "Corolla", "year": 2022}


@pytest.fixture
def vehicle_service() -> AsyncMock:
    return AsyncMock(spec=VehicleService)


@pytest.fixture
def client(app: FastAPI, vehicle_service: AsyncMock) -> AsyncClient:
    app.dependency_overrides[get_vehicle_service] = lambda: vehicle_service
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _vehicle(**overrides: object) -> Vehicle:
    defaults: dict[str, object] = {
        "registration_number": "AA-111",
        "model": "Corolla",
        "year": 2022,
        "created_at": NOW,
        "updated_at": NOW,
    }
    return Vehicle(**{**defaults, **overrides})  # type: ignore[arg-type]


class TestCreateVehicle:
    async def test_should_return_201_with_the_created_vehicle(
        self, client: AsyncClient, vehicle_service: AsyncMock
    ) -> None:
        vehicle_service.create.return_value = _vehicle()

        response = await client.post("/vehicles", json=PAYLOAD)

        assert response.status_code == 201
        body = response.json()
        assert body["registration_number"] == "AA-111"
        assert body["vehicle_type"] == "car"
        assert body["status"] == "available"

    async def test_should_return_409_for_a_duplicate_registration_number(
        self, client: AsyncClient, vehicle_service: AsyncMock
    ) -> None:
        vehicle_service.create.side_effect = RegistrationNumberAlreadyExistsError(
            "taken"
        )

        response = await client.post("/vehicles", json=PAYLOAD)

        assert response.status_code == 409
        assert response.json()["error"] == "RegistrationNumberAlreadyExistsError"

    @pytest.mark.parametrize(
        "bad",
        [
            {"registration_number": "", "model": "C", "year": 2022},
            {"registration_number": "AA", "model": "", "year": 2022},
            {"registration_number": "AA", "model": "C", "year": "not-a-year"},
        ],
    )
    async def test_should_reject_invalid_payloads_with_422(
        self, client: AsyncClient, bad: dict[str, object]
    ) -> None:
        response = await client.post("/vehicles", json=bad)

        assert response.status_code == 422


class TestReadVehicles:
    async def test_should_return_404_for_an_unknown_vehicle(
        self, client: AsyncClient, vehicle_service: AsyncMock
    ) -> None:
        vehicle_service.get.side_effect = VehicleNotFoundError("nope")

        response = await client.get(f"/vehicles/{uuid4()}")

        assert response.status_code == 404

    async def test_should_reject_a_malformed_uuid(self, client: AsyncClient) -> None:
        response = await client.get("/vehicles/not-a-uuid")

        assert response.status_code == 422

    async def test_should_pass_the_status_filter_through_to_the_service(
        self, client: AsyncClient, vehicle_service: AsyncMock
    ) -> None:
        vehicle_service.list.return_value = []

        response = await client.get("/vehicles?status=maintenance&limit=5")

        assert response.status_code == 200
        kwargs = vehicle_service.list.await_args.kwargs
        assert kwargs["status"] is VehicleStatus.MAINTENANCE
        assert kwargs["limit"] == 5

    async def test_should_reject_an_out_of_range_limit(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/vehicles?limit=500")

        assert response.status_code == 422


class TestRetireVehicle:
    async def test_should_return_the_retired_vehicle(
        self, client: AsyncClient, vehicle_service: AsyncMock
    ) -> None:
        vehicle_service.retire.return_value = _vehicle(
            status=VehicleStatus.RETIRED, retired_at=NOW
        )

        response = await client.post(f"/vehicles/{uuid4()}/retire")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "retired"
        assert body["retired_at"] is not None

    async def test_should_return_409_while_a_rental_is_active(
        self, client: AsyncClient, vehicle_service: AsyncMock
    ) -> None:
        vehicle_service.retire.side_effect = VehicleHasActiveRentalError("rented")

        response = await client.post(f"/vehicles/{uuid4()}/retire")

        assert response.status_code == 409
        assert response.json()["error"] == "VehicleHasActiveRentalError"

    async def test_should_return_409_when_already_retired(
        self, client: AsyncClient, vehicle_service: AsyncMock
    ) -> None:
        vehicle_service.retire.side_effect = VehicleRetiredError("already retired")

        response = await client.post(f"/vehicles/{uuid4()}/retire")

        assert response.status_code == 409

    async def test_there_should_be_no_delete_endpoint(
        self, client: AsyncClient
    ) -> None:
        # Deleting cascades to the rentals, so it is deliberately unreachable.
        response = await client.delete(f"/vehicles/{uuid4()}")

        assert response.status_code == 405


class TestUpdateVehicle:
    async def test_should_return_409_when_maintenance_is_blocked(
        self, client: AsyncClient, vehicle_service: AsyncMock
    ) -> None:
        vehicle_service.update.side_effect = VehicleHasActiveRentalError("rented")

        response = await client.patch(
            f"/vehicles/{uuid4()}", json={"status": "maintenance"}
        )

        assert response.status_code == 409

    async def test_should_apply_a_partial_update(
        self, client: AsyncClient, vehicle_service: AsyncMock
    ) -> None:
        vehicle_service.update.return_value = _vehicle(year=2024)

        response = await client.patch(f"/vehicles/{uuid4()}", json={"year": 2024})

        assert response.status_code == 200
        assert response.json()["year"] == 2024

    async def test_should_forward_only_the_fields_that_were_sent(
        self, client: AsyncClient, vehicle_service: AsyncMock
    ) -> None:
        # An omitted field must stay omitted all the way down, so the entity is
        # never handed a None that looks like a deliberate change.
        vehicle_service.update.return_value = _vehicle(year=2024)

        await client.patch(f"/vehicles/{uuid4()}", json={"year": 2024})

        changes = vehicle_service.update.await_args.args[1]
        assert changes.attributes() == {"year": 2024}
        assert changes.status is None

    async def test_should_return_422_when_the_entity_rejects_a_field(
        self, client: AsyncClient, vehicle_service: AsyncMock
    ) -> None:
        # A blank model is rejected by the entity's own constraint, so it
        # arrives as pydantic's error rather than a DomainError. Without a
        # handler for it that would be a 500.
        vehicle_service.update.side_effect = lambda *_, **__: _vehicle(model="")

        response = await client.patch(f"/vehicles/{uuid4()}", json={"model": ""})

        assert response.status_code == 422
