import logging
import sys
from logging.handlers import RotatingFileHandler

from vehicle_rental_core.core.config import Settings

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"

# Everything the logging module itself puts on a record; whatever is left came
# from a caller's ``extra=`` and is worth rendering.
_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class KeyValueFormatter(logging.Formatter):
    """Appends ``extra=`` fields as ``key=value``, leaving messages static.

    Without this the fields are accepted and then silently dropped, since the
    format string has no placeholder for them.
    """

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        fields = {
            key: value for key, value in record.__dict__.items() if key not in _RESERVED
        }
        if not fields:
            return formatted
        rendered = " ".join(f"{key}={value!r}" for key, value in fields.items())
        return f"{formatted} {rendered}"


def configure_logging(settings: Settings) -> None:
    """Install a stdout handler for the process, plus a file one if configured.

    ``force=True`` replaces handlers uvicorn may already have attached, so log
    lines keep a single consistent format instead of being emitted twice.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if settings.log_file is not None:
        settings.log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                settings.log_file,
                maxBytes=settings.log_file_max_bytes,
                backupCount=settings.log_file_backup_count,
                encoding="utf-8",
            )
        )

    formatter = KeyValueFormatter(_LOG_FORMAT)
    for handler in handlers:
        handler.setFormatter(formatter)

    logging.basicConfig(level=settings.log_level, handlers=handlers, force=True)
