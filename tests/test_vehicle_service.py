from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from vehicle_rental_core.application.commands import VehicleChanges
from vehicle_rental_core.application.vehicle_service import VehicleService
from vehicle_rental_core.domain.enums import VehicleStatus
from vehicle_rental_core.domain.errors import (
    InvalidVehicleYearError,
    RegistrationNumberAlreadyExistsError,
    VehicleHasActiveRentalError,
    VehicleNotFoundError,
    VehicleRetiredError,
)
from vehicle_rental_core.domain.rental import Rental
from vehicle_rental_core.domain.vehicle import Vehicle
from vehicle_rental_core.infrastructure.repositories.rental_repository import (
    RentalRepository,
)
from vehicle_rental_core.infrastructure.repositories.vehicle_repository import (
    VehicleRepository,
)

NOW = datetime(2026, 6, 1, tzinfo=UTC)


@pytest.fixture
def vehicle_repository() -> AsyncMock:
    return AsyncMock(spec=VehicleRepository)


@pytest.fixture
def rental_repository() -> AsyncMock:
    return AsyncMock(spec=RentalRepository)


@pytest.fixture
def service(
    session: AsyncMock, vehicle_repository: AsyncMock, rental_repository: AsyncMock
) -> VehicleService:
    return VehicleService(
        session, vehicle_repository, rental_repository, clock=lambda: NOW
    )


def _vehicle(**overrides: object) -> Vehicle:
    defaults: dict[str, object] = {
        "registration_number": "AA-111",
        "model": "Corolla",
        "year": 2022,
    }
    return Vehicle(**{**defaults, **overrides})  # type: ignore[arg-type]


def _integrity_error(message: str) -> IntegrityError:
    return IntegrityError("INSERT", {}, Exception(message))


class TestCreateVehicle:
    async def test_should_persist_and_commit_a_new_vehicle(
        self, service: VehicleService, vehicle_repository: AsyncMock, session: AsyncMock
    ) -> None:
        vehicle_repository.get_by_registration_number.return_value = None
        vehicle_repository.add.return_value = _vehicle()

        created = await service.create(
            registration_number="AA-111", model="Corolla", year=2022
        )

        assert created.registration_number == "AA-111"
        session.commit.assert_awaited_once()

    async def test_should_reject_a_duplicate_registration_number(
        self, service: VehicleService, vehicle_repository: AsyncMock, session: AsyncMock
    ) -> None:
        vehicle_repository.get_by_registration_number.return_value = _vehicle()

        with pytest.raises(RegistrationNumberAlreadyExistsError):
            await service.create(
                registration_number="AA-111", model="Corolla", year=2022
            )

        vehicle_repository.add.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_should_check_uniqueness_against_retired_vehicles_too(
        self, service: VehicleService, vehicle_repository: AsyncMock
    ) -> None:
        # The unique index spans retired rows, and a plate lookup never hides
        # them, so a retired vehicle still holds its registration number.
        vehicle_repository.get_by_registration_number.return_value = _vehicle(
            status=VehicleStatus.RETIRED, retired_at=NOW
        )

        with pytest.raises(RegistrationNumberAlreadyExistsError):
            await service.create(registration_number="AA-111", model="C", year=2022)

    async def test_should_reject_a_plate_claimed_after_the_check(
        self, service: VehicleService, vehicle_repository: AsyncMock, session: AsyncMock
    ) -> None:
        # Another transaction won the race between our check and our insert.
        vehicle_repository.get_by_registration_number.return_value = None
        vehicle_repository.add.side_effect = _integrity_error(
            "duplicate key value violates unique constraint "
            '"ix_vehicles_registration_number"'
        )

        with pytest.raises(RegistrationNumberAlreadyExistsError):
            await service.create(
                registration_number="AA-111", model="Corolla", year=2022
            )

        session.rollback.assert_awaited_once()

    async def test_should_not_mask_an_unrelated_integrity_error(
        self, service: VehicleService, vehicle_repository: AsyncMock
    ) -> None:
        vehicle_repository.get_by_registration_number.return_value = None
        vehicle_repository.add.side_effect = _integrity_error(
            'violates check constraint "retired_status_matches_timestamp"'
        )

        with pytest.raises(IntegrityError):
            await service.create(
                registration_number="AA-111", model="Corolla", year=2022
            )


class TestGetVehicle:
    async def test_should_raise_when_the_vehicle_is_absent(
        self, service: VehicleService, vehicle_repository: AsyncMock
    ) -> None:
        vehicle_repository.get.return_value = None

        with pytest.raises(VehicleNotFoundError):
            await service.get(uuid4())


