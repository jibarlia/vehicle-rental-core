"""Generate demo data in-process through the services, not over HTTP."""

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

# Share of generated rentals that are closed, so the data has history.
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
    """Import faker only when seeding runs.

    It is a dev dependency, and cli/main.py imports this module to register the
    command, so a top-level import would break ``vrc --help`` in production.
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

    Drawn from system entropy, not ``--seed``: that makes a run reproducible,
    this makes it distinct, which the unique indexes on ``registration_number``
    and ``email`` require.
    """
    return random.SystemRandom().randrange(100_000)


def _plate(token: int, index: int) -> str:
    """An eight-digit Israeli plate, ``NNN-NN-NNN``.

    Five digits of run token then three of vehicle index, which caps a single
    run at 1,000 vehicles.
    """
    digits = f"{token:05d}{index:03d}"
    return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"


def _email(token: int, address: str) -> str:
    """Tag a generated address with the run token.

    Faker's ``unique`` proxy only promises uniqueness within one process, so
    two runs on the same ``--seed`` would repeat addresses.
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
                    email=_email(token, fake.unique.email()),
                    date_of_birth=_birth_date(rng),
                    sex=rng.choice(list(Sex)),
                )
                customer_ids.append(customer.id)
                created["customers"] += 1

            if not vehicle_ids or not customer_ids:
                return created

            # A partial unique index allows one open rental per vehicle.
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

    Writes in-process, so no server need be running. Safe to run repeatedly:
    each run adds a batch under a new token rather than replacing one.
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

    # Echoed because every plate in the run starts with it.
    typer.secho(
        f"batch {batch:05d}: created "
        f"{created['vehicles']} vehicles, "
        f"{created['customers']} customers, "
        f"{created['rentals']} rentals "
        f"({created['completed']} already ended)",
        fg=typer.colors.GREEN,
    )
