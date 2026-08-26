from datetime import UTC, date, datetime
from uuid import uuid4

from vehicle_rental_core.domain.customer import Customer
from vehicle_rental_core.domain.enums import Sex, VehicleStatus, VehicleType
from vehicle_rental_core.domain.rental import Rental
from vehicle_rental_core.domain.vehicle import Vehicle
from vehicle_rental_core.infrastructure.models.rental import RentalModel
from vehicle_rental_core.infrastructure.models.vehicle import VehicleModel
from vehicle_rental_core.infrastructure.repositories.mappers import (
    apply_customer,
    apply_vehicle,
    customer_to_domain,
    customer_to_model,
    rental_to_domain,
    rental_to_model,
    vehicle_to_domain,
    vehicle_to_model,
)

NOW = datetime(2026, 6, 1, tzinfo=UTC)


class TestVehicleMapping:
    def test_should_round_trip_every_field(self) -> None:
        original = Vehicle(
            registration_number="AA-111",
            model="Corolla",
            year=2022,
            vehicle_type=VehicleType.CAR,
            status=VehicleStatus.MAINTENANCE,
            retired_at=NOW,
        )

        model = vehicle_to_model(original)
        # A fresh model has no server-assigned version; supply it as the DB would.
        model.version = original.version
        restored = vehicle_to_domain(model)

        assert restored.id == original.id
        assert restored.registration_number == original.registration_number
        assert restored.model == original.model
        assert restored.year == original.year
        assert restored.vehicle_type is original.vehicle_type
        assert restored.status is original.status
        assert restored.retired_at == original.retired_at

    def test_apply_should_copy_mutable_state_onto_a_loaded_model(self) -> None:
        model = VehicleModel(
            id=uuid4(),
            registration_number="AA-111",
            model="Corolla",
            year=2022,
            vehicle_type=VehicleType.CAR,
            status=VehicleStatus.AVAILABLE,
            retired_at=None,
        )
        # The default applies at flush, so supply it as the database would.
        model.version = 1
        vehicle = vehicle_to_domain(model)
        vehicle.status = VehicleStatus.MAINTENANCE
        vehicle.year = 2024
        vehicle.retired_at = NOW

        apply_vehicle(model, vehicle)

        assert model.status is VehicleStatus.MAINTENANCE
        assert model.year == 2024
        assert model.retired_at == NOW

    def test_apply_should_not_touch_identity_or_version(self) -> None:
        original_id = uuid4()
        model = VehicleModel(
            id=original_id,
            registration_number="AA-111",
            model="Corolla",
            year=2022,
            vehicle_type=VehicleType.CAR,
            status=VehicleStatus.AVAILABLE,
        )
        model.version = 7
        vehicle = vehicle_to_domain(model)
        vehicle.id = uuid4()
        vehicle.version = 99

        apply_vehicle(model, vehicle)

        # Identity is fixed and the version belongs to SQLAlchemy's locking.
        assert model.id == original_id
        assert model.version == 7


class TestRentalMapping:
    def test_should_round_trip_every_field(self) -> None:
        original = Rental(
            vehicle_id=uuid4(),
            customer_id=uuid4(),
            customer_name="Ada Lovelace",
            start_at=NOW,
            end_at=None,
        )

        restored = rental_to_domain(rental_to_model(original))

        assert restored.id == original.id
        assert restored.vehicle_id == original.vehicle_id
        assert restored.customer_id == original.customer_id
        assert restored.customer_name == original.customer_name
        assert restored.start_at == original.start_at
        assert restored.end_at is None
        assert restored.is_active is True

    def test_should_preserve_a_closed_period(self) -> None:
        ended = datetime(2026, 6, 5, tzinfo=UTC)
        original = Rental(
            vehicle_id=uuid4(),
            customer_name="Ada",
            start_at=NOW,
            end_at=ended,
        )

        restored = rental_to_domain(rental_to_model(original))

        assert restored.end_at == ended
        assert restored.is_active is False

    def test_model_should_not_carry_timestamps_the_database_owns(self) -> None:
        model: RentalModel = rental_to_model(
            Rental(vehicle_id=uuid4(), customer_name="Ada", start_at=NOW)
        )

        # created_at/updated_at come from server defaults, never from Python.
        assert model.created_at is None

    def test_should_keep_the_name_when_the_customer_id_is_gone(self) -> None:
        # What a deleted customer leaves: SET NULL wiped the id, snapshot stays.
        orphaned = Rental(
            vehicle_id=uuid4(),
            customer_id=None,
            customer_name="Ada Lovelace",
            start_at=NOW,
        )

        restored = rental_to_domain(rental_to_model(orphaned))

        assert restored.customer_id is None
        assert restored.customer_name == "Ada Lovelace"


class TestCustomerMapping:
    def test_should_round_trip_every_field(self) -> None:
        original = Customer(
            name="Ada Lovelace",
            email="ada@example.com",
            date_of_birth=date(1990, 6, 1),
            sex=Sex.FEMALE,
        )

        restored = customer_to_domain(customer_to_model(original))

        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.email == original.email
        assert restored.date_of_birth == original.date_of_birth
        assert restored.sex is Sex.FEMALE

    def test_apply_should_copy_mutable_state_but_not_identity(self) -> None:
        model = customer_to_model(
            Customer(
                name="Ada",
                email="ada@example.com",
                date_of_birth=date(1990, 6, 1),
            )
        )
        original_id = model.id

        apply_customer(
            model,
            Customer(
                name="Grace Hopper",
                email="grace@example.com",
                date_of_birth=date(1906, 12, 9),
                sex=Sex.FEMALE,
            ),
        )

        assert model.name == "Grace Hopper"
        assert model.email == "grace@example.com"
        assert model.id == original_id

    def test_model_should_not_carry_timestamps_the_database_owns(self) -> None:
        model = customer_to_model(
            Customer(
                name="Ada",
                email="ada@example.com",
                date_of_birth=date(1990, 6, 1),
            )
        )

        assert model.created_at is None
        assert model.updated_at is None