class TestRetireVehicle:
    async def test_should_retire_and_commit(
        self,
        service: VehicleService,
        vehicle_repository: AsyncMock,
        rental_repository: AsyncMock,
        session: AsyncMock,
    ) -> None:
        vehicle = _vehicle()
        vehicle_repository.get.return_value = vehicle
        rental_repository.has_active_rental_for_vehicle.return_value = False

        await service.retire(vehicle.id)

        persisted = vehicle_repository.update.await_args.args[0]
        assert persisted.status is VehicleStatus.RETIRED
        assert persisted.retired_at == NOW
        session.commit.assert_awaited_once()

    async def test_should_refuse_retiring_while_a_rental_is_active(
        self,
        service: VehicleService,
        vehicle_repository: AsyncMock,
        rental_repository: AsyncMock,
        session: AsyncMock,
    ) -> None:
        vehicle_repository.get.return_value = _vehicle()
        rental_repository.has_active_rental_for_vehicle.return_value = True

        with pytest.raises(VehicleHasActiveRentalError):
            await service.retire(uuid4())

        vehicle_repository.update.assert_not_awaited()
        session.commit.assert_not_awaited()


class TestMaintenanceTransition:
    async def test_should_refuse_maintenance_while_a_rental_is_active(
        self,
        service: VehicleService,
        vehicle_repository: AsyncMock,
        rental_repository: AsyncMock,
        session: AsyncMock,
    ) -> None:
        vehicle_repository.get.return_value = _vehicle()
        rental_repository.has_active_rental_for_vehicle.return_value = True

        with pytest.raises(VehicleHasActiveRentalError):
            await service.update(
                uuid4(), VehicleChanges(status=VehicleStatus.MAINTENANCE)
            )

        vehicle_repository.update.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_should_allow_maintenance_when_no_rental_is_active(
        self,
        service: VehicleService,
        vehicle_repository: AsyncMock,
        rental_repository: AsyncMock,
    ) -> None:
        vehicle_repository.get.return_value = _vehicle()
        rental_repository.has_active_rental_for_vehicle.return_value = False

        await service.update(uuid4(), VehicleChanges(status=VehicleStatus.MAINTENANCE))

        assert (
            vehicle_repository.update.await_args.args[0].status
            is VehicleStatus.MAINTENANCE
        )

    async def test_should_release_a_vehicle_from_maintenance(
        self,
        service: VehicleService,
        vehicle_repository: AsyncMock,
        rental_repository: AsyncMock,
    ) -> None:
        vehicle_repository.get.return_value = _vehicle(status=VehicleStatus.MAINTENANCE)
        rental_repository.has_active_rental_for_vehicle.return_value = False

        await service.update(uuid4(), VehicleChanges(status=VehicleStatus.AVAILABLE))

        updated = vehicle_repository.update.await_args.args[0]
        assert updated.status is VehicleStatus.AVAILABLE
        assert updated.retired_at is None

    async def test_should_refuse_updating_an_retired_vehicle(
        self, service: VehicleService, vehicle_repository: AsyncMock, session: AsyncMock
    ) -> None:
        retired = _vehicle(status=VehicleStatus.RETIRED, retired_at=NOW)
        vehicle_repository.get.return_value = retired

        with pytest.raises(VehicleRetiredError):
            await service.update(uuid4(), VehicleChanges(year=2024))

        vehicle_repository.update.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_should_apply_partial_field_updates(
        self, service: VehicleService, vehicle_repository: AsyncMock
    ) -> None:
        vehicle_repository.get.return_value = _vehicle(model="Corolla", year=2022)

        await service.update(uuid4(), VehicleChanges(year=2024))

        updated = vehicle_repository.update.await_args.args[0]
        assert updated.year == 2024
        assert updated.model == "Corolla"  # untouched


class TestYearValidation:
    """The rule lives in the domain, so it applies to every caller."""

    async def test_should_reject_an_implausible_year_on_create(
        self, service: VehicleService, vehicle_repository: AsyncMock, session: AsyncMock
    ) -> None:
        vehicle_repository.get_by_registration_number.return_value = None

        with pytest.raises(InvalidVehicleYearError):
            await service.create(
                registration_number="AA-111", model="Corolla", year=99999
            )

        vehicle_repository.add.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_should_reject_an_implausible_year_on_update(
        self, service: VehicleService, vehicle_repository: AsyncMock, session: AsyncMock
    ) -> None:
        vehicle_repository.get.return_value = _vehicle()

        with pytest.raises(InvalidVehicleYearError):
            await service.update(uuid4(), VehicleChanges(year=2202))

        vehicle_repository.update.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_should_accept_next_years_model(
        self, service: VehicleService, vehicle_repository: AsyncMock
    ) -> None:
        # NOW is 2026-06-01, so a 2027 model is legitimate.
        vehicle_repository.get_by_registration_number.return_value = None
        vehicle_repository.add.side_effect = lambda vehicle: vehicle

        created = await service.create(
            registration_number="AA-111", model="Corolla", year=2027
        )

        assert created.year == 2027


