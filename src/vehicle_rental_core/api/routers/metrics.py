import logging

from fastapi import APIRouter, Response
from sqlalchemy.exc import SQLAlchemyError

from vehicle_rental_core.api.dependencies import FleetMetricsServiceDep
from vehicle_rental_core.core.observability.metrics import (
    render_latest,
    set_fleet_gauges,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["observability"])


@router.get("/metrics", include_in_schema=False)
async def metrics(service: FleetMetricsServiceDep) -> Response:
    try:
        fleet = await service.collect()
    except SQLAlchemyError:
        # A failed scrape would take the HTTP metrics down with the gauges,
        # exactly when they are most worth having. Serve the stale ones.
        logger.warning("Fleet gauges not refreshed", extra={"reason": "database"})
    else:
        set_fleet_gauges(fleet.vehicle_counts, fleet.ongoing_rentals)
    return render_latest()
