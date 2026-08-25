from datetime import UTC, datetime
from uuid import uuid4

from vehicle_rental_core.domain.enums import VehicleStatus, VehicleType
from vehicle_rental_core.domain.rental import Rental
from vehicle_rental_core.domain.vehicle import Vehicle
from vehicle_rental_core.infrastructure.models.rental import RentalModel
from vehicle_rental_core.infrastructure.models.vehicle import VehicleModel
from vehicle_rental_core.infrastructure.repositories.mappers import (
    apply_vehicle,
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
        # A fresh model has no server-assigned version yet; supply it as the
        # database would after a flush.
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
        # The column default is applied at flush, so an unflushed model has no
        # version yet; supply it as the database would.
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
            customer_name="Ada Lovelace",
            start_at=NOW,
            end_at=None,
        )

        restored = rental_to_domain(rental_to_model(original))

        assert restored.id == original.id
        assert restored.vehicle_id == original.vehicle_id
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
        assert model.updated_at is None
