"""ASGI entrypoint — ``uvicorn vehicle_rental_core.main:app``."""

from vehicle_rental_core.api.app import create_app

app = create_app()
