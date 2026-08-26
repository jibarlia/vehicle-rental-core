from datetime import date
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from vehicle_rental_core.application.commands import CustomerChanges
from vehicle_rental_core.domain.customer import Customer
from vehicle_rental_core.domain.enums import Sex
from vehicle_rental_core.domain.errors import (
    CustomerNotFoundError,
    EmailAlreadyExistsError,
)
from vehicle_rental_core.infrastructure.repositories.customer_repository import (
    CustomerRepository,
)

_EMAIL_INDEX = "ix_customers_email"


class CustomerService:
    """Customer use cases. Owns the transaction; builds no SQL."""

    def __init__(
        self,
        session: AsyncSession,
        customer_repository: CustomerRepository,
    ) -> None:
        self._session = session
        self._customer_repository = customer_repository

    async def create(
        self,
        *,
        name: str,
        email: str,
        date_of_birth: date,
        sex: Sex = Sex.UNSPECIFIED,
    ) -> Customer:
        await self._reject_taken_email(email)

        customer = Customer(
            name=name,
            email=email,
            date_of_birth=date_of_birth,
            sex=sex,
        )
        try:
            created = await self._customer_repository.add(customer)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            # Another transaction claimed the address between check and insert.
            self._reraise_duplicate_email(exc, email)
            raise

        return created

    async def get(self, customer_id: UUID) -> Customer:
        customer = await self._customer_repository.get(customer_id)
        if customer is None:
            raise CustomerNotFoundError(f"Customer {customer_id} not found.")
        return customer

    async def list(self, *, offset: int = 0, limit: int = 20) -> list[Customer]:
        return await self._customer_repository.list(offset=offset, limit=limit)

    async def update(self, customer_id: UUID, changes: CustomerChanges) -> Customer:
        customer = await self.get(customer_id)

        attributes = changes.attributes()
        # Only when the address moves: an unchanged email would match the
        # customer's own row and reject their update.
        new_email = attributes.get("email")
        if new_email is not None and new_email != customer.email:
            await self._reject_taken_email(new_email)

        for name, value in attributes.items():
            setattr(customer, name, value)

        try:
            updated = await self._customer_repository.update(customer)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            self._reraise_duplicate_email(exc, str(new_email))
            raise

        return updated

    async def delete(self, customer_id: UUID) -> None:
        """Delete the customer, keeping their rentals as history.

        A real delete, unlike retiring a vehicle: the FK is ``ON DELETE SET
        NULL`` and ``customer_name`` was snapshotted at start.
        """
        await self.get(customer_id)
        await self._customer_repository.delete(customer_id)
        await self._session.commit()

    async def _reject_taken_email(self, email: str) -> None:
        """Up front for a clean 409; the unique index is the real guarantee."""
        existing = await self._customer_repository.get_by_email(email)
        if existing is not None:
            raise EmailAlreadyExistsError(f"Email {email!r} is already registered.")

    @staticmethod
    def _reraise_duplicate_email(exc: IntegrityError, email: str) -> None:
        if _EMAIL_INDEX in str(exc.orig):
            raise EmailAlreadyExistsError(
                f"Email {email!r} is already registered."
            ) from exc
