from fastapi import APIRouter, Response

from vehicle_rental_core.core.observability.metrics import render_latest

router = APIRouter(tags=["observability"])


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return render_latest()
