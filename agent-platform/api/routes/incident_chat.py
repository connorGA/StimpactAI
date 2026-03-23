from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from openai import AsyncOpenAI

from api.core.config import get_openai_api_key, get_openai_chat_model
from api.core.errors import APIError
from api.core.security import require_project_list_access, require_project_read_access
from api.db.postgres import PostgresConnectionManager, get_postgres_manager
from api.repositories.control_plane_repository import ControlPlaneRepository
from api.repositories.incident_repository import IncidentRepository
from api.schemas.chat import GlobalIncidentChatRequest, IncidentChatResponse, IncidentDetailChatRequest
from services.code_context import CodeContextService
from services.failure_classifier import FailureClassifier
from services.incident_chat import IncidentChatService

router = APIRouter(prefix="/incidents", tags=["incident-chat"])


def get_incident_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> IncidentRepository:
    return IncidentRepository(manager.pool)


def get_control_plane_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> ControlPlaneRepository:
    return ControlPlaneRepository(manager.pool)


def get_failure_classifier() -> FailureClassifier:
    return FailureClassifier()


def get_code_context_service() -> CodeContextService:
    return CodeContextService()


def get_incident_chat_service(
    repository: IncidentRepository = Depends(get_incident_repository),
    classifier: FailureClassifier = Depends(get_failure_classifier),
    code_context: CodeContextService = Depends(get_code_context_service),
) -> IncidentChatService:
    api_key = get_openai_api_key()
    if api_key is None:
        raise APIError(
            "OPENAI_API_KEY is not configured for incident chat.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="openai_unconfigured",
        )

    return IncidentChatService(
        repository,
        client=AsyncOpenAI(api_key=api_key),
        model=get_openai_chat_model(),
        classifier=classifier,
        code_context=code_context,
    )


@router.post("/chat", response_model=IncidentChatResponse, status_code=status.HTTP_200_OK)
async def chat_about_incidents(
    request: Request,
    payload: GlobalIncidentChatRequest,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: IncidentChatService = Depends(get_incident_chat_service),
) -> IncidentChatResponse:
    await require_project_list_access(request, payload.project_id, repository=repository)
    return await service.chat_about_incidents(payload)


@router.post("/{incident_id}/chat", response_model=IncidentChatResponse, status_code=status.HTTP_200_OK)
async def chat_about_incident(
    request: Request,
    incident_id: str,
    payload: IncidentDetailChatRequest,
    incident_repository: IncidentRepository = Depends(get_incident_repository),
    control_plane_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: IncidentChatService = Depends(get_incident_chat_service),
) -> IncidentChatResponse:
    incident = await incident_repository.get_incident(incident_id)
    if incident is None:
        raise APIError(
            f"Incident {incident_id} was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="incident_not_found",
        )
    await require_project_read_access(
        request,
        incident.project_id,
        repository=control_plane_repository,
    )
    return await service.chat_about_incident(incident_id, payload)
