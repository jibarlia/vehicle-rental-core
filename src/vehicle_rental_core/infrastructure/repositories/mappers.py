"""Translation between ORM models and domain entities, kept in one place so
the domain stays free of SQLAlchemy."""

from vehicle_rental_core.domain.customer import Customer
from vehicle_rental_core.domain.rental import Rental
from vehicle_rental_core.domain.vehicle import Vehicle
from vehicle_rental_core.infrastructure.models.customer import CustomerModel
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

    ``id`` and ``version`` are excluded; SQLAlchemy owns the version.
    """
    model.vehicle_type = vehicle.vehicle_type
    model.registration_number = vehicle.registration_number
    model.model = vehicle.model
    model.year = vehicle.year
    model.status = vehicle.status
    model.retired_at = vehicle.retired_at


def customer_to_domain(model: CustomerModel) -> Customer:
    return Customer(
        id=model.id,
        name=model.name,
        email=model.email,
        date_of_birth=model.date_of_birth,
        sex=model.sex,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def customer_to_model(customer: Customer) -> CustomerModel:
    return CustomerModel(
        id=customer.id,
        name=customer.name,
        email=customer.email,
        date_of_birth=customer.date_of_birth,
        sex=customer.sex,
    )


def apply_customer(model: CustomerModel, customer: Customer) -> None:
    """Copy mutable domain state onto a loaded model. Identity is fixed."""
    model.name = customer.name
    model.email = customer.email
    model.date_of_birth = customer.date_of_birth
    model.sex = customer.sex


def rental_to_domain(model: RentalModel) -> Rental:
    return Rental(
        id=model.id,
        vehicle_id=model.vehicle_id,
        customer_id=model.customer_id,
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
        customer_id=rental.customer_id,
        customer_name=rental.customer_name,
        start_at=rental.start_at,
        end_at=rental.end_at,
    )
