from vehicle_rental_core.application.views import FleetMetrics
from vehicle_rental_core.domain.enums import VehicleStatus
from vehicle_rental_core.infrastructure.repositories.rental_repository import (
    RentalRepository,
)
from vehicle_rental_core.infrastructure.repositories.vehicle_repository import (
    VehicleRepository,
)


class FleetMetricsService:
    """Fleet tallies for a metrics scrape.

    Read-only, so unlike its sibling services it holds no session: there is
    nothing to commit.
    """

    def __init__(
        self,
        vehicle_repository: VehicleRepository,
        rental_repository: RentalRepository,
    ) -> None:
        self._vehicle_repository = vehicle_repository
        self._rental_repository = rental_repository

    async def collect(self) -> FleetMetrics:
        counts = await self._vehicle_repository.count_by_status()
        # Absent statuses come back missing, not zero.
        return FleetMetrics(
            vehicle_counts={member: counts.get(member, 0) for member in VehicleStatus},
            ongoing_rentals=await self._rental_repository.count_active_rentals(),
        )
