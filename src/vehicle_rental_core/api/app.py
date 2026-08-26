from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

import vehicle_rental_core.infrastructure.models  # noqa: F401 — populates metadata
from vehicle_rental_core import __version__
from vehicle_rental_core.api.errors import register_exception_handlers
from vehicle_rental_core.api.routers import (
    customers,
    health,
    metrics,
    rentals,
    vehicles,
)
from vehicle_rental_core.core.config import Settings, get_settings
from vehicle_rental_core.core.observability.logging import configure_logging
from vehicle_rental_core.core.observability.metrics import install_metrics_middleware
from vehicle_rental_core.infrastructure.db import create_engine, create_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings: Settings = app.state.settings
    configure_logging(settings)

    engine = create_engine(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    try:
        yield
    finally:
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory.

    Taking ``settings`` as an argument keeps the app constructible against a
    throwaway configuration, which is what makes the test suite hermetic.
    Schema is never created here — Alembic owns it.
    """
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = settings

    if settings.metrics_enabled:
        install_metrics_middleware(app)
        app.include_router(metrics.router)

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(vehicles.router)
    app.include_router(rentals.router)
    app.include_router(customers.router)
    return app
