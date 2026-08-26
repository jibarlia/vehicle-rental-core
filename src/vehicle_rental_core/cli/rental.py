"""Rental operations, driven through the HTTP API."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

import typer

from vehicle_rental_core.cli import _client

app = typer.Typer(help="Rental operations.", no_args_is_help=True)

BaseUrl = Annotated[
    str | None, typer.Option("--base-url", help="Override API_BASE_URL.")
]
AsJson = Annotated[bool, typer.Option("--json", help="Print the raw response.")]


@app.command()
def start(
    vehicle_id: Annotated[UUID, typer.Option("--vehicle-id", "-v")],
    customer_id: Annotated[UUID, typer.Option("--customer-id", "-c")],
    start_at: Annotated[
        datetime | None,
        typer.Option("--start-at", help="Defaults to now, server-side."),
    ] = None,
    base_url: BaseUrl = None,
    as_json: AsJson = False,
) -> None:
    """Register a rental, marking the vehicle in use.

    The customer's name is snapshotted server-side, so only their id is needed.
    """
    payload: dict[str, object] = {
        "vehicle_id": str(vehicle_id),
        "customer_id": str(customer_id),
    }
    if start_at is not None:
        payload["start_at"] = start_at.isoformat()

    created = _client.request("POST", "/rentals", override=base_url, json=payload)
    _client.render(created, as_json=as_json)


@app.command()
def end(
    rental_id: Annotated[UUID, typer.Argument(help="Rental to close.")],
    end_at: Annotated[
        datetime | None, typer.Option("--end-at", help="Defaults to now, server-side.")
    ] = None,
    base_url: BaseUrl = None,
    as_json: AsJson = False,
) -> None:
    """End a rental and release the vehicle."""
    payload: dict[str, object] = {}
    if end_at is not None:
        payload["end_at"] = end_at.isoformat()

    closed = _client.request(
        "POST", f"/rentals/{rental_id}/complete", override=base_url, json=payload
    )
    _client.render(closed, as_json=as_json)
