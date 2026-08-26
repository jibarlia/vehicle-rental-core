from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from vehicle_rental_core.api.dependencies import get_vehicle_service
from vehicle_rental_core.application.vehicle_service import VehicleService
from vehicle_rental_core.application.views import FleetStatus, VehicleStatusEntry
from vehicle_rental_core.domain.enums import VehicleStatus
from vehicle_rental_core.domain.errors import (
    RegistrationNumberAlreadyExistsError,
    VehicleHasActiveRentalError,
    VehicleNotFoundError,
    VehicleRetiredError,
)
from vehicle_rental_core.domain.rental import Rental
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


class TestFleetStatus:
    @staticmethod
    def _fleet(*entries: VehicleStatusEntry, **counts: int) -> FleetStatus:
        tally = {member: counts.get(member.value, 0) for member in VehicleStatus}
        return FleetStatus(
            counts=tally, total=sum(tally.values()), entries=list(entries)
        )

    async def test_should_return_counts_for_every_status_including_zeroes(
        self, client: AsyncClient, vehicle_service: AsyncMock
    ) -> None:
        vehicle_service.fleet_status.return_value = self._fleet(available=8, in_use=3)

        response = await client.get("/vehicles/status")

        assert response.status_code == 200
        body = response.json()
        # A client renders a fixed set of tiles, so a status with no vehicles
        # must report 0 rather than go missing.
        assert body["counts"] == {
            "available": 8,
            "in_use": 3,
            "maintenance": 0,
            "retired": 0,
        }
        assert body["total"] == 11

    async def test_should_carry_a_retired_vehicle_in_items(
        self, client: AsyncClient, vehicle_service: AsyncMock
    ) -> None:
        # The status view reports on the fleet, and a report that silently drops
        # part of its population is a report that misleads.
        retired = _vehicle(status=VehicleStatus.RETIRED, retired_at=NOW)
        vehicle_service.fleet_status.return_value = self._fleet(
            VehicleStatusEntry(vehicle=retired), retired=1
        )

        response = await client.get("/vehicles/status")

        body = response.json()
        assert [item["status"] for item in body["items"]] == ["retired"]
        # And the total counts it, so it does not promise fewer rows than
        # paging delivers.
        assert body["total"] == 1

    async def test_should_nest_the_active_rental_under_a_vehicle_in_use(
        self, client: AsyncClient, vehicle_service: AsyncMock
    ) -> None:
        vehicle = _vehicle(status=VehicleStatus.IN_USE)
        rental = Rental(
            vehicle_id=vehicle.id,
            customer_id=uuid4(),
            customer_name="Dana Levi",
            start_at=NOW,
        )
        vehicle_service.fleet_status.return_value = self._fleet(
            VehicleStatusEntry(vehicle=vehicle, current_rental=rental), in_use=1
        )

        response = await client.get("/vehicles/status")

        item = response.json()["items"][0]
        assert item["status"] == "in_use"
        assert item["current_rental"] == {
            "id": str(rental.id),
            "customer_id": str(rental.customer_id),
            "customer_name": "Dana Levi",
            "start_at": "2026-06-01T00:00:00Z",
        }

    async def test_should_leave_current_rental_null_for_a_vehicle_not_in_use(
        self, client: AsyncClient, vehicle_service: AsyncMock
    ) -> None:
        vehicle_service.fleet_status.return_value = self._fleet(
            VehicleStatusEntry(vehicle=_vehicle()), available=1
        )

        response = await client.get("/vehicles/status")

        assert response.json()["items"][0]["current_rental"] is None

    async def test_should_omit_the_fields_a_status_board_does_not_display(
        self, client: AsyncClient, vehicle_service: AsyncMock
    ) -> None:
        # Pinned deliberately: these ride along on every row of every page and
        # are shown on none, so the row must not quietly re-fatten.
        vehicle_service.fleet_status.return_value = self._fleet(
            VehicleStatusEntry(vehicle=_vehicle()), available=1
        )

        response = await client.get("/vehicles/status")

        item = response.json()["items"][0]
        assert set(item) == {
            "id",
            "registration_number",
            "model",
            "year",
            "status",
            "current_rental",
        }

    async def test_should_pass_the_status_filter_through_to_the_service(
        self, client: AsyncClient, vehicle_service: AsyncMock
    ) -> None:
        vehicle_service.fleet_status.return_value = self._fleet()

        response = await client.get("/vehicles/status?status=maintenance&limit=5")

        assert response.status_code == 200
        kwargs = vehicle_service.fleet_status.await_args.kwargs
        assert kwargs["status"] is VehicleStatus.MAINTENANCE
        assert kwargs["limit"] == 5

    async def test_should_reject_an_out_of_range_limit(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/vehicles/status?limit=500")

        assert response.status_code == 422

    async def test_should_route_status_to_the_fleet_handler_not_get_vehicle(
        self, client: AsyncClient, vehicle_service: AsyncMock
    ) -> None:
        # FastAPI matches in declaration order. Were this route declared after
        # GET /{vehicle_id}, "status" would be read as a vehicle id and fail
        # with a 422 that points nowhere near the real cause.
        vehicle_service.fleet_status.return_value = self._fleet()

        response = await client.get("/vehicles/status")

        assert response.status_code == 200
        vehicle_service.fleet_status.assert_awaited_once()
        vehicle_service.get.assert_not_awaited()
