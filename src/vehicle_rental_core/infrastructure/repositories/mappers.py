"""Translation between ORM models and domain entities.

Keeping this in one place is what lets the domain stay free of SQLAlchemy and
the application layer never see a ``*Model``.
"""

from vehicle_rental_core.domain.rental import Rental
from vehicle_rental_core.domain.vehicle import Vehicle
from vehicle_rental_core.infrastructure.models.rental import RentalModel
from vehicle_rental_core.infrastructure.models.vehicle import VehicleModel


def vehicle_to_domain(model: VehicleModel) -> Vehicle:
    return Vehicle(
        id=model.id,
        vehicle_type=model.vehicle_type,
        registration_number=model.registration_number,
        model=model.model,
        year=model.year,
        status=model.status,
        retired_at=model.retired_at,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def vehicle_to_model(vehicle: Vehicle) -> VehicleModel:
    return VehicleModel(
        id=vehicle.id,
        vehicle_type=vehicle.vehicle_type,
        registration_number=vehicle.registration_number,
        model=vehicle.model,
        year=vehicle.year,
        status=vehicle.status,
        retired_at=vehicle.retired_at,
    )


def apply_vehicle(model: VehicleModel, vehicle: Vehicle) -> None:
    """Copy mutable domain state onto a loaded model.

    ``id`` and ``version`` are excluded: identity is fixed, and the version is
    owned by SQLAlchemy's optimistic-locking machinery.
    """
    model.vehicle_type = vehicle.vehicle_type
    model.registration_number = vehicle.registration_number
    model.model = vehicle.model
    model.year = vehicle.year
    model.status = vehicle.status
    model.retired_at = vehicle.retired_at


def rental_to_domain(model: RentalModel) -> Rental:
    return Rental(
        id=model.id,
        vehicle_id=model.vehicle_id,
        customer_name=model.customer_name,
        start_at=model.start_at,
        end_at=model.end_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def rental_to_model(rental: Rental) -> RentalModel:
    return RentalModel(
        id=rental.id,
        vehicle_id=rental.vehicle_id,
        customer_name=rental.customer_name,
        start_at=rental.start_at,
        end_at=rental.end_at,
    )
