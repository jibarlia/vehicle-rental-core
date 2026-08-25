from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from vehicle_rental_core.cli import main as cli_main
from vehicle_rental_core.cli.main import _redact, app
from vehicle_rental_core.core.config import get_settings

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


class TestConfigCommand:
    def test_should_redact_the_database_password(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(
            "DATABASE_URL", "postgresql+psycopg://admin:s3cret@db:5432/rental"
        )

        result = runner.invoke(app, ["config"])

        assert result.exit_code == 0
        assert "s3cret" not in result.output
        assert "postgresql+psycopg://admin:***@db:5432/rental" in result.output


class TestHealthcheckCommand:
    """The ping itself is mocked — these cover the command's exit contract."""

    def test_should_exit_nonzero_when_the_database_is_unreachable(self) -> None:
        with patch.object(cli_main, "_ping_database", new_callable=AsyncMock) as ping:
            ping.side_effect = OSError("connection refused")

            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 1
        assert "database unreachable" in result.output

    def test_should_exit_zero_when_the_database_answers(self) -> None:
        with patch.object(cli_main, "_ping_database", new_callable=AsyncMock) as ping:
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 0
        assert "database reachable" in result.output
        ping.assert_awaited_once()


class TestRedact:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("postgresql+psycopg:///local", "postgresql+psycopg:///local"),
            ("postgresql+psycopg://db:5432/x", "postgresql+psycopg://db:5432/x"),
            ("postgresql+psycopg://u:p@h/d", "postgresql+psycopg://u:***@h/d"),
        ],
    )
    def test_should_only_mask_credentials_when_present(
        self, url: str, expected: str
    ) -> None:
        assert _redact(url) == expected
