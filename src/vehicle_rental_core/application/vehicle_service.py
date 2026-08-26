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
        # The session is the transaction boundary. It is injected rather than
        # reached for through a repository; a Unit of Work will take this role.
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
        # Checked up front for a clean 409; the unique index is the real
        # guarantee under concurrency.
        existing = await self._vehicle_repository.get_by_registration_number(
            registration_number
        )
        if existing is not None:
            raise RegistrationNumberAlreadyExistsError(
                f"Registration number {registration_number!r} is already taken."
            )

        # Constructing the entity validates it; there is no separate step to
        # forget.
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
            # The unique index is the authority: another transaction claimed
            # this plate between our check above and our insert.
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

        Read-only: nothing here commits.

        The counts are an aggregate over every row and ignore the filter and
        the page, so the response stays a fixed size however large the fleet
        grows — the page is what scales, and it is bounded by ``limit``.
        """
        vehicles = await self._vehicle_repository.list(
            status=status, offset=offset, limit=limit
        )
        counts = await self._vehicle_repository.count_by_status()
        # Absent statuses come back missing, not zero; filling them in here is
        # what lets a client render a stable set of tiles instead of guessing
        # whether a gap means "none" or "not reported".
        complete_counts = {member: counts.get(member, 0) for member in VehicleStatus}

        rentals_by_vehicle = await self._active_rentals_by_vehicle(vehicles)
        entries = [
            VehicleStatusEntry(
                vehicle=vehicle,
                current_rental=rentals_by_vehicle.get(vehicle.id),
            )
            for vehicle in vehicles
        ]

        # How many rows the caller can page through, which is what a total on a
        # paginated response is taken to mean. Read off the counts rather than
        # counted again: they already tally every status over the whole table,
        # so the filtered total is exact and costs no second query.
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

        Only ``IN_USE`` vehicles are asked about: for any other status there is
        no open rental to find, so a wider query would return the same answer
        and read more rows. A page with none skips the query altogether.
        """
        in_use_ids = [
            vehicle.id for vehicle in vehicles if vehicle.status is VehicleStatus.IN_USE
        ]
        rentals = await self._rental_repository.list_active_for_vehicles(in_use_ids)
        return {rental.vehicle_id: rental for rental in rentals}

    async def update(self, vehicle_id: UUID, changes: VehicleChanges) -> Vehicle:
        vehicle = await self.get(vehicle_id)

        # Status is the one field that cannot be a plain validated assignment:
        # its rules need the clock and a fact about other rows that the entity
        # has no way to fetch for itself.
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

        This is the only supported way to remove a vehicle from service. A hard
        DELETE cascades to the rentals and is not reachable from the API.
        """
        vehicle = await self.get(vehicle_id)
        vehicle.retire(
            at=self._clock(),
            has_active_rental=await self._has_active_rental(vehicle_id),
        )
        retired = await self._vehicle_repository.update(vehicle)
        await self._commit()
        return retired

    async def _has_active_rental(self, vehicle_id: UUID) -> bool:
        return await self._rental_repository.has_active_rental_for_vehicle(vehicle_id)

    async def _commit(self) -> None:
        await self._session.commit()
