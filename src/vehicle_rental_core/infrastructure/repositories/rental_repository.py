from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vehicle_rental_core.domain.errors import ConcurrentUpdateError
from vehicle_rental_core.domain.rental import Rental
from vehicle_rental_core.infrastructure.models.rental import RentalModel
from vehicle_rental_core.infrastructure.repositories.mappers import (
    rental_to_domain,
    rental_to_model,
)


class RentalRepository:
    """Data access for ``rentals``. Active means ``end_at IS NULL``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, rental: Rental) -> Rental:
        model = rental_to_model(rental)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return rental_to_domain(model)

    async def get(self, rental_id: UUID) -> Rental | None:
        model = await self._get_model(rental_id)
        return rental_to_domain(model) if model is not None else None

    async def get_active_rental_for_vehicle(self, vehicle_id: UUID) -> Rental | None:
        """The vehicle's open rental — the one with no ``end_at`` — if any.

        At most one can exist: ``uq_rentals_one_active_per_vehicle`` guarantees
        it, which is why this returns a single rental rather than a list.
        """
        statement = select(RentalModel).where(
            RentalModel.vehicle_id == vehicle_id,
            RentalModel.end_at.is_(None),
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return rental_to_domain(model) if model is not None else None

    async def has_active_rental_for_vehicle(self, vehicle_id: UUID) -> bool:
        """Whether the vehicle is currently rented out.

        Cheaper than :meth:`get_active_rental_for_vehicle` when only the answer
        matters — it selects one id instead of building an entity.
        """
        statement = (
            select(RentalModel.id)
            .where(
                RentalModel.vehicle_id == vehicle_id,
                RentalModel.end_at.is_(None),
            )
            .limit(1)
        )
        return (await self._session.execute(statement)).first() is not None

    async def list_for_vehicle(
        self, vehicle_id: UUID, *, offset: int = 0, limit: int = 20
    ) -> list[Rental]:
        # Ordering matches ix_rentals_vehicle_start_at so the index serves it.
        statement = (
            select(RentalModel)
            .where(RentalModel.vehicle_id == vehicle_id)
            .order_by(RentalModel.start_at.desc())
            .offset(offset)
            .limit(limit)
        )
        models = (await self._session.execute(statement)).scalars().all()
        return [rental_to_domain(model) for model in models]

    async def update(self, rental: Rental) -> Rental:
        model = await self._get_model(rental.id)
        if model is None:
            raise ConcurrentUpdateError(f"Rental {rental.id} no longer exists.")

        model.customer_name = rental.customer_name
        model.start_at = rental.start_at
        model.end_at = rental.end_at
        await self._session.flush()
        await self._session.refresh(model)
        return rental_to_domain(model)

    async def _get_model(self, rental_id: UUID) -> RentalModel | None:
        statement = select(RentalModel).where(RentalModel.id == rental_id)
        return (await self._session.execute(statement)).scalar_one_or_none()
