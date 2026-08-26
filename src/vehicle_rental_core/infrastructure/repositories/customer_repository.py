from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from vehicle_rental_core.domain.customer import Customer
from vehicle_rental_core.domain.errors import ConcurrentUpdateError
from vehicle_rental_core.infrastructure.models.customer import CustomerModel
from vehicle_rental_core.infrastructure.repositories.mappers import (
    apply_customer,
    customer_to_domain,
    customer_to_model,
)


class CustomerRepository:
    """Data access for ``customers``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, customer: Customer) -> Customer:
        model = customer_to_model(customer)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return customer_to_domain(model)

    async def get(self, customer_id: UUID) -> Customer | None:
        model = await self._get_model(customer_id)
        return customer_to_domain(model) if model is not None else None

    async def get_by_email(self, email: str) -> Customer | None:
        statement = select(CustomerModel).where(CustomerModel.email == email)
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return customer_to_domain(model) if model is not None else None

    async def list(self, *, offset: int = 0, limit: int = 20) -> list[Customer]:
        statement = (
            select(CustomerModel)
            .order_by(CustomerModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        models = (await self._session.execute(statement)).scalars().all()
        return [customer_to_domain(model) for model in models]

    async def update(self, customer: Customer) -> Customer:
        model = await self._get_model(customer.id)
        if model is None:
            raise ConcurrentUpdateError(f"Customer {customer.id} no longer exists.")

        apply_customer(model, customer)
        await self._session.flush()
        await self._session.refresh(model)
        return customer_to_domain(model)

    async def delete(self, customer_id: UUID) -> None:
        """Remove the customer, letting the database null its rentals' FK.

        Issued as a single statement rather than a load-then-delete: the row
        does not need to be in the session, and ``passive_deletes`` on the
        rentals relationship means the ``ON DELETE SET NULL`` is the database's
        job either way. Deleting a row that is not there is a no-op — the
        caller establishes existence when it wants a 404.
        """
        statement = delete(CustomerModel).where(CustomerModel.id == customer_id)
        await self._session.execute(statement)
        await self._session.flush()

    async def _get_model(self, customer_id: UUID) -> CustomerModel | None:
        statement = select(CustomerModel).where(CustomerModel.id == customer_id)
        return (await self._session.execute(statement)).scalar_one_or_none()
