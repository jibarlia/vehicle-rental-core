"""Generate demo data straight through the services.

Deliberately the opposite of the vehicle/rental commands: those are HTTP
clients, this reaches into the application layer in-process. Bulk generation
should not need a running server or pay a round trip per row — and going
through the services rather than raw SQL means the generated data obeys every
rule the real callers do.
"""

import asyncio
import random
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

import typer

from vehicle_rental_core.application.customer_service import CustomerService
from vehicle_rental_core.application.rental_service import RentalService
from vehicle_rental_core.application.vehicle_service import VehicleService
from vehicle_rental_core.core.config import Settings, get_settings
from vehicle_rental_core.domain.enums import Sex, VehicleType
from vehicle_rental_core.domain.errors import DomainError
from vehicle_rental_core.infrastructure.db import create_engine, create_session_factory
from vehicle_rental_core.infrastructure.repositories.customer_repository import (
    CustomerRepository,
)
from vehicle_rental_core.infrastructure.repositories.rental_repository import (
    RentalRepository,
)
from vehicle_rental_core.infrastructure.repositories.vehicle_repository import (
    VehicleRepository,
)

# Roughly a third of generated rentals are closed, so the data has history
# rather than only open rentals.
_COMPLETED_SHARE = 0.4

_MODELS = (
    "Corolla",
    "Civic",
    "Golf",
    "Focus",
    "Astra",
    "Clio",
    "Polo",
    "Yaris",
    "Fiesta",
    "Ibiza",
)


def _import_faker() -> Any:
    """Import faker only when seeding actually runs.

    faker is a dev dependency: cli/main.py imports this module to register the
    command, so a top-level import would break `vrc --help` entirely on a
    production install.
    """
    try:
        from faker import Faker
    except ModuleNotFoundError as exc:  # pragma: no cover - environment specific
        raise typer.BadParameter(
            "vrc seed needs faker, a dev dependency. Install it with 'uv sync'."
        ) from exc
    return Faker


def _run_token() -> int:
    """A fresh five-digit token identifying this batch.

    Drawn from system entropy rather than from ``--seed``, because its job is
    the opposite one: ``--seed`` makes a run *reproducible*, this makes a run
    *distinct*. Both ``registration_number`` and ``email`` carry unique
    indexes, so without a per-run token a second seeding would collide on its
    very first row.

    Two runs landing on the same token is a 1-in-100,000 draw; it surfaces as a
    plain "already taken" error, and running again picks a new one.
    """
    return random.SystemRandom().randrange(100_000)


def _plate(token: int, index: int) -> str:
    """An eight-digit Israeli plate, ``NNN-NN-NNN``.

    The leading five digits are the run token and the trailing three are the
    vehicle's index, which keeps every plate in a run distinct without a
    round trip to check, and keeps runs from colliding with each other. The
    layout caps a single run at 1,000 vehicles.
    """
    digits = f"{token:05d}{index:03d}"
    return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"


def _email(token: int, address: str) -> str:
    """Tag a generated address with the run token.

    Faker's ``unique`` proxy only promises uniqueness within one process, so
    two runs on the same ``--seed`` would generate the same addresses against a
    column that will not have them twice. Sub-addressing keeps the name
    readable — ``ada@example.com`` becomes ``ada+04217@example.com``.
    """
    local, _, domain = address.partition("@")
    return f"{local}+{token:05d}@{domain}"


async def _seed(
    settings: Settings,
    *,
    vehicles: int,
    customers: int,
    rentals: int,
    seed: int,
    token: int,
) -> dict[str, int]:
    faker_class = _import_faker()
    faker_class.seed(seed)
    fake = faker_class()
    rng = random.Random(seed)

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    created = {"vehicles": 0, "customers": 0, "rentals": 0, "completed": 0}

    try:
        async with session_factory() as session:
            vehicle_service = VehicleService(
                session, VehicleRepository(session), RentalRepository(session)
            )
            customer_service = CustomerService(session, CustomerRepository(session))
            rental_service = RentalService(
                session,
                RentalRepository(session),
                VehicleRepository(session),
                CustomerRepository(session),
            )

            vehicle_ids = []
            for index in range(vehicles):
                vehicle = await vehicle_service.create(
                    registration_number=_plate(token, index),
                    model=rng.choice(_MODELS),
                    year=rng.randint(2010, datetime.now(UTC).year),
                    vehicle_type=VehicleType.CAR,
                )
                vehicle_ids.append(vehicle.id)
                created["vehicles"] += 1

            customer_ids = []
            for _ in range(customers):
                customer = await customer_service.create(
                    name=fake.name(),
                    # unique() keeps addresses distinct inside this run; the
                    # run token keeps them distinct from every earlier one.
                    email=_email(token, fake.unique.email()),
                    date_of_birth=_birth_date(rng),
                    sex=rng.choice(list(Sex)),
                )
                customer_ids.append(customer.id)
                created["customers"] += 1

            if not vehicle_ids or not customer_ids:
                return created

            # One active rental per vehicle is enforced by a partial unique
            # index, so a vehicle is used at most once for an open rental.
            available = rng.sample(vehicle_ids, k=min(rentals, len(vehicle_ids)))
            for vehicle_id in available:
                started = await rental_service.start(
                    vehicle_id=vehicle_id,
                    customer_id=rng.choice(customer_ids),
                    start_at=_start_date(rng),
                )
                created["rentals"] += 1

                if rng.random() < _COMPLETED_SHARE:
                    await rental_service.complete(started.id)
                    created["completed"] += 1
    finally:
        await engine.dispose()

    return created


def _birth_date(rng: random.Random) -> date:
    today = datetime.now(UTC).date()
    return today - timedelta(days=rng.randint(18 * 365, 80 * 365))


def _start_date(rng: random.Random) -> datetime:
    return datetime.now(UTC) - timedelta(hours=rng.randint(1, 30 * 24))


def seed(
    vehicles: Annotated[int, typer.Option("--vehicles", min=0)] = 20,
    customers: Annotated[int, typer.Option("--customers", min=0)] = 10,
    rentals: Annotated[int, typer.Option("--rentals", min=0)] = 15,
    seed_value: Annotated[
        int, typer.Option("--seed", help="Fixes the names, models and dates.")
    ] = 42,
    token: Annotated[
        int | None,
        typer.Option(
            "--token",
            min=0,
            max=99_999,
            help="Batch id for plates and emails. Random unless given.",
        ),
    ] = None,
) -> None:
    """Generate demo vehicles, customers and rentals.

    Writes in-process through the services, so no server needs to be running —
    unlike the vehicle and rental commands, which drive the HTTP API.

    Safe to run repeatedly: every run draws a new batch token, so its plates
    and email addresses cannot collide with an earlier run's. Each run *adds*
    a batch rather than replacing one, so three runs leave three batches.
    """
    settings = get_settings()
    batch = _run_token() if token is None else token
    try:
        created = asyncio.run(
            _seed(
                settings,
                vehicles=vehicles,
                customers=customers,
                rentals=rentals,
                seed=seed_value,
                token=batch,
            )
        )
    except DomainError as exc:
        typer.secho(f"seeding stopped: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    # The token is echoed because it is how you tell one batch from another:
    # every plate in this run starts with it.
    typer.secho(
        f"batch {batch:05d}: created "
        f"{created['vehicles']} vehicles, "
        f"{created['customers']} customers, "
        f"{created['rentals']} rentals "
        f"({created['completed']} already ended)",
        fg=typer.colors.GREEN,
    )
