from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from vehicle_rental_core.application.clock import Clock, utcnow
from vehicle_rental_core.domain.enums import VehicleStatus
from vehicle_rental_core.domain.errors import (
    CustomerNotFoundError,
    RentalNotFoundError,
    VehicleHasActiveRentalError,
    VehicleNotFoundError,
    VehicleNotRentableError,
)
from vehicle_rental_core.domain.rental import Rental
from vehicle_rental_core.infrastructure.repositories.customer_repository import (
    CustomerRepository,
)
from vehicle_rental_core.infrastructure.repositories.rental_repository import (
    RentalRepository,
)
from vehicle_rental_core.infrastructure.repositories.vehicle_repository import (
    VehicleRepository,
)

_ACTIVE_RENTAL_INDEX = "uq_rentals_one_active_per_vehicle"


class RentalService:
    """Rental use cases, including the vehicle status transitions they drive."""

    def __init__(
        self,
        session: AsyncSession,
        rental_repository: RentalRepository,
        vehicle_repository: VehicleRepository,
        customer_repository: CustomerRepository,
        clock: Clock = utcnow,
    ) -> None:
        self._session = session
        self._rental_repository = rental_repository
        self._vehicle_repository = vehicle_repository
        self._customer_repository = customer_repository
        self._clock = clock

    async def start(
        self,
        *,
        vehicle_id: UUID,
        customer_id: UUID,
        start_at: datetime | None = None,
    ) -> Rental:
        vehicle = await self._vehicle_repository.get(vehicle_id)
        if vehicle is None:
            raise VehicleNotFoundError(f"Vehicle {vehicle_id} not found.")

        if not vehicle.is_rentable:
            raise VehicleNotRentableError(
                f"Vehicle {vehicle_id} is {vehicle.status}, not available."
            )

        customer = await self._customer_repository.get(customer_id)
        if customer is None:
            raise CustomerNotFoundError(f"Customer {customer_id} not found.")

        rental = Rental(
            vehicle_id=vehicle_id,
            customer_id=customer.id,
            # Frozen on purpose: a later rename or delete cannot rewrite it.
            customer_name=customer.name,
            start_at=start_at or self._clock(),
        )

        vehicle.status = VehicleStatus.IN_USE
        await self._vehicle_repository.update(vehicle)

        try:
            created = await self._rental_repository.add(rental)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            # Another transaction opened a rental between check and insert.
            if _ACTIVE_RENTAL_INDEX in str(exc.orig):
                raise VehicleHasActiveRentalError(
                    f"Vehicle {vehicle_id} already has an active rental."
                ) from exc
            raise

        return created

    async def complete(
        self, rental_id: UUID, *, end_at: datetime | None = None
    ) -> Rental:
        rental = await self.get(rental_id)
        rental.complete(end_at or self._clock())
        updated = await self._rental_repository.update(rental)

        # Shares the transaction, so the fleet can never show a car as rented
        # with no rental.
        vehicle = await self._vehicle_repository.get(rental.vehicle_id)
        if vehicle is not None and vehicle.status is VehicleStatus.IN_USE:
            vehicle.status = VehicleStatus.AVAILABLE
            await self._vehicle_repository.update(vehicle)

        await self._session.commit()
        return updated

    async def get(self, rental_id: UUID) -> Rental:
        rental = await self._rental_repository.get(rental_id)
        if rental is None:
            raise RentalNotFoundError(f"Rental {rental_id} not found.")
        return rental

    async def list_for_vehicle(
        self, vehicle_id: UUID, *, offset: int = 0, limit: int = 20
    ) -> list[Rental]:
        return await self._rental_repository.list_for_vehicle(
            vehicle_id, offset=offset, limit=limit
        )

    async def get_active_rental_for_vehicle(self, vehicle_id: UUID) -> Rental | None:
        return await self._rental_repository.get_active_rental_for_vehicle(vehicle_id)
