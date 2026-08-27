from unittest.mock import AsyncMock

import pytest

from vehicle_rental_core.application.fleet_metrics_service import FleetMetricsService
from vehicle_rental_core.domain.enums import VehicleStatus
from vehicle_rental_core.infrastructure.repositories.rental_repository import (
    RentalRepository,
)
from vehicle_rental_core.infrastructure.repositories.vehicle_repository import (
    VehicleRepository,
)


@pytest.fixture
def vehicle_repository() -> AsyncMock:
    repository = AsyncMock(spec=VehicleRepository)
    repository.count_by_status.return_value = {}
    return repository


@pytest.fixture
def rental_repository() -> AsyncMock:
    repository = AsyncMock(spec=RentalRepository)
    repository.count_active_rentals.return_value = 0
    return repository


@pytest.fixture
def service(
    vehicle_repository: AsyncMock, rental_repository: AsyncMock
) -> FleetMetricsService:
    return FleetMetricsService(vehicle_repository, rental_repository)


class TestCollect:
    async def test_should_report_every_status_filling_absent_ones_with_zero(
        self, service: FleetMetricsService, vehicle_repository: AsyncMock
    ) -> None:
        # A status with no rows must still be published, or its gauge label
        # would keep whatever the previous scrape set.
        vehicle_repository.count_by_status.return_value = {VehicleStatus.AVAILABLE: 8}

        metrics = await service.collect()

        assert metrics.vehicle_counts == {
            VehicleStatus.AVAILABLE: 8,
            VehicleStatus.IN_USE: 0,
            VehicleStatus.MAINTENANCE: 0,
            VehicleStatus.RETIRED: 0,
        }

    async def test_should_report_the_count_of_open_rentals(
        self, service: FleetMetricsService, rental_repository: AsyncMock
    ) -> None:
        rental_repository.count_active_rentals.return_value = 3

        metrics = await service.collect()

        assert metrics.ongoing_rentals == 3
