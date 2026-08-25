from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from vehicle_rental_core.domain.errors import ConcurrentUpdateError
from vehicle_rental_core.domain.rental import Rental
from vehicle_rental_core.infrastructure.repositories.rental_repository import (
    RentalRepository,
)

NOW = datetime(2026, 6, 1, tzinfo=UTC)


@pytest.fixture
def repository(session: AsyncMock) -> RentalRepository:
    return RentalRepository(session)


class TestUpdate:
    async def test_should_reject_a_rental_whose_row_is_gone(
        self, repository: RentalRepository, session: AsyncMock
    ) -> None:
        # A domain error, not a bare LookupError: the API layer maps this to a
        # 409 instead of letting it escape as a 500.
        #
        # The result is a MagicMock, not the AsyncMock a child of `session`
        # would default to — scalar_one_or_none is sync and must not return a
        # coroutine.
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        rental = Rental(vehicle_id=uuid4(), customer_name="Ada", start_at=NOW)

        with pytest.raises(ConcurrentUpdateError):
            await repository.update(rental)

        session.flush.assert_not_awaited()
