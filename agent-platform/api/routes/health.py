from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from api.core.config import should_fail_readiness_when_degraded
from api.db.postgres import PostgresConnectionManager, get_postgres_manager
from api.observability import get_metrics_registry

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness() -> dict[str, object]:
    return {"status": "ok", "service": "agent-platform"}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness(
    response: Response,
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> dict[str, object]:
    database_ready = await manager.ping()
    status_label = "ready" if database_ready else "degraded"
    if should_fail_readiness_when_degraded() and not database_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": status_label,
        "checks": {
            "database": {
                "configured": manager.is_configured,
                "ready": database_ready,
            }
        },
        "strict": should_fail_readiness_when_degraded(),
    }


@router.get("/metrics", status_code=status.HTTP_200_OK)
async def metrics() -> Response:
    return Response(
        content=get_metrics_registry().render_prometheus(),
        media_type="text/plain; version=0.0.4",
    )
