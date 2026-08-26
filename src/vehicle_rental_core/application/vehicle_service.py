from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from vehicle_rental_core.application.clock import Clock, utcnow
from vehicle_rental_core.application.commands import VehicleChanges
from vehicle_rental_core.application.views import FleetStatus, VehicleStatusEntry
from vehicle_rental_core.domain.enums import VehicleStatus, VehicleType
from vehicle_rental_core.domain.errors import (
    RegistrationNumberAlreadyExistsError,
    VehicleHasActiveRentalError,
    VehicleNotFoundError,
)
from vehicle_rental_core.domain.rental import Rental
from vehicle_rental_core.domain.vehicle import Vehicle
from vehicle_rental_core.infrastructure.repositories.rental_repository import (
    RentalRepository,
)
from vehicle_rental_core.infrastructure.repositories.vehicle_repository import (
    VehicleRepository,
)

_REGISTRATION_NUMBER_INDEX = "ix_vehicles_registration_number"


class VehicleService:
    """Vehicle use cases. Owns the transaction; builds no SQL."""

    def __init__(
        self,
        session: AsyncSession,
        vehicle_repository: VehicleRepository,
        rental_repository: RentalRepository,
        clock: Clock = utcnow,
    ) -> None:
        self._session = session
        self._vehicle_repository = vehicle_repository
        self._rental_repository = rental_repository
        self._clock = clock

    async def create(
        self,
        *,
        registration_number: str,
        model: str,
        year: int,
        vehicle_type: VehicleType = VehicleType.CAR,
    ) -> Vehicle:
        # Up front for a clean 409; the unique index is the real guarantee.
        existing = await self._vehicle_repository.get_by_registration_number(
            registration_number
        )
        if existing is not None:
            raise RegistrationNumberAlreadyExistsError(
                f"Registration number {registration_number!r} is already taken."
            )

        vehicle = Vehicle(
            registration_number=registration_number,
            model=model,
            year=year,
            vehicle_type=vehicle_type,
        )
        try:
            created = await self._vehicle_repository.add(vehicle)
            await self._commit()
        except IntegrityError as exc:
            await self._session.rollback()
            # Another transaction claimed the plate between check and insert.
            if _REGISTRATION_NUMBER_INDEX in str(exc.orig):
                raise RegistrationNumberAlreadyExistsError(
                    f"Registration number {registration_number!r} is already taken."
                ) from exc
            raise

        return created

    async def get(self, vehicle_id: UUID) -> Vehicle:
        vehicle = await self._vehicle_repository.get(vehicle_id)
        if vehicle is None:
            raise VehicleNotFoundError(f"Vehicle {vehicle_id} not found.")
        return vehicle

    async def list(
        self,
        *,
        status: VehicleStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[Vehicle]:
        return await self._vehicle_repository.list(
            status=status, offset=offset, limit=limit
        )

    async def fleet_status(
        self,
        *,
        status: VehicleStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> FleetStatus:
        """One page of vehicles with their status, under whole-fleet counts.

        Read-only. The counts ignore the filter and the page, so the response
        stays a fixed size however large the fleet grows.
        """
        vehicles = await self._vehicle_repository.list(
            status=status, offset=offset, limit=limit
        )
        counts = await self._vehicle_repository.count_by_status()
        # Absent statuses come back missing, not zero.
        complete_counts = {member: counts.get(member, 0) for member in VehicleStatus}

        rentals_by_vehicle = await self._active_rentals_by_vehicle(vehicles)
        entries = [
            VehicleStatusEntry(
                vehicle=vehicle,
                current_rental=rentals_by_vehicle.get(vehicle.id),
            )
            for vehicle in vehicles
        ]

        # Read off the counts, which already tally the whole table, so the
        # filtered total is exact without a second query.
        total = (
            complete_counts[status]
            if status is not None
            else sum(complete_counts.values())
        )

        return FleetStatus(counts=complete_counts, total=total, entries=entries)

    async def _active_rentals_by_vehicle(
        self, vehicles: Sequence[Vehicle]
    ) -> dict[UUID, Rental]:
        """Open rentals for the vehicles that have one, keyed by vehicle.

        Only ``IN_USE`` vehicles are asked about; no other status can have one.
        """
        in_use_ids = [
            vehicle.id for vehicle in vehicles if vehicle.status is VehicleStatus.IN_USE
        ]
        rentals = await self._rental_repository.list_active_for_vehicles(in_use_ids)
        return {rental.vehicle_id: rental for rental in rentals}

    async def update(self, vehicle_id: UUID, changes: VehicleChanges) -> Vehicle:
        vehicle = await self.get(vehicle_id)

        # Status needs the clock and facts about other rows, so it cannot be a
        # plain validated assignment.
        if changes.status is not None:
            vehicle.change_status(
                changes.status,
                at=self._clock(),
                has_active_rental=await self._has_active_rental(vehicle_id),
            )

        vehicle.apply(changes.attributes())

        updated = await self._vehicle_repository.update(vehicle)
        await self._commit()
        return updated

    async def retire(self, vehicle_id: UUID) -> Vehicle:
        """Retire a vehicle from the fleet, keeping it and its rentals on record.

        Takes a vehicle out of service without erasing it, unlike
        :meth:`delete`.
        """
        vehicle = await self.get(vehicle_id)
        vehicle.retire(
            at=self._clock(),
            has_active_rental=await self._has_active_rental(vehicle_id),
        )
        retired = await self._vehicle_repository.update(vehicle)
        await self._commit()
        return retired

    async def delete(self, vehicle_id: UUID) -> None:
        """Delete a vehicle and, by cascade, every rental it appeared in.

        A retired vehicle can be deleted: retirement blocks *changes*, and this
        erases the row rather than changing it.
        """
        await self.get(vehicle_id)
        # Deleting a vehicle someone is currently driving would take the open
        # rental with it, so the guard matches retire's.
        if await self._has_active_rental(vehicle_id):
            raise VehicleHasActiveRentalError(
                f"Vehicle {vehicle_id} has an active rental."
            )

        await self._vehicle_repository.delete(vehicle_id)
        await self._commit()

    async def _has_active_rental(self, vehicle_id: UUID) -> bool:
        return await self._rental_repository.has_active_rental_for_vehicle(vehicle_id)

    async def _commit(self) -> None:
        await self._session.commit()
