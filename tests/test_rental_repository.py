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
        # A domain error, not a bare LookupError, so the API maps it to a 409.
        # MagicMock, not AsyncMock: scalar_one_or_none is sync.
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        rental = Rental(vehicle_id=uuid4(), customer_name="Ada", start_at=NOW)

        with pytest.raises(ConcurrentUpdateError):
            await repository.update(rental)

        session.flush.assert_not_awaited()


class TestListActiveForVehicles:
    async def test_should_not_query_for_an_empty_id_list(
        self, repository: RentalRepository, session: AsyncMock
    ) -> None:
        # An empty IN () can only return nothing, so no round trip is sent.
        assert await repository.list_active_for_vehicles([]) == []

        session.execute.assert_not_awaited()

    async def test_should_return_the_open_rentals_of_the_given_vehicles(
        self, repository: RentalRepository, session: AsyncMock
    ) -> None:
        vehicle_id = uuid4()
        model = MagicMock()
        model.id = uuid4()
        model.vehicle_id = vehicle_id
        model.customer_id = uuid4()
        model.customer_name = "Ada"
        model.start_at = NOW
        model.end_at = None
        model.created_at = NOW
        model.updated_at = NOW
        result = MagicMock()
        result.scalars.return_value.all.return_value = [model]
        session.execute.return_value = result

        rentals = await repository.list_active_for_vehicles([vehicle_id])

        assert [rental.vehicle_id for rental in rentals] == [vehicle_id]
