import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from vehicle_rental_core.domain.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)

logger = logging.getLogger(__name__)

# Domain errors carry business meaning; HTTP status is a presentation concern,
# so the mapping lives here and nowhere else.
_STATUS_BY_ERROR: tuple[tuple[type[DomainError], int], ...] = (
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (ConflictError, status.HTTP_409_CONFLICT),
    (ValidationError, status.HTTP_422_UNPROCESSABLE_CONTENT),
)


def _status_for(error: DomainError) -> int:
    for error_type, code in _STATUS_BY_ERROR:
        if isinstance(error, error_type):
            return code
    return status.HTTP_400_BAD_REQUEST


def install_domain_error_handler(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(_: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, DomainError)
        code = _status_for(error)
        logger.info(
            "Domain rule rejected the request",
            extra={"error": type(error).__name__, "status_code": code},
        )
        return JSONResponse(
            status_code=code,
            content={"detail": str(error), "error": type(error).__name__},
        )
