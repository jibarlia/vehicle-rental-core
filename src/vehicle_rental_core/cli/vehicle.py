"""Vehicle operations, driven through the HTTP API."""

from typing import Annotated
from uuid import UUID

import typer

from vehicle_rental_core.cli import _client
from vehicle_rental_core.domain.enums import VehicleStatus, VehicleType

app = typer.Typer(help="Vehicle operations.", no_args_is_help=True)

# The columns worth seeing in a fleet listing; the full record is a --json away.
_LIST_COLUMNS = ["id", "registration_number", "model", "year", "status"]

BaseUrl = Annotated[
    str | None, typer.Option("--base-url", help="Override API_BASE_URL.")
]
AsJson = Annotated[bool, typer.Option("--json", help="Print the raw response.")]


@app.command()
def add(
    registration_number: Annotated[
        str, typer.Option("--registration-number", "-r", help="Licence plate.")
    ],
    model: Annotated[str, typer.Option("--model", "-m", help="Model name.")],
    year: Annotated[int, typer.Option("--year", "-y", help="Model year.")],
    vehicle_type: Annotated[
        VehicleType, typer.Option("--type", help="Kind of vehicle.")
    ] = VehicleType.CAR,
    base_url: BaseUrl = None,
    as_json: AsJson = False,
) -> None:
    """Add a vehicle to the fleet."""
    created = _client.request(
        "POST",
        "/vehicles",
        override=base_url,
        json={
            "registration_number": registration_number,
            "model": model,
            "year": year,
            "vehicle_type": vehicle_type.value,
        },
    )
    _client.render(created, as_json=as_json)


@app.command()
def update(
    vehicle_id: Annotated[UUID, typer.Argument(help="Vehicle to change.")],
    model: Annotated[str | None, typer.Option("--model", "-m")] = None,
    year: Annotated[int | None, typer.Option("--year", "-y")] = None,
    status: Annotated[
        VehicleStatus | None, typer.Option("--status", "-s", help="New status.")
    ] = None,
    base_url: BaseUrl = None,
    as_json: AsJson = False,
) -> None:
    """Change a vehicle's details or status.

    Only the flags actually passed are sent, so an omitted field stays omitted
    rather than arriving as a null the API would have to guess about.
    """
    changes: dict[str, object] = {}
    if model is not None:
        changes["model"] = model
    if year is not None:
        changes["year"] = year
    if status is not None:
        changes["status"] = status.value

    if not changes:
        raise typer.BadParameter("Pass at least one of --model, --year or --status.")

    updated = _client.request(
        "PATCH", f"/vehicles/{vehicle_id}", override=base_url, json=changes
    )
    _client.render(updated, as_json=as_json)


@app.command(name="list")
def list_vehicles(
    status: Annotated[
        VehicleStatus | None, typer.Option("--status", "-s", help="Filter by status.")
    ] = None,
    offset: Annotated[int, typer.Option("--offset", min=0)] = 0,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 20,
    base_url: BaseUrl = None,
    as_json: AsJson = False,
) -> None:
    """List the fleet, optionally filtered by status.

    Retired vehicles are hidden unless asked for by name (``--status retired``),
    which is the API's rule, not a second one invented here.
    """
    params: dict[str, object] = {"offset": offset, "limit": limit}
    if status is not None:
        params["status"] = status.value

    vehicles = _client.request("GET", "/vehicles", override=base_url, params=params)
    _client.render(vehicles, as_json=as_json, columns=_LIST_COLUMNS)
