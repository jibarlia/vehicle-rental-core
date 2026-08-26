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


def _plate(index: int) -> str:
    """Sequential, not random: the column has a unique index.

    Deterministic within a run and across runs, so seeding a clean database
    twice with the same --seed produces the same fleet. Seeding a database that
    already holds these plates fails loudly, which is the honest outcome.
    """
    return f"SD-{index:05d}"


async def _seed(
    settings: Settings, *, vehicles: int, customers: int, rentals: int, seed: int
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
                    registration_number=_plate(index),
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
                    # unique() because the email column has a unique index.
                    email=fake.unique.email(),
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


app_command_help = "Generate demo vehicles, customers and rentals."


def seed(
    vehicles: Annotated[int, typer.Option("--vehicles", min=0)] = 20,
    customers: Annotated[int, typer.Option("--customers", min=0)] = 10,
    rentals: Annotated[int, typer.Option("--rentals", min=0)] = 15,
    seed_value: Annotated[
        int, typer.Option("--seed", help="Makes a run reproducible.")
    ] = 42,
) -> None:
    """Generate demo vehicles, customers and rentals.

    Writes in-process through the services, so no server needs to be running —
    unlike the vehicle and rental commands, which drive the HTTP API.
    """
    settings = get_settings()
    try:
        created = asyncio.run(
            _seed(
                settings,
                vehicles=vehicles,
                customers=customers,
                rentals=rentals,
                seed=seed_value,
            )
        )
    except DomainError as exc:
        typer.secho(f"seeding stopped: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.secho(
        "created "
        f"{created['vehicles']} vehicles, "
        f"{created['customers']} customers, "
        f"{created['rentals']} rentals "
        f"({created['completed']} already ended)",
        fg=typer.colors.GREEN,
    )
