from fastapi import FastAPI


def test_asgi_entrypoint_should_expose_an_app() -> None:
    # Guards `uvicorn vehicle_rental_core.main:app`, the Docker CMD target.
    from vehicle_rental_core.main import app

    assert isinstance(app, FastAPI)
