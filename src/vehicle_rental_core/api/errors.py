import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

from vehicle_rental_core.domain.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)

logger = logging.getLogger(__name__)

# HTTP status is a presentation concern, so the mapping lives only here.
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


def _rejection(error: Exception, code: int) -> JSONResponse:
    logger.info(
        "A rule rejected the request",
        extra={"error": type(error).__name__, "status_code": code},
    )
    return JSONResponse(
        status_code=code,
        content={"detail": str(error), "error": type(error).__name__},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(_: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, DomainError)
        return _rejection(error, _status_for(error))

    # Entity constraints raise pydantic's error, which would otherwise be a
    # 500. RequestValidationError does not inherit from it, so request-body
    # validation is unaffected.
    @app.exception_handler(PydanticValidationError)
    async def handle_entity_validation_error(
        _: Request, error: Exception
    ) -> JSONResponse:
        return _rejection(error, status.HTTP_422_UNPROCESSABLE_CONTENT)

    # Anything reaching here is a bug, not a rejected rule, so it is logged with
    # a traceback and answered without leaking the exception text.
    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, error: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled error serving the request",
            extra={"error": type(error).__name__},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Internal server error",
                "error": "InternalServerError",
            },
        )
