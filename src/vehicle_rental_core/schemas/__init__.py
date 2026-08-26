from vehicle_rental_core.schemas.customer import (
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
)
from vehicle_rental_core.schemas.rental import (
    ActiveRentalRead,
    RentalComplete,
    RentalCreate,
    RentalRead,
)
from vehicle_rental_core.schemas.vehicle import (
    FleetStatusRead,
    VehicleCreate,
    VehicleRead,
    VehicleStatusRead,
    VehicleUpdate,
)

__all__ = [
    "ActiveRentalRead",
    "CustomerCreate",
    "CustomerRead",
    "CustomerUpdate",
    "FleetStatusRead",
    "RentalComplete",
    "RentalCreate",
    "RentalRead",
    "VehicleCreate",
    "VehicleRead",
    "VehicleStatusRead",
    "VehicleUpdate",
]
