import logging
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from vehicle_rental_core.application.rental_service import RentalService
from vehicle_rental_core.domain.customer import Customer
from vehicle_rental_core.domain.enums import VehicleStatus
from vehicle_rental_core.domain.errors import (
    CustomerNotFoundError,
    InvalidRentalPeriodError,
    RentalNotFoundError,
    VehicleHasActiveRentalError,
    VehicleNotFoundError,
    VehicleNotRentableError,
)
from vehicle_rental_core.domain.rental import Rental
from vehicle_rental_core.domain.vehicle import Vehicle
from vehicle_rental_core.infrastructure.repositories.customer_repository import (
    CustomerRepository,
)
from vehicle_rental_core.infrastructure.repositories.rental_repository import (
    RentalRepository,
)
from vehicle_rental_core.infrastructure.repositories.vehicle_repository import (
    VehicleRepository,
)

NOW = datetime(2026, 6, 1, tzinfo=UTC)


@pytest.fixture
def rental_repository() -> AsyncMock:
    return AsyncMock(spec=RentalRepository)


@pytest.fixture
def vehicle_repository() -> AsyncMock:
    return AsyncMock(spec=VehicleRepository)


@pytest.fixture
def customer_repository() -> AsyncMock:
    repository = AsyncMock(spec=CustomerRepository)
    repository.get.return_value = _customer()
    return repository


@pytest.fixture
def service(
    session: AsyncMock,
    rental_repository: AsyncMock,
    vehicle_repository: AsyncMock,
    customer_repository: AsyncMock,
) -> RentalService:
    return RentalService(
        session,
        rental_repository,
        vehicle_repository,
        customer_repository,
        clock=lambda: NOW,
    )


def _vehicle(**overrides: object) -> Vehicle:
    defaults: dict[str, object] = {
        "registration_number": "AA-111",
        "model": "Corolla",
        "year": 2022,
    }
    return Vehicle(**{**defaults, **overrides})  # type: ignore[arg-type]


def _customer(**overrides: object) -> Customer:
    defaults: dict[str, object] = {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "date_of_birth": date(1990, 6, 1),
    }
    return Customer(**{**defaults, **overrides})  # type: ignore[arg-type]


def _integrity_error(message: str) -> IntegrityError:
    return IntegrityError("INSERT", {}, Exception(message))


class TestStartRental:
    async def test_should_open_a_rental_and_mark_the_vehicle_in_use(
        self,
        service: RentalService,
        vehicle_repository: AsyncMock,
        rental_repository: AsyncMock,
        session: AsyncMock,
    ) -> None:
        vehicle = _vehicle()
        vehicle_repository.get.return_value = vehicle
        rental_repository.add.side_effect = lambda rental: rental

        created = await service.start(vehicle_id=vehicle.id, customer_id=uuid4())

        assert created.is_active is True
        assert created.start_at == NOW  # clock supplies the default
        assert (
            vehicle_repository.update.await_args.args[0].status is VehicleStatus.IN_USE
        )
        session.commit.assert_awaited_once()

    async def test_should_reject_a_rental_starting_in_the_future(
        self,
        service: RentalService,
        vehicle_repository: AsyncMock,
        rental_repository: AsyncMock,
        session: AsyncMock,
    ) -> None:
        # The entity rejects it; what matters here is that nothing was written
        # first, since the vehicle is marked in_use after the rental is built.
        vehicle_repository.get.return_value = _vehicle()

        with pytest.raises(InvalidRentalPeriodError):
            await service.start(
                vehicle_id=uuid4(),
                customer_id=uuid4(),
                start_at=datetime.now(UTC) + timedelta(days=1),
            )

        vehicle_repository.update.assert_not_awaited()
        rental_repository.add.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_should_accept_a_backdated_start(
        self,
        service: RentalService,
        vehicle_repository: AsyncMock,
        rental_repository: AsyncMock,
    ) -> None:
        # Recording a rental that already ran stays supported; only the future
        # is refused.
        backdated = NOW - timedelta(days=3)
        vehicle_repository.get.return_value = _vehicle()
        rental_repository.add.side_effect = lambda rental: rental

        created = await service.start(
            vehicle_id=uuid4(), customer_id=uuid4(), start_at=backdated
        )

        assert created.start_at == backdated

    async def test_should_snapshot_the_customer_name_onto_the_rental(
        self,
        service: RentalService,
        vehicle_repository: AsyncMock,
        rental_repository: AsyncMock,
        customer_repository: AsyncMock,
    ) -> None:
        # Copied, not referenced, so it survives a rename or delete.
        customer = _customer(name="Grace Hopper")
        customer_repository.get.return_value = customer
        vehicle_repository.get.return_value = _vehicle()
        rental_repository.add.side_effect = lambda rental: rental

        created = await service.start(vehicle_id=uuid4(), customer_id=customer.id)

        assert created.customer_id == customer.id
        assert created.customer_name == "Grace Hopper"

    async def test_should_reject_an_unknown_customer(
        self,
        service: RentalService,
        vehicle_repository: AsyncMock,
        rental_repository: AsyncMock,
        customer_repository: AsyncMock,
    ) -> None:
        vehicle_repository.get.return_value = _vehicle()
        customer_repository.get.return_value = None

        with pytest.raises(CustomerNotFoundError):
            await service.start(vehicle_id=uuid4(), customer_id=uuid4())

        rental_repository.add.assert_not_awaited()

    async def test_should_reject_an_unknown_vehicle(
        self, service: RentalService, vehicle_repository: AsyncMock
    ) -> None:
        vehicle_repository.get.return_value = None

        with pytest.raises(VehicleNotFoundError):
            await service.start(vehicle_id=uuid4(), customer_id=uuid4())

    @pytest.mark.parametrize(
        "status",
        [
            VehicleStatus.IN_USE,
            VehicleStatus.MAINTENANCE,
            VehicleStatus.RETIRED,
        ],
    )
    async def test_should_reject_a_vehicle_that_is_not_available(
        self,
        service: RentalService,
        vehicle_repository: AsyncMock,
        status: VehicleStatus,
    ) -> None:
        vehicle_repository.get.return_value = _vehicle(status=status)

        with pytest.raises(VehicleNotRentableError):
            await service.start(vehicle_id=uuid4(), customer_id=uuid4())

    async def test_should_translate_the_partial_index_violation_into_a_conflict(
        self,
        service: RentalService,
        vehicle_repository: AsyncMock,
        rental_repository: AsyncMock,
        session: AsyncMock,
    ) -> None:
        # Another transaction won the race between our check and our insert.
        vehicle_repository.get.return_value = _vehicle()
        rental_repository.add.side_effect = _integrity_error(
            "duplicate key value violates unique constraint "
            '"uq_rentals_one_active_per_vehicle"'
        )

        with pytest.raises(VehicleHasActiveRentalError):
            await service.start(vehicle_id=uuid4(), customer_id=uuid4())

        session.rollback.assert_awaited_once()

    async def test_should_not_mask_an_unrelated_integrity_error(
        self,
        service: RentalService,
        vehicle_repository: AsyncMock,
        rental_repository: AsyncMock,
    ) -> None:
        vehicle_repository.get.return_value = _vehicle()
        rental_repository.add.side_effect = _integrity_error(
            'violates foreign key constraint "fk_rentals_vehicle_id_vehicles"'
        )

        with pytest.raises(IntegrityError):
            await service.start(vehicle_id=uuid4(), customer_id=uuid4())


