import logging
from collections.abc import Iterator
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from vehicle_rental_core.core.config import Settings
from vehicle_rental_core.core.observability.logging import (
    KeyValueFormatter,
    configure_logging,
)


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    """``configure_logging`` uses ``force=True``, which closes pytest's handlers."""
    root = logging.getLogger()
    handlers = root.handlers[:]
    level = root.level
    root.handlers = []
    yield
    for handler in root.handlers:
        handler.close()
    root.handlers = handlers
    root.setLevel(level)


def _settings(**overrides: object) -> Settings:
    return Settings(
        environment="test",
        _env_file=None,  # type: ignore[call-arg]
        **overrides,  # type: ignore[arg-type]
    )


def _record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Event",
        args=None,
        exc_info=None,
    )
    record.__dict__.update(extra)
    return record


class TestConfigureLogging:
    def test_should_install_only_a_stdout_handler_when_no_log_file(self) -> None:
        configure_logging(_settings())

        handlers = logging.getLogger().handlers
        assert len(handlers) == 1
        assert isinstance(handlers[0], logging.StreamHandler)

    def test_should_add_a_rotating_file_handler_when_log_file_is_set(
        self, tmp_path: Path
    ) -> None:
        configure_logging(
            _settings(
                log_file=tmp_path / "app.log",
                log_file_max_bytes=2048,
                log_file_backup_count=3,
            )
        )

        handlers = logging.getLogger().handlers
        file_handlers = [h for h in handlers if isinstance(h, RotatingFileHandler)]
        assert len(handlers) == 2
        assert len(file_handlers) == 1
        assert file_handlers[0].maxBytes == 2048
        assert file_handlers[0].backupCount == 3

    def test_should_create_the_log_file_directory(self, tmp_path: Path) -> None:
        log_file = tmp_path / "nested" / "deeper" / "app.log"

        configure_logging(_settings(log_file=log_file))

        assert log_file.parent.is_dir()

    def test_should_write_records_to_the_log_file(self, tmp_path: Path) -> None:
        log_file = tmp_path / "app.log"
        configure_logging(_settings(log_file=log_file, log_level="INFO"))

        logging.getLogger("test").info("Vehicle created", extra={"vehicle_id": "abc"})
        for handler in logging.getLogger().handlers:
            handler.flush()

        contents = log_file.read_text(encoding="utf-8")
        assert "Vehicle created" in contents
        assert "vehicle_id='abc'" in contents

    def test_should_honour_the_configured_level(self, tmp_path: Path) -> None:
        log_file = tmp_path / "app.log"
        configure_logging(_settings(log_file=log_file, log_level="ERROR"))

        logging.getLogger("test").info("Vehicle created")
        for handler in logging.getLogger().handlers:
            handler.flush()

        assert log_file.read_text(encoding="utf-8") == ""


class TestKeyValueFormatter:
    def test_should_append_extra_fields_to_the_message(self) -> None:
        formatted = KeyValueFormatter("%(message)s").format(
            _record(vehicle_id="abc", fields=["model"])
        )

        assert formatted == "Event vehicle_id='abc' fields=['model']"

    def test_should_leave_a_record_without_extras_unchanged(self) -> None:
        formatted = KeyValueFormatter("%(message)s").format(_record())

        assert formatted == "Event"

    def test_should_not_treat_standard_attributes_as_extras(self) -> None:
        formatted = KeyValueFormatter("%(levelname)s %(name)s %(message)s").format(
            _record()
        )

        assert formatted == "INFO test Event"
