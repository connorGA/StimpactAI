from __future__ import annotations

from fastapi import APIRouter, Depends, status
from openai import AsyncOpenAI

from api.core.config import get_openai_api_key, get_openai_model
from api.core.errors import APIError
from api.db.postgres import PostgresConnectionManager, get_postgres_manager
from api.repositories.incident_repository import IncidentRepository
from api.schemas.chat import GlobalIncidentChatRequest, IncidentChatResponse, IncidentDetailChatRequest
from services.incident_chat import IncidentChatService

router = APIRouter(prefix="/incidents", tags=["incident-chat"])


def get_incident_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> IncidentRepository:
    return IncidentRepository(manager.pool)


def get_incident_chat_service(
    repository: IncidentRepository = Depends(get_incident_repository),
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
        model=get_openai_model(),
    )


@router.post("/chat", response_model=IncidentChatResponse, status_code=status.HTTP_200_OK)
async def chat_about_incidents(
    payload: GlobalIncidentChatRequest,
    service: IncidentChatService = Depends(get_incident_chat_service),
) -> IncidentChatResponse:
    return await service.chat_about_incidents(payload)


@router.post("/{incident_id}/chat", response_model=IncidentChatResponse, status_code=status.HTTP_200_OK)
async def chat_about_incident(
    incident_id: str,
    payload: IncidentDetailChatRequest,
    service: IncidentChatService = Depends(get_incident_chat_service),
) -> IncidentChatResponse:
    return await service.chat_about_incident(incident_id, payload)
