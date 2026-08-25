from uuid import UUID

from fastapi import APIRouter, status

from vehicle_rental_core.api.dependencies import RentalServiceDep
from vehicle_rental_core.schemas.rental import (
    RentalComplete,
    RentalCreate,
    RentalRead,
)

router = APIRouter(prefix="/rentals", tags=["rentals"])


@router.post("", response_model=RentalRead, status_code=status.HTTP_201_CREATED)
async def start_rental(
    payload: RentalCreate, rental_service: RentalServiceDep
) -> RentalRead:
    rental = await rental_service.start(
        vehicle_id=payload.vehicle_id,
        customer_name=payload.customer_name,
        start_at=payload.start_at,
    )
    return RentalRead.model_validate(rental)


@router.get("/{rental_id}", response_model=RentalRead)
async def get_rental(rental_id: UUID, rental_service: RentalServiceDep) -> RentalRead:
    return RentalRead.model_validate(await rental_service.get(rental_id))


@router.post("/{rental_id}/complete", response_model=RentalRead)
async def complete_rental(
    rental_id: UUID, payload: RentalComplete, rental_service: RentalServiceDep
) -> RentalRead:
    """Close an active rental and release the vehicle back to available."""
    rental = await rental_service.complete(rental_id, end_at=payload.end_at)
    return RentalRead.model_validate(rental)
