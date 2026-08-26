from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from vehicle_rental_core.domain.customer import Customer
from vehicle_rental_core.domain.errors import ConcurrentUpdateError
from vehicle_rental_core.infrastructure.repositories.customer_repository import (
    CustomerRepository,
)

BORN = date(1990, 6, 1)


@pytest.fixture
def repository(session: AsyncMock) -> CustomerRepository:
    return CustomerRepository(session)


def _missing_row(session: AsyncMock) -> None:
    """Make the next query return no row.

    The result is a MagicMock, not the AsyncMock a child of `session` would
    default to — scalar_one_or_none is sync and must not return a coroutine.
    """
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result


class TestUpdate:
    async def test_should_reject_a_customer_whose_row_is_gone(
        self, repository: CustomerRepository, session: AsyncMock
    ) -> None:
        _missing_row(session)
        customer = Customer(name="Ada", email="ada@example.com", date_of_birth=BORN)

        with pytest.raises(ConcurrentUpdateError):
            await repository.update(customer)

        session.flush.assert_not_awaited()


class TestDelete:
    async def test_should_issue_one_statement_without_loading_the_row(
        self, repository: CustomerRepository, session: AsyncMock
    ) -> None:
        # No SELECT first: the service establishes existence for the 404.
        await repository.delete(uuid4())

        session.execute.assert_awaited_once()

    async def test_should_not_flush(
        self, repository: CustomerRepository, session: AsyncMock
    ) -> None:
        # execute() sends the DELETE straight away, so a flush would be a no-op.
        await repository.delete(uuid4())

        session.flush.assert_not_awaited()
