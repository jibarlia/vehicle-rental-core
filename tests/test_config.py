import pytest
from pydantic import ValidationError

from vehicle_rental_core.core.config import Settings, get_settings


class TestSettings:
    def test_defaults_should_describe_a_local_environment(self) -> None:
        settings = Settings(_env_file=None)  # type: ignore[call-arg]

        assert settings.app_name == "vehicle-rental-core"
        assert settings.environment == "local"
        assert settings.debug is False
        assert settings.database_url.startswith("postgresql+psycopg://")

    def test_environment_variables_should_override_defaults(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("APP_NAME", "override")
        monkeypatch.setenv("API_PORT", "9001")

        settings = Settings(_env_file=None)  # type: ignore[call-arg]

        assert settings.app_name == "override"
        assert settings.api_port == 9001

    def test_unknown_environment_should_be_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(environment="prod", _env_file=None)  # type: ignore[arg-type,call-arg]

    def test_out_of_range_port_should_be_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(api_port=70000, _env_file=None)  # type: ignore[call-arg]


def test_get_settings_should_return_a_cached_instance() -> None:
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()