class TestFleetStatus:
    async def test_should_report_zero_for_a_status_the_repository_omits(
        self, service: VehicleService, vehicle_repository: AsyncMock
    ) -> None:
        # The GROUP BY returns only statuses that exist. A client rendering a
        # fixed set of tiles needs the gaps filled, not left missing.
        vehicle_repository.list.return_value = []
        vehicle_repository.count_by_status.return_value = {
            VehicleStatus.AVAILABLE: 8,
            VehicleStatus.IN_USE: 3,
        }

        fleet = await service.fleet_status()

        assert fleet.counts == {
            VehicleStatus.AVAILABLE: 8,
            VehicleStatus.IN_USE: 3,
            VehicleStatus.MAINTENANCE: 0,
            VehicleStatus.RETIRED: 0,
        }
        assert fleet.total == 11

    async def test_should_count_the_whole_fleet_regardless_of_the_page(
        self, service: VehicleService, vehicle_repository: AsyncMock
    ) -> None:
        # The counts answer "how is the fleet doing?", which is a different
        # question from "what is on this screen?".
        vehicle_repository.list.return_value = [_vehicle()]
        vehicle_repository.count_by_status.return_value = {VehicleStatus.AVAILABLE: 500}

        fleet = await service.fleet_status(limit=1)

        assert fleet.total == 500
        assert len(fleet.entries) == 1

    async def test_should_look_up_rentals_only_for_vehicles_in_use(
        self,
        service: VehicleService,
        vehicle_repository: AsyncMock,
        rental_repository: AsyncMock,
    ) -> None:
        in_use = _vehicle(registration_number="AA-222", status=VehicleStatus.IN_USE)
        available = _vehicle()
        vehicle_repository.list.return_value = [in_use, available]
        vehicle_repository.count_by_status.return_value = {}
        rental_repository.list_active_for_vehicles.return_value = []

        await service.fleet_status()

        # An available vehicle cannot have an open rental, so widening the
        # lookup would read more rows for the same answer.
        rental_repository.list_active_for_vehicles.assert_awaited_once_with([in_use.id])

    async def test_should_pair_each_vehicle_with_its_own_rental(
        self,
        service: VehicleService,
        vehicle_repository: AsyncMock,
        rental_repository: AsyncMock,
    ) -> None:
        first = _vehicle(registration_number="AA-222", status=VehicleStatus.IN_USE)
        second = _vehicle(registration_number="AA-333", status=VehicleStatus.IN_USE)
        vehicle_repository.list.return_value = [first, second]
        vehicle_repository.count_by_status.return_value = {}
        rentals = [
            Rental(vehicle_id=second.id, customer_name="Bob", start_at=NOW),
            Rental(vehicle_id=first.id, customer_name="Ada", start_at=NOW),
        ]
        rental_repository.list_active_for_vehicles.return_value = rentals

        fleet = await service.fleet_status()

        # Rentals come back in whatever order the index yields, so they are
        # matched by vehicle id rather than by position.
        assert [entry.current_rental.customer_name for entry in fleet.entries] == [  # type: ignore[union-attr]
            "Ada",
            "Bob",
        ]

    async def test_should_skip_the_rental_query_when_no_vehicle_is_in_use(
        self,
        service: VehicleService,
        vehicle_repository: AsyncMock,
        rental_repository: AsyncMock,
    ) -> None:
        vehicle_repository.list.return_value = [_vehicle()]
        vehicle_repository.count_by_status.return_value = {}
        rental_repository.list_active_for_vehicles.return_value = []

        fleet = await service.fleet_status()

        assert fleet.entries[0].current_rental is None
        rental_repository.list_active_for_vehicles.assert_awaited_once_with([])

    async def test_should_leave_the_rental_unset_when_none_comes_back(
        self,
        service: VehicleService,
        vehicle_repository: AsyncMock,
        rental_repository: AsyncMock,
    ) -> None:
        # A vehicle can read as in_use with its rental already closed by a
        # concurrent transaction. The page should still render, not blow up.
        vehicle_repository.list.return_value = [_vehicle(status=VehicleStatus.IN_USE)]
        vehicle_repository.count_by_status.return_value = {}
        rental_repository.list_active_for_vehicles.return_value = []

        fleet = await service.fleet_status()

        assert fleet.entries[0].current_rental is None

    async def test_should_not_commit(
        self,
        service: VehicleService,
        vehicle_repository: AsyncMock,
        session: AsyncMock,
    ) -> None:
        vehicle_repository.list.return_value = []
        vehicle_repository.count_by_status.return_value = {}

        await service.fleet_status()

        session.commit.assert_not_awaited()
