from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vehicle_rental_core.domain.enums import VehicleStatus
from vehicle_rental_core.domain.errors import ConcurrentUpdateError
from vehicle_rental_core.domain.vehicle import Vehicle
from vehicle_rental_core.infrastructure.models.vehicle import VehicleModel
from vehicle_rental_core.infrastructure.repositories.mappers import (
    apply_vehicle,
    vehicle_to_domain,
    vehicle_to_model,
)


class VehicleRepository:
    """Data access for ``vehicles``.

    Nothing here hides retired vehicles. Retiring keeps the record readable —
    that is the whole point of retiring rather than deleting — so a reader that
    dropped those rows would be undoing the distinction. Callers that want a
    narrower set say so with ``status``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, vehicle: Vehicle) -> Vehicle:
        model = vehicle_to_model(vehicle)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return vehicle_to_domain(model)

    async def get(self, vehicle_id: UUID) -> Vehicle | None:
        model = await self._get_model(vehicle_id)
        return vehicle_to_domain(model) if model is not None else None

    async def get_by_registration_number(
        self, registration_number: str
    ) -> Vehicle | None:
        """Plates are unique across retired vehicles too, so none are skipped."""
        statement = select(VehicleModel).where(
            VehicleModel.registration_number == registration_number
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return vehicle_to_domain(model) if model is not None else None

    async def list(
        self,
        *,
        status: VehicleStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[Vehicle]:
        """Vehicles, newest first — every one of them unless ``status`` narrows it.

        Retired vehicles are included. A collection that quietly withheld part
        of the collection would leave a caller no way to ask for the whole
        thing, and no way to discover that anything was missing; narrowing is
        the caller's business, spelled out with ``status``.
        """
        statement = select(VehicleModel)
        if status is not None:
            statement = statement.where(VehicleModel.status == status)

        statement = (
            statement.order_by(VehicleModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        models = (await self._session.execute(statement)).scalars().all()
        return [vehicle_to_domain(model) for model in models]

    async def count_by_status(self) -> dict[VehicleStatus, int]:
        """How many vehicles sit in each status, across the whole table.

        Unlike :meth:`list` this hides nothing — retired vehicles are counted
        under their own status, because a tally that quietly omitted them would
        not add up to the fleet.

        Only statuses actually present come back; filling in the zeroes is the
        caller's job, since what counts as a complete set is a presentation
        question rather than a storage one.
        """
        statement = select(VehicleModel.status, func.count()).group_by(
            VehicleModel.status
        )
        rows = (await self._session.execute(statement)).all()
        return {status: count for status, count in rows}

    async def update(self, vehicle: Vehicle) -> Vehicle:
        """Persist domain changes, rejecting writes based on stale state."""
        model = await self._get_model(vehicle.id)
        if model is None:
            raise ConcurrentUpdateError(f"Vehicle {vehicle.id} no longer exists.")

        # The caller read version N; if the row has moved on, their decision was
        # made against state that is no longer true.
        if model.version != vehicle.version:
            raise ConcurrentUpdateError(
                f"Vehicle {vehicle.id} was modified by another transaction."
            )

        apply_vehicle(model, vehicle)
        await self._session.flush()
        await self._session.refresh(model)
        return vehicle_to_domain(model)

    async def _get_model(self, vehicle_id: UUID) -> VehicleModel | None:
        statement = select(VehicleModel).where(VehicleModel.id == vehicle_id)
        return (await self._session.execute(statement)).scalar_one_or_none()