class TestCompleteRental:
    async def test_should_close_the_rental_and_release_the_vehicle(
        self,
        service: RentalService,
        rental_repository: AsyncMock,
        vehicle_repository: AsyncMock,
        session: AsyncMock,
    ) -> None:
        vehicle = _vehicle(status=VehicleStatus.IN_USE)
        rental = Rental(vehicle_id=vehicle.id, customer_name="Ada", start_at=NOW)
        rental_repository.get.return_value = rental
        rental_repository.update.side_effect = lambda updated: updated
        vehicle_repository.get.return_value = vehicle

        closed = await service.complete(rental.id)

        assert closed.end_at == NOW
        assert (
            vehicle_repository.update.await_args.args[0].status
            is VehicleStatus.AVAILABLE
        )
        session.commit.assert_awaited_once()

    async def test_should_reject_an_unknown_rental(
        self, service: RentalService, rental_repository: AsyncMock
    ) -> None:
        rental_repository.get.return_value = None

        with pytest.raises(RentalNotFoundError):
            await service.complete(uuid4())

    async def test_should_not_touch_a_vehicle_that_is_not_in_use(
        self,
        service: RentalService,
        rental_repository: AsyncMock,
        vehicle_repository: AsyncMock,
    ) -> None:
        # A vehicle already in maintenance must not be silently freed.
        vehicle = _vehicle(status=VehicleStatus.MAINTENANCE)
        rental = Rental(vehicle_id=vehicle.id, customer_name="Ada", start_at=NOW)
        rental_repository.get.return_value = rental
        rental_repository.update.side_effect = lambda updated: updated
        vehicle_repository.get.return_value = vehicle

        await service.complete(rental.id)

        vehicle_repository.update.assert_not_awaited()


class TestAuditLogging:
    async def test_should_log_a_started_rental(
        self,
        service: RentalService,
        vehicle_repository: AsyncMock,
        rental_repository: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level(logging.INFO)
        vehicle = _vehicle()
        vehicle_repository.get.return_value = vehicle
        rental_repository.add.side_effect = lambda rental: rental

        created = await service.start(vehicle_id=vehicle.id, customer_id=uuid4())

        record = caplog.records[-1]
        assert record.message == "Rental started"
        assert record.__dict__["rental_id"] == str(created.id)
        assert record.__dict__["vehicle_id"] == str(vehicle.id)
        assert record.__dict__["customer_id"] == str(created.customer_id)

    async def test_should_log_a_completed_rental(
        self,
        service: RentalService,
        rental_repository: AsyncMock,
        vehicle_repository: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level(logging.INFO)
        vehicle = _vehicle(status=VehicleStatus.IN_USE)
        rental = Rental(vehicle_id=vehicle.id, customer_name="Ada", start_at=NOW)
        rental_repository.get.return_value = rental
        rental_repository.update.side_effect = lambda updated: updated
        vehicle_repository.get.return_value = vehicle

        await service.complete(rental.id)

        record = caplog.records[-1]
        assert record.message == "Rental completed"
        assert record.__dict__["rental_id"] == str(rental.id)
        assert record.__dict__["vehicle_id"] == str(vehicle.id)
        assert record.__dict__["end_at"] == NOW.isoformat()

    async def test_should_not_log_a_rejected_start(
        self,
        service: RentalService,
        vehicle_repository: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level(logging.INFO)
        vehicle_repository.get.return_value = None

        with pytest.raises(VehicleNotFoundError):
            await service.start(vehicle_id=uuid4(), customer_id=uuid4())

        assert caplog.records == []
