from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from vehicle_rental_core.domain.enums import VehicleStatus, VehicleType
from vehicle_rental_core.infrastructure.repositories.vehicle_repository import (
    VehicleRepository,
)

NOW = datetime(2026, 6, 1, tzinfo=UTC)


@pytest.fixture
def repository(session: AsyncMock) -> VehicleRepository:
    return VehicleRepository(session)


def _empty_result(session: AsyncMock) -> None:
    """Make ``session.execute`` yield no rows, so only the SQL is under test."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result


def _executed_sql(session: AsyncMock) -> str:
    statement = session.execute.await_args.args[0]
    return str(statement.compile(compile_kwargs={"literal_binds": True}))


class TestList:
    """What the listing does and does not filter.

    Pinned because it was silent: the listing used to drop retired vehicles
    with no parameter saying so.
    """

    async def test_should_not_filter_at_all_when_no_status_is_given(
        self, repository: VehicleRepository, session: AsyncMock
    ) -> None:
        _empty_result(session)

        await repository.list()

        # In particular not the "status != retired" that used to be implied.
        assert "WHERE" not in _executed_sql(session)

    async def test_should_return_a_retired_vehicle_the_query_yields(
        self, repository: VehicleRepository, session: AsyncMock
    ) -> None:
        # Nothing may drop the row on the way back out either.
        model = MagicMock()
        model.id = uuid4()
        model.vehicle_type = VehicleType.CAR
        model.registration_number = "AA-111"
        model.model = "Corolla"
        model.year = 2022
        model.status = VehicleStatus.RETIRED
        model.retired_at = NOW
        model.version = 2
        model.created_at = NOW
        model.updated_at = NOW
        result = MagicMock()
        result.scalars.return_value.all.return_value = [model]
        session.execute.return_value = result

        vehicles = await repository.list()

        assert [vehicle.status for vehicle in vehicles] == [VehicleStatus.RETIRED]

    async def test_should_narrow_to_the_requested_status(
        self, repository: VehicleRepository, session: AsyncMock
    ) -> None:
        _empty_result(session)

        await repository.list(status=VehicleStatus.MAINTENANCE)

        assert "status = 'maintenance'" in _executed_sql(session)

    async def test_should_still_return_retired_vehicles_when_asked_by_name(
        self, repository: VehicleRepository, session: AsyncMock
    ) -> None:
        _empty_result(session)

        await repository.list(status=VehicleStatus.RETIRED)

        assert "status = 'retired'" in _executed_sql(session)

    async def test_should_page_newest_first(
        self, repository: VehicleRepository, session: AsyncMock
    ) -> None:
        _empty_result(session)

        await repository.list(offset=40, limit=10)

        sql = _executed_sql(session)
        assert "ORDER BY vehicles.created_at DESC" in sql
        assert "LIMIT 10" in sql
        assert "OFFSET 40" in sql


class TestCountByStatus:
    async def test_should_map_the_grouped_rows_to_a_dict(
        self, repository: VehicleRepository, session: AsyncMock
    ) -> None:
        # MagicMock, not AsyncMock: .all() is sync.
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
        # Absent statuses are absent, not zero; the caller fills them in.
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result

        assert await repository.count_by_status() == {}


class TestDelete:
    async def test_should_issue_one_statement_without_loading_the_row(
        self, repository: VehicleRepository, session: AsyncMock
    ) -> None:
        # No SELECT first: the service establishes existence for the 404.
        await repository.delete(uuid4())

        session.execute.assert_awaited_once()

    async def test_should_not_flush(
        self, repository: VehicleRepository, session: AsyncMock
    ) -> None:
        # execute() sends the DELETE straight away, so a flush would be a no-op.
        await repository.delete(uuid4())

        session.flush.assert_not_awaited()

    async def test_should_not_delete_the_rentals_itself(
        self, repository: VehicleRepository, session: AsyncMock
    ) -> None:
        # The ON DELETE CASCADE does that, which is why the statement names
        # only vehicles.
        await repository.delete(uuid4())

        sql = str(session.execute.await_args.args[0])
        assert sql.startswith("DELETE FROM vehicles")
        assert "rentals" not in sql
