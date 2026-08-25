from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from vehicle_rental_core.api.dependencies import RentalServiceDep, VehicleServiceDep
from vehicle_rental_core.application.commands import VehicleChanges
from vehicle_rental_core.domain.enums import VehicleStatus
from vehicle_rental_core.schemas.rental import RentalRead
from vehicle_rental_core.schemas.vehicle import (
    VehicleCreate,
    VehicleRead,
    VehicleUpdate,
)

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.post("", response_model=VehicleRead, status_code=status.HTTP_201_CREATED)
async def create_vehicle(
    payload: VehicleCreate, vehicle_service: VehicleServiceDep
) -> VehicleRead:
    vehicle = await vehicle_service.create(
        registration_number=payload.registration_number,
        model=payload.model,
        year=payload.year,
        vehicle_type=payload.vehicle_type,
    )
    return VehicleRead.model_validate(vehicle)


@router.get("", response_model=list[VehicleRead])
async def list_vehicles(
    vehicle_service: VehicleServiceDep,
    status_filter: Annotated[VehicleStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[VehicleRead]:
    vehicles = await vehicle_service.list(
        status=status_filter, offset=offset, limit=limit
    )
    return [VehicleRead.model_validate(vehicle) for vehicle in vehicles]


@router.get("/{vehicle_id}", response_model=VehicleRead)
async def get_vehicle(
    vehicle_id: UUID, vehicle_service: VehicleServiceDep
) -> VehicleRead:
    return VehicleRead.model_validate(await vehicle_service.get(vehicle_id))


@router.patch("/{vehicle_id}", response_model=VehicleRead)
async def update_vehicle(
    vehicle_id: UUID, payload: VehicleUpdate, vehicle_service: VehicleServiceDep
) -> VehicleRead:
    # Built from what the client actually sent, so an omitted field stays
    # omitted all the way down instead of arriving as an indistinguishable None.
    changes = VehicleChanges(**payload.model_dump(exclude_unset=True))
    vehicle = await vehicle_service.update(vehicle_id, changes)
    return VehicleRead.model_validate(vehicle)


@router.post("/{vehicle_id}/retire", response_model=VehicleRead)
async def retire_vehicle(vehicle_id: UUID, service: VehicleServiceDep) -> VehicleRead:
    """Retire a vehicle from the fleet, keeping it and its rentals on record.

    The only way to remove a vehicle from service — there is deliberately no
    endpoint that deletes one, because deleting cascades to its rentals.
    Rejected with 409 while a rental is active.
    """
    return VehicleRead.model_validate(await service.retire(vehicle_id))


@router.get("/{vehicle_id}/rentals", response_model=list[RentalRead])
async def list_vehicle_rentals(
    vehicle_id: UUID,
    vehicles: VehicleServiceDep,
    rentals: RentalServiceDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[RentalRead]:
    # Resolve the vehicle first so a deleted or unknown id is a 404 rather than
    # an empty list that looks like "no rentals".
    await vehicles.get(vehicle_id)
    history = await rentals.list_for_vehicle(vehicle_id, offset=offset, limit=limit)
    return [RentalRead.model_validate(rental) for rental in history]
