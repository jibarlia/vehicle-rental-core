"""The vehicle commands, with the API stubbed at the HTTP boundary."""

import json
from typing import Any
from uuid import uuid4

import httpx
import pytest
from typer.testing import CliRunner

from vehicle_rental_core.cli.main import app
from vehicle_rental_core.core.config import get_settings

runner = CliRunner()

VEHICLE_ID = str(uuid4())
VEHICLE = {
    "id": VEHICLE_ID,
    "registration_number": "AA-111",
    "model": "Corolla",
    "year": 2022,
    "status": "available",
}


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


class TestAdd:
    def test_should_post_the_vehicle(self, stub_api: Any) -> None:
        seen = stub_api(httpx.Response(201, json=VEHICLE))

        result = runner.invoke(
            app, ["vehicle", "add", "-r", "AA-111", "-m", "Corolla", "-y", "2022"]
        )

        assert result.exit_code == 0
        assert seen[0].method == "POST"
        assert seen[0].url.path == "/vehicles"

    def test_should_exit_nonzero_on_a_conflict(self, stub_api: Any) -> None:
        stub_api(
            httpx.Response(
                409,
                json={
                    "detail": "already taken",
                    "error": "RegistrationNumberAlreadyExistsError",
                },
            )
        )

        result = runner.invoke(
            app, ["vehicle", "add", "-r", "AA-111", "-m", "Corolla", "-y", "2022"]
        )

        assert result.exit_code == 1
        assert "RegistrationNumberAlreadyExistsError" in result.output


class TestUpdate:
    def test_should_send_only_the_flags_passed(self, stub_api: Any) -> None:
        # An omitted field must stay omitted, not arrive as a null.
        seen = stub_api(httpx.Response(200, json=VEHICLE))

        result = runner.invoke(
            app, ["vehicle", "update", VEHICLE_ID, "--status", "maintenance"]
        )

        assert result.exit_code == 0
        assert json.loads(seen[0].content) == {"status": "maintenance"}

    def test_should_send_several_fields_together(self, stub_api: Any) -> None:
        seen = stub_api(httpx.Response(200, json=VEHICLE))

        runner.invoke(
            app, ["vehicle", "update", VEHICLE_ID, "-m", "Civic", "-y", "2023"]
        )

        assert json.loads(seen[0].content) == {"model": "Civic", "year": 2023}

    def test_should_refuse_an_update_with_nothing_to_change(
        self, stub_api: Any
    ) -> None:
        seen = stub_api(httpx.Response(200, json=VEHICLE))

        result = runner.invoke(app, ["vehicle", "update", VEHICLE_ID])

        assert result.exit_code != 0
        assert seen == []  # never reached the API

    def test_should_reject_an_unknown_status(self) -> None:
        result = runner.invoke(
            app, ["vehicle", "update", VEHICLE_ID, "--status", "banana"]
        )

        assert result.exit_code != 0


class TestList:
    def test_should_pass_the_status_filter_through(self, stub_api: Any) -> None:
        seen = stub_api(httpx.Response(200, json=[VEHICLE]))

        result = runner.invoke(app, ["vehicle", "list", "--status", "in_use"])

        assert result.exit_code == 0
        assert seen[0].url.params["status"] == "in_use"

    def test_should_omit_the_filter_when_not_given(self, stub_api: Any) -> None:
        seen = stub_api(httpx.Response(200, json=[VEHICLE]))

        runner.invoke(app, ["vehicle", "list"])

        assert "status" not in seen[0].url.params

    def test_should_report_an_unreachable_api(self, stub_api: Any) -> None:
        stub_api(raises=httpx.ConnectError("connection refused"))

        result = runner.invoke(app, ["vehicle", "list"])

        assert result.exit_code == 1
        assert "unreachable" in result.output
