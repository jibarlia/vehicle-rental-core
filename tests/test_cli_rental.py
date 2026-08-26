"""The rental commands, with the API stubbed at the HTTP boundary."""

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
CUSTOMER_ID = str(uuid4())
RENTAL_ID = str(uuid4())
RENTAL = {
    "id": RENTAL_ID,
    "vehicle_id": VEHICLE_ID,
    "customer_id": CUSTOMER_ID,
    "customer_name": "Ada Lovelace",
    "start_at": "2026-06-01T00:00:00Z",
    "end_at": None,
}


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


class TestStart:
    def test_should_post_both_ids(self, stub_api: Any) -> None:
        seen = stub_api(httpx.Response(201, json=RENTAL))

        result = runner.invoke(
            app, ["rental", "start", "-v", VEHICLE_ID, "-c", CUSTOMER_ID]
        )

        assert result.exit_code == 0
        assert seen[0].url.path == "/rentals"
        assert json.loads(seen[0].content) == {
            "vehicle_id": VEHICLE_ID,
            "customer_id": CUSTOMER_ID,
        }

    def test_should_omit_start_at_when_not_given(self, stub_api: Any) -> None:
        # Absent means "now, server-side" — not a null the API must interpret.
        seen = stub_api(httpx.Response(201, json=RENTAL))

        runner.invoke(app, ["rental", "start", "-v", VEHICLE_ID, "-c", CUSTOMER_ID])

        assert "start_at" not in json.loads(seen[0].content)

    def test_should_send_start_at_when_given(self, stub_api: Any) -> None:
        seen = stub_api(httpx.Response(201, json=RENTAL))

        runner.invoke(
            app,
            [
                "rental",
                "start",
                "-v",
                VEHICLE_ID,
                "-c",
                CUSTOMER_ID,
                "--start-at",
                "2026-06-01T09:00:00",
            ],
        )

        assert json.loads(seen[0].content)["start_at"].startswith("2026-06-01T09:00")

    def test_should_report_an_unknown_customer(self, stub_api: Any) -> None:
        stub_api(
            httpx.Response(
                404,
                json={
                    "detail": f"Customer {CUSTOMER_ID} not found.",
                    "error": "CustomerNotFoundError",
                },
            )
        )

        result = runner.invoke(
            app, ["rental", "start", "-v", VEHICLE_ID, "-c", CUSTOMER_ID]
        )

        assert result.exit_code == 1
        assert "CustomerNotFoundError" in result.output

    def test_should_report_an_unrentable_vehicle(self, stub_api: Any) -> None:
        stub_api(
            httpx.Response(
                409,
                json={
                    "detail": "is in_use, not available.",
                    "error": "VehicleNotRentableError",
                },
            )
        )

        result = runner.invoke(
            app, ["rental", "start", "-v", VEHICLE_ID, "-c", CUSTOMER_ID]
        )

        assert result.exit_code == 1
        assert "VehicleNotRentableError" in result.output

    def test_should_reject_a_malformed_id(self) -> None:
        result = runner.invoke(
            app, ["rental", "start", "-v", "not-a-uuid", "-c", CUSTOMER_ID]
        )

        assert result.exit_code != 0


class TestEnd:
    def test_should_post_to_the_complete_endpoint(self, stub_api: Any) -> None:
        seen = stub_api(httpx.Response(200, json={**RENTAL, "end_at": "2026-06-05"}))

        result = runner.invoke(app, ["rental", "end", RENTAL_ID])

        assert result.exit_code == 0
        assert seen[0].url.path == f"/rentals/{RENTAL_ID}/complete"

    def test_should_send_an_empty_body_when_no_end_given(self, stub_api: Any) -> None:
        seen = stub_api(httpx.Response(200, json=RENTAL))

        runner.invoke(app, ["rental", "end", RENTAL_ID])

        assert json.loads(seen[0].content) == {}

    def test_should_report_an_already_ended_rental(self, stub_api: Any) -> None:
        stub_api(
            httpx.Response(
                409,
                json={
                    "detail": "already ended.",
                    "error": "RentalAlreadyEndedError",
                },
            )
        )

        result = runner.invoke(app, ["rental", "end", RENTAL_ID])

        assert result.exit_code == 1
        assert "RentalAlreadyEndedError" in result.output

    def test_should_report_an_unknown_rental(self, stub_api: Any) -> None:
        stub_api(
            httpx.Response(
                404,
                json={"detail": "not found.", "error": "RentalNotFoundError"},
            )
        )

        result = runner.invoke(app, ["rental", "end", str(uuid4())])

        assert result.exit_code == 1
        assert "RentalNotFoundError" in result.output
