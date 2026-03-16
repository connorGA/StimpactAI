from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from openai import AsyncOpenAI

from api.core.config import get_openai_api_key, get_openai_rca_model
from api.core.errors import APIError
from api.db.postgres import PostgresConnectionManager, get_postgres_manager
from api.repositories.incident_repository import IncidentRepository
from api.schemas.incidents import (
    IncidentClassificationResponse,
    IncidentDetailResponse,
    IncidentEventResponse,
    IncidentRootCauseResponse,
    IncidentListResponse,
    IncidentSummaryResponse,
)
from models.incident import IncidentStatus
from services.failure_classifier import FailureClassifier
from services.root_cause_analysis import (
    RootCauseAnalysisService,
    RootCauseAnalyzer,
    RootCauseReasoner,
)

router = APIRouter(prefix="/incidents", tags=["incidents"])


def get_incident_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> IncidentRepository:
    return IncidentRepository(manager.pool)


def get_failure_classifier() -> FailureClassifier:
    return FailureClassifier()


def get_root_cause_analysis_service(
    repository: IncidentRepository = Depends(get_incident_repository),
    classifier: FailureClassifier = Depends(get_failure_classifier),
) -> RootCauseAnalysisService:
    api_key = get_openai_api_key()
    if api_key is None:
        raise APIError(
            "OPENAI_API_KEY is not configured for root cause analysis.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="openai_unconfigured",
        )

    return RootCauseAnalysisService(
        repository,
        classifier=classifier,
        analyzer=RootCauseAnalyzer(),
        reasoner=RootCauseReasoner(
            client=AsyncOpenAI(api_key=api_key),
            model=get_openai_rca_model(),
        ),
    )


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


@router.get(
    "/{incident_id}/classification",
    response_model=IncidentClassificationResponse,
    status_code=status.HTTP_200_OK,
)
async def classify_incident(
    incident_id: str,
    repository: IncidentRepository = Depends(get_incident_repository),
    classifier: FailureClassifier = Depends(get_failure_classifier),
    event_limit: int = Query(default=50, ge=1, le=200),
) -> IncidentClassificationResponse:
    incident = await repository.get_incident(incident_id)
    if incident is None:
        raise APIError(
            f"Incident {incident_id} was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="incident_not_found",
        )

    events = await repository.list_incident_events(incident_id, limit=event_limit)
    classification = classifier.classify(incident, events)
    return IncidentClassificationResponse.from_classification(
        incident_id=incident.id,
        classification=classification,
    )


@router.get(
    "/{incident_id}/root-cause",
    response_model=IncidentRootCauseResponse,
    status_code=status.HTTP_200_OK,
)
async def analyze_root_cause(
    incident_id: str,
    service: RootCauseAnalysisService = Depends(get_root_cause_analysis_service),
    event_limit: int = Query(default=50, ge=1, le=200),
) -> IncidentRootCauseResponse:
    analysis = await service.analyze_incident(incident_id, event_limit=event_limit)
    return IncidentRootCauseResponse.from_analysis(analysis)
