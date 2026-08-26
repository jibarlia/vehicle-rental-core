from unittest.mock import AsyncMock, MagicMock

import pytest

from vehicle_rental_core.domain.enums import VehicleStatus
from vehicle_rental_core.infrastructure.repositories.vehicle_repository import (
    VehicleRepository,
)


@pytest.fixture
def repository(session: AsyncMock) -> VehicleRepository:
    return VehicleRepository(session)


class TestCountByStatus:
    async def test_should_map_the_grouped_rows_to_a_dict(
        self, repository: VehicleRepository, session: AsyncMock
    ) -> None:
        # MagicMock rather than the AsyncMock a child of `session` would
        # default to: .all() is sync and must not return a coroutine.
        result = MagicMock()
        result.all.return_value = [
            (VehicleStatus.AVAILABLE, 8),
            (VehicleStatus.IN_USE, 3),
        ]
        session.execute.return_value = result

        counts = await repository.count_by_status()

        assert counts == {VehicleStatus.AVAILABLE: 8, VehicleStatus.IN_USE: 3}

    async def test_should_return_nothing_for_an_empty_table(
        self, repository: VehicleRepository, session: AsyncMock
    ) -> None:
        # Absent statuses are absent, not zero — filling them in belongs to the
        # caller, who knows what a complete set looks like.
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result

        assert await repository.count_by_status() == {}
