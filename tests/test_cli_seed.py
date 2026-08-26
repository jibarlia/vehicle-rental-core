"""The seed command, with the database and services stubbed out.

Unlike the vehicle and rental commands, seeding writes in-process through the
services, so what is faked here is the session factory rather than HTTP.
"""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from typer.testing import CliRunner

from vehicle_rental_core.cli import seed as seed_module
from vehicle_rental_core.cli.main import app
from vehicle_rental_core.core.config import get_settings
from vehicle_rental_core.domain.customer import Customer
from vehicle_rental_core.domain.errors import RegistrationNumberAlreadyExistsError
from vehicle_rental_core.domain.rental import Rental
from vehicle_rental_core.domain.vehicle import Vehicle

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


@pytest.fixture
def services(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Replace the three services and the engine the command builds itself."""
    vehicles = AsyncMock()
    vehicles.create.side_effect = lambda **kwargs: Vehicle(
        registration_number=kwargs["registration_number"],
        model=kwargs["model"],
        year=kwargs["year"],
    )
    customers = AsyncMock()
    customers.create.side_effect = lambda **kwargs: Customer(
        name=kwargs["name"],
        email=kwargs["email"],
        date_of_birth=kwargs["date_of_birth"],
        sex=kwargs["sex"],
    )
    rentals = AsyncMock()
    rentals.start.side_effect = lambda **kwargs: Rental(
        vehicle_id=kwargs["vehicle_id"],
        customer_id=kwargs["customer_id"],
        customer_name="seeded",
        start_at=kwargs["start_at"],
    )

    monkeypatch.setattr(seed_module, "VehicleService", lambda *a: vehicles)
    monkeypatch.setattr(seed_module, "CustomerService", lambda *a: customers)
    monkeypatch.setattr(seed_module, "RentalService", lambda *a: rentals)
    monkeypatch.setattr(seed_module, "VehicleRepository", lambda *a: MagicMock())
    monkeypatch.setattr(seed_module, "CustomerRepository", lambda *a: MagicMock())
    monkeypatch.setattr(seed_module, "RentalRepository", lambda *a: MagicMock())

    engine = AsyncMock()
    monkeypatch.setattr(seed_module, "create_engine", lambda settings: engine)

    session = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session
    factory.return_value.__aexit__.return_value = None
    monkeypatch.setattr(seed_module, "create_session_factory", lambda e: factory)

    return {"vehicles": vehicles, "customers": customers, "rentals": rentals}


class TestSeed:
    def test_should_create_the_requested_counts(
        self, services: dict[str, AsyncMock]
    ) -> None:
        result = runner.invoke(
            app, ["seed", "--vehicles", "5", "--customers", "3", "--rentals", "2"]
        )

        assert result.exit_code == 0
        assert services["vehicles"].create.await_count == 5
        assert services["customers"].create.await_count == 3
        assert services["rentals"].start.await_count == 2

    def test_should_not_open_more_rentals_than_there_are_vehicles(
        self, services: dict[str, AsyncMock]
    ) -> None:
        # One active rental per vehicle is a database guarantee; asking for more
        # rentals than vehicles must not try to violate it.
        result = runner.invoke(
            app, ["seed", "--vehicles", "2", "--customers", "2", "--rentals", "10"]
        )

        assert result.exit_code == 0
        assert services["rentals"].start.await_count == 2

    def test_should_be_reproducible_for_a_given_seed(
        self, services: dict[str, AsyncMock]
    ) -> None:
        runner.invoke(
            app, ["seed", "--vehicles", "4", "--customers", "4", "--seed", "7"]
        )
        first = [
            c.kwargs["email"] for c in services["customers"].create.await_args_list
        ]

        services["customers"].create.reset_mock()
        runner.invoke(
            app, ["seed", "--vehicles", "4", "--customers", "4", "--seed", "7"]
        )
        second = [
            c.kwargs["email"] for c in services["customers"].create.await_args_list
        ]

        assert first == second

    def test_should_differ_for_a_different_seed(
        self, services: dict[str, AsyncMock]
    ) -> None:
        runner.invoke(
            app, ["seed", "--vehicles", "4", "--customers", "4", "--seed", "1"]
        )
        first = [c.kwargs["name"] for c in services["customers"].create.await_args_list]

        services["customers"].create.reset_mock()
        runner.invoke(
            app, ["seed", "--vehicles", "4", "--customers", "4", "--seed", "2"]
        )
        second = [
            c.kwargs["name"] for c in services["customers"].create.await_args_list
        ]

        assert first != second

    def test_should_generate_plates_that_cannot_collide_within_a_run(
        self, services: dict[str, AsyncMock]
    ) -> None:
        # The column has a unique index, so a random plate would eventually
        # abort a large run.
        runner.invoke(app, ["seed", "--vehicles", "50", "--customers", "1"])

        plates = [
            call.kwargs["registration_number"]
            for call in services["vehicles"].create.await_args_list
        ]
        assert len(plates) == len(set(plates))

    def test_should_generate_adult_birth_dates(
        self, services: dict[str, AsyncMock]
    ) -> None:
        runner.invoke(app, ["seed", "--vehicles", "1", "--customers", "10"])

        today = datetime.now(UTC).date()
        for call in services["customers"].create.await_args_list:
            born: date = call.kwargs["date_of_birth"]
            assert born < today

    def test_should_stop_cleanly_on_a_domain_error(
        self, services: dict[str, AsyncMock]
    ) -> None:
        # Seeding a database that already holds these rows is a real outcome,
        # and it should read as a message rather than a traceback.
        services["vehicles"].create.side_effect = RegistrationNumberAlreadyExistsError(
            "SD-00000 is taken"
        )

        result = runner.invoke(app, ["seed", "--vehicles", "1", "--customers", "1"])

        assert result.exit_code == 1
        assert "seeding stopped" in result.output

    def test_should_skip_rentals_when_there_is_nothing_to_rent(
        self, services: dict[str, AsyncMock]
    ) -> None:
        result = runner.invoke(
            app, ["seed", "--vehicles", "0", "--customers", "0", "--rentals", "5"]
        )

        assert result.exit_code == 0
        services["rentals"].start.assert_not_awaited()


class TestPlate:
    def test_should_be_zero_padded_and_sequential(self) -> None:
        assert seed_module._plate(0) == "SD-00000"
        assert seed_module._plate(42) == "SD-00042"


class TestLazyFakerImport:
    def test_should_import_faker_only_when_seeding_runs(self) -> None:
        # A top-level import would break `vrc --help` on an install without
        # dev dependencies, since main.py imports this module to register it.
        source = seed_module.__file__ or ""
        assert source
        with open(source) as handle:
            head = handle.read().split("def _import_faker")[0]
        assert "import faker" not in head
        assert "from faker" not in head
