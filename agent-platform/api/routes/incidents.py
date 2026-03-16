from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from api.core.errors import APIError
from api.db.postgres import PostgresConnectionManager, get_postgres_manager
from api.repositories.incident_repository import IncidentRepository
from api.schemas.incidents import (
    IncidentDetailResponse,
    IncidentEventResponse,
    IncidentListResponse,
    IncidentSummaryResponse,
)
from models.incident import IncidentStatus

router = APIRouter(prefix="/incidents", tags=["incidents"])


def get_incident_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> IncidentRepository:
    return IncidentRepository(manager.pool)


@router.get("", response_model=IncidentListResponse, status_code=status.HTTP_200_OK)
async def list_incidents(
    repository: IncidentRepository = Depends(get_incident_repository),
    project_id: str | None = Query(default=None, min_length=1, max_length=128),
    status_filter: Annotated[IncidentStatus | None, Query(alias="status")] = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> IncidentListResponse:
    incidents, total = await repository.list_incidents(
        project_id=project_id,
        status=status_filter.value if status_filter is not None else None,
        limit=limit,
        offset=offset,
    )

    return IncidentListResponse(
        items=[IncidentSummaryResponse.from_record(incident) for incident in incidents],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{incident_id}", response_model=IncidentDetailResponse, status_code=status.HTTP_200_OK)
async def get_incident(
    incident_id: str,
    repository: IncidentRepository = Depends(get_incident_repository),
    event_limit: int = Query(default=100, ge=1, le=500),
) -> IncidentDetailResponse:
    incident = await repository.get_incident(incident_id)
    if incident is None:
        raise APIError(
            f"Incident {incident_id} was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="incident_not_found",
        )

    events = await repository.list_incident_events(incident_id, limit=event_limit)
    return IncidentDetailResponse(
        incident=IncidentSummaryResponse.from_record(incident),
        events=[IncidentEventResponse.from_record(event) for event in events],
    )
