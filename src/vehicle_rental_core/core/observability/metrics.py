import time
from collections.abc import Awaitable, Callable, Mapping

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from vehicle_rental_core.domain.enums import VehicleStatus

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests handled.",
    labelnames=("method", "path", "status"),
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    labelnames=("method", "path"),
)

# Gauges, not counters, so no _total suffix: these move down as well as up.
FLEET_VEHICLES = Gauge(
    "fleet_vehicles",
    "Vehicles in the fleet, by status.",
    labelnames=("status",),
)

FLEET_RENTALS_ONGOING = Gauge(
    "fleet_rentals_ongoing",
    "Rentals currently open.",
)


def _route_template(request: Request) -> str:
    """Label with the route template, not the concrete URL.

    ``/vehicles/{vehicle_id}`` stays one time series; ``/vehicles/1``,
    ``/vehicles/2``, ... would create an unbounded number of them.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "__unmatched__"


def set_fleet_gauges(
    vehicle_counts: Mapping[VehicleStatus, int], ongoing_rentals: int
) -> None:
    """Publish the fleet tallies.

    ``vehicle_counts`` must carry every status: a label that stops being
    written keeps its last value, so an omitted status would read as stale.
    """
    for status, count in vehicle_counts.items():
        FLEET_VEHICLES.labels(status).set(count)
    FLEET_RENTALS_ONGOING.set(ongoing_rentals)


def render_latest() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def install_metrics_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def record_request_metrics(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # An unhandled error still surfaced as a 500 to the client, so it
            # must appear in the counter rather than vanish from the metrics.
            path = _route_template(request)
            REQUEST_COUNT.labels(request.method, path, "500").inc()
            REQUEST_LATENCY.labels(request.method, path).observe(
                time.perf_counter() - started
            )
            raise

        path = _route_template(request)
        REQUEST_COUNT.labels(request.method, path, str(response.status_code)).inc()
        REQUEST_LATENCY.labels(request.method, path).observe(
            time.perf_counter() - started
        )
        return response
