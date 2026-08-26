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


# Declared above GET /{vehicle_id} on purpose: FastAPI matches routes in
# declaration order, so below it the literal "status" would be swallowed by the
# UUID path param and answered with a puzzling 422. Keep this handler first.
@router.get("/status", response_model=FleetStatusRead)
async def get_fleet_status(
    vehicle_service: VehicleServiceDep,
    status_filter: Annotated[VehicleStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> FleetStatusRead:
    """The fleet at a glance: counts over every vehicle, plus one page of them.

    The counts describe the whole fleet whatever the filter and page are, so
    "how many are available?" is answerable without walking the table. A vehicle
    that is out carries the rental explaining it, which is what saves a caller
    from asking each one in turn.
    """
    fleet = await vehicle_service.fleet_status(
        status=status_filter, offset=offset, limit=limit
    )
    return FleetStatusRead(
        counts=dict(fleet.counts),
        total=fleet.total,
        items=[
            # Built field by field rather than validated off the entry: the row
            # is a chosen subset, and current_rental comes from a second object.
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
