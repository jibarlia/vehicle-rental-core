from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from vehicle_rental_core.application.commands import CustomerChanges
from vehicle_rental_core.application.customer_service import CustomerService
from vehicle_rental_core.domain.customer import Customer
from vehicle_rental_core.domain.enums import Sex
from vehicle_rental_core.domain.errors import (
    CustomerNotFoundError,
    EmailAlreadyExistsError,
)
from vehicle_rental_core.infrastructure.repositories.customer_repository import (
    CustomerRepository,
)

BORN = date(1990, 6, 1)


@pytest.fixture
def customer_repository() -> AsyncMock:
    return AsyncMock(spec=CustomerRepository)


@pytest.fixture
def service(session: AsyncMock, customer_repository: AsyncMock) -> CustomerService:
    return CustomerService(session, customer_repository)


def _customer(**overrides: object) -> Customer:
    defaults: dict[str, object] = {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "date_of_birth": BORN,
    }
    return Customer(**{**defaults, **overrides})  # type: ignore[arg-type]


def _integrity_error(message: str) -> IntegrityError:
    return IntegrityError("INSERT", {}, Exception(message))


class TestCreateCustomer:
    async def test_should_persist_and_commit(
        self,
        service: CustomerService,
        customer_repository: AsyncMock,
        session: AsyncMock,
    ) -> None:
        customer_repository.get_by_email.return_value = None
        customer_repository.add.side_effect = lambda customer: customer

        created = await service.create(
            name="Ada Lovelace", email="ada@example.com", date_of_birth=BORN
        )

        assert created.name == "Ada Lovelace"
        assert created.sex is Sex.UNSPECIFIED
        session.commit.assert_awaited_once()

    async def test_should_reject_an_email_already_taken(
        self,
        service: CustomerService,
        customer_repository: AsyncMock,
    ) -> None:
        customer_repository.get_by_email.return_value = _customer()

        with pytest.raises(EmailAlreadyExistsError):
            await service.create(
                name="Someone", email="ada@example.com", date_of_birth=BORN
            )

        customer_repository.add.assert_not_awaited()

    async def test_should_translate_the_unique_index_violation_into_a_conflict(
        self,
        service: CustomerService,
        customer_repository: AsyncMock,
        session: AsyncMock,
    ) -> None:
        # Another transaction claimed the address between our check and insert.
        customer_repository.get_by_email.return_value = None
        customer_repository.add.side_effect = _integrity_error(
            'duplicate key value violates unique constraint "ix_customers_email"'
        )

        with pytest.raises(EmailAlreadyExistsError):
            await service.create(
                name="Ada", email="ada@example.com", date_of_birth=BORN
            )

        session.rollback.assert_awaited_once()

    async def test_should_not_mask_an_unrelated_integrity_error(
        self,
        service: CustomerService,
        customer_repository: AsyncMock,
    ) -> None:
        customer_repository.get_by_email.return_value = None
        customer_repository.add.side_effect = _integrity_error(
            'violates check constraint "ck_customers_sex"'
        )

        with pytest.raises(IntegrityError):
            await service.create(
                name="Ada", email="ada@example.com", date_of_birth=BORN
            )


class TestGetCustomer:
    async def test_should_reject_an_unknown_customer(
        self, service: CustomerService, customer_repository: AsyncMock
    ) -> None:
        customer_repository.get.return_value = None

        with pytest.raises(CustomerNotFoundError):
            await service.get(uuid4())


class TestUpdateCustomer:
    async def test_should_apply_only_the_fields_sent(
        self,
        service: CustomerService,
        customer_repository: AsyncMock,
        session: AsyncMock,
    ) -> None:
        customer_repository.get.return_value = _customer()
        customer_repository.update.side_effect = lambda customer: customer

        updated = await service.update(uuid4(), CustomerChanges(name="Grace Hopper"))

        assert updated.name == "Grace Hopper"
        assert updated.email == "ada@example.com"  # untouched
        session.commit.assert_awaited_once()

    async def test_should_reject_moving_to_an_email_someone_else_holds(
        self,
        service: CustomerService,
        customer_repository: AsyncMock,
    ) -> None:
        customer_repository.get.return_value = _customer()
        customer_repository.get_by_email.return_value = _customer(
            email="grace@example.com"
        )

        with pytest.raises(EmailAlreadyExistsError):
            await service.update(uuid4(), CustomerChanges(email="grace@example.com"))

        customer_repository.update.assert_not_awaited()

    async def test_should_allow_resubmitting_the_customers_own_email(
        self,
        service: CustomerService,
        customer_repository: AsyncMock,
    ) -> None:
        # Re-checking an unchanged address would find the customer's own row
        # and reject their own update.
        customer_repository.get.return_value = _customer()
        customer_repository.update.side_effect = lambda customer: customer

        updated = await service.update(
            uuid4(), CustomerChanges(name="Ada L.", email="ada@example.com")
        )

        assert updated.name == "Ada L."
        customer_repository.get_by_email.assert_not_awaited()


class TestDeleteCustomer:
    async def test_should_delete_and_commit(
        self,
        service: CustomerService,
        customer_repository: AsyncMock,
        session: AsyncMock,
    ) -> None:
        customer = _customer()
        customer_repository.get.return_value = customer

        await service.delete(customer.id)

        customer_repository.delete.assert_awaited_once_with(customer.id)
        session.commit.assert_awaited_once()

    async def test_should_reject_an_unknown_customer(
        self, service: CustomerService, customer_repository: AsyncMock
    ) -> None:
        customer_repository.get.return_value = None

        with pytest.raises(CustomerNotFoundError):
            await service.delete(uuid4())

        customer_repository.delete.assert_not_awaited()
