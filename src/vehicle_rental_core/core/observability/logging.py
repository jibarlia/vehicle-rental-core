import logging
import sys

from vehicle_rental_core.core.config import Settings

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"


def configure_logging(settings: Settings) -> None:
    """Install one stdout handler for the process.

    ``force=True`` replaces handlers uvicorn may already have attached, so log
    lines keep a single consistent format instead of being emitted twice.
    """
    logging.basicConfig(
        level=settings.log_level,
        format=_LOG_FORMAT,
        stream=sys.stdout,
        force=True,
    )
