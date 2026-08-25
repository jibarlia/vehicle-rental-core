import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from vehicle_rental_core.api.dependencies import SessionDep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def liveness() -> dict[str, str]:
    """Liveness: the process is up. Deliberately touches no dependency."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(session: SessionDep, response: Response) -> dict[str, str]:
    """Readiness: the service can actually serve traffic.

    Returns 503 rather than raising so an orchestrator sees a plain unhealthy
    signal and keeps the pod out of rotation instead of restarting it.
    """
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness probe failed: database unreachable")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "database": "unreachable"}

    return {"status": "ok", "database": "reachable"}
