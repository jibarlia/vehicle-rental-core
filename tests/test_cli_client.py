"""The CLI's HTTP boundary: how failures read and how results print.

The `stub_api` fixture stands in for the network — no server, no socket.
"""

from typing import Any

import httpx
import pytest
import typer

from vehicle_rental_core.cli import _client
from vehicle_rental_core.core.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


class TestBaseUrl:
    def test_should_prefer_the_explicit_override(self) -> None:
        assert _client.base_url("http://elsewhere:9000") == "http://elsewhere:9000"

    def test_should_fall_back_to_settings(self) -> None:
        assert _client.base_url(None) == "http://localhost:8000"

    def test_should_strip_a_trailing_slash(self) -> None:
        # Otherwise every URL would carry a double slash before the path.
        assert _client.base_url("http://localhost:8000/") == "http://localhost:8000"


class TestSuccess:
    def test_should_return_the_decoded_body(self, stub_api: Any) -> None:
        stub_api(httpx.Response(200, json={"id": "abc"}))

        assert _client.request("GET", "/vehicles") == {"id": "abc"}

    def test_should_return_none_for_a_204(self, stub_api: Any) -> None:
        # 204 carries no body, so json() would raise.
        stub_api(httpx.Response(204))

        assert _client.request("DELETE", "/customers/x") is None


class TestFailure:
    def test_should_report_the_domain_error_name_and_detail(
        self, stub_api: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The envelope the API's exception handlers produce.
        stub_api(
            httpx.Response(
                404,
                json={
                    "detail": "Vehicle abc not found.",
                    "error": "VehicleNotFoundError",
                },
            )
        )

        with pytest.raises(typer.Exit) as exit_info:
            _client.request("GET", "/vehicles/abc")

        assert exit_info.value.exit_code == 1
        output = capsys.readouterr().out
        assert "VehicleNotFoundError" in output
        assert "Vehicle abc not found." in output

    def test_should_flatten_fastapis_validation_detail(
        self, stub_api: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # FastAPI nests request-validation errors as a list, unlike ours.
        stub_api(
            httpx.Response(
                422,
                json={
                    "detail": [
                        {"loc": ["body", "year"], "msg": "input should be an integer"}
                    ]
                },
            )
        )

        with pytest.raises(typer.Exit):
            _client.request("POST", "/vehicles")

        assert "body.year" in capsys.readouterr().out

    def test_should_survive_a_response_that_is_not_json(
        self, stub_api: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # A proxy or a crash can return HTML; it must not mask the status.
        stub_api(httpx.Response(502, text="<html>bad gateway"))

        with pytest.raises(typer.Exit):
            _client.request("GET", "/vehicles")

        assert "502" in capsys.readouterr().out

    def test_should_name_the_unreachable_url(
        self, stub_api: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        stub_api(raises=httpx.ConnectError("connection refused"))

        with pytest.raises(typer.Exit) as exit_info:
            _client.request("GET", "/vehicles", override="http://localhost:9999")

        assert exit_info.value.exit_code == 1
        output = capsys.readouterr().out
        assert "unreachable" in output
        assert "http://localhost:9999" in output


class TestRender:
    def test_should_print_a_table_for_a_list(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _client.render(
            [{"id": "1", "model": "Corolla"}], as_json=False, columns=["model"]
        )

        assert "Corolla" in capsys.readouterr().out

    def test_should_say_so_when_a_list_is_empty(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # An empty table would look like a rendering failure.
        _client.render([], as_json=False)

        assert "no results" in capsys.readouterr().out

    def test_should_print_raw_json_when_asked(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _client.render({"id": "abc"}, as_json=True)

        assert '"id"' in capsys.readouterr().out
