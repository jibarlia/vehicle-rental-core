from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from vehicle_rental_core.api.dependencies import RentalServiceDep, VehicleServiceDep
from vehicle_rental_core.application.commands import VehicleChanges
from vehicle_rental_core.domain.enums import VehicleStatus
from vehicle_rental_core.schemas.rental import ActiveRentalRead, RentalRead
from vehicle_rental_core.schemas.vehicle import (
    FleetStatusRead,
    VehicleCreate,
    VehicleRead,
    VehicleStatusRead,
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


# Must stay above GET /{vehicle_id}: FastAPI matches in declaration order.
@router.get("/status", response_model=FleetStatusRead)
async def get_fleet_status(
    vehicle_service: VehicleServiceDep,
    status_filter: Annotated[VehicleStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> FleetStatusRead:
    """The fleet at a glance: counts over every vehicle, plus one page of them.

    Counts describe the whole fleet whatever the filter; a vehicle that is out
    carries the rental explaining it.
    """
    fleet = await vehicle_service.fleet_status(
        status=status_filter, offset=offset, limit=limit
    )
    return FleetStatusRead(
        counts=dict(fleet.counts),
        total=fleet.total,
        items=[
            VehicleStatusRead(
                id=entry.vehicle.id,
                registration_number=entry.vehicle.registration_number,
                model=entry.vehicle.model,
                year=entry.vehicle.year,
                status=entry.vehicle.status,
                current_rental=(
                    ActiveRentalRead.model_validate(entry.current_rental)
                    if entry.current_rental is not None
                    else None
                ),
            )
            for entry in fleet.entries
        ],
    )


@router.get("/{vehicle_id}", response_model=VehicleRead)
async def get_vehicle(
    vehicle_id: UUID, vehicle_service: VehicleServiceDep
) -> VehicleRead:
    return VehicleRead.model_validate(await vehicle_service.get(vehicle_id))


@router.patch("/{vehicle_id}", response_model=VehicleRead)
async def update_vehicle(
    vehicle_id: UUID, payload: VehicleUpdate, vehicle_service: VehicleServiceDep
) -> VehicleRead:
    # exclude_unset keeps an omitted field distinct from one sent as null.
    changes = VehicleChanges(**payload.model_dump(exclude_unset=True))
    vehicle = await vehicle_service.update(vehicle_id, changes)
    return VehicleRead.model_validate(vehicle)


@router.post("/{vehicle_id}/retire", response_model=VehicleRead)
async def retire_vehicle(vehicle_id: UUID, service: VehicleServiceDep) -> VehicleRead:
    """Retire a vehicle from the fleet, keeping it and its rentals on record.

    The only way to remove one from service; there is deliberately no DELETE,
    because deleting cascades to the rentals. Returns 409 while a rental is
    active.
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
    # Resolve first so an unknown id is a 404, not an empty list.
    await vehicles.get(vehicle_id)
    history = await rentals.list_for_vehicle(vehicle_id, offset=offset, limit=limit)
    return [RentalRead.model_validate(rental) for rental in history]
