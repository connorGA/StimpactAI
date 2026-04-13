from __future__ import annotations

from datetime import UTC, datetime
import logging

from fastapi import APIRouter, Depends, Request, status

from api.core.security import (
    authorize_telemetry_ingest_payload,
    enforce_browser_token_issue_rate_limit,
    enforce_telemetry_payload_rate_limit,
    enforce_telemetry_rate_limit,
    issue_browser_ingest_token_for_request,
    require_telemetry_ingest_access,
)
from api.db.postgres import PostgresConnectionManager, get_postgres_manager
from api.events.publisher import IncidentEventPublisher, get_incident_event_publisher
from api.events.outbox_signaler import OutboxSignaler
from api.repositories.control_plane_repository import ControlPlaneRepository
from api.repositories.telemetry_repository import PostgresTelemetryRepository
from api.schemas.telemetry import (
    BrowserTelemetryTokenIssueRequest,
    BrowserTelemetryTokenIssueResponse,
    TelemetryAcceptedResponse,
    TelemetryErrorRequest,
    TelemetryHeartbeatAcceptedResponse,
    TelemetryHeartbeatRequest,
)
from models.normalized_telemetry import NormalizedTelemetry

router = APIRouter(prefix="/telemetry", tags=["telemetry"])
logger = logging.getLogger(__name__)


def get_telemetry_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> PostgresTelemetryRepository:
    return PostgresTelemetryRepository(manager.pool)


def get_control_plane_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> ControlPlaneRepository:
    return ControlPlaneRepository(manager.pool)


def get_outbox_signaler(request: Request) -> OutboxSignaler:
    return request.app.state.outbox_signaler


@router.post(
    "/browser-token",
    response_model=BrowserTelemetryTokenIssueResponse,
    status_code=status.HTTP_200_OK,
)
async def issue_browser_token(
    request: Request,
    payload: BrowserTelemetryTokenIssueRequest,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> BrowserTelemetryTokenIssueResponse:
    await enforce_browser_token_issue_rate_limit(request, payload.project_id)
    issued = await issue_browser_ingest_token_for_request(
        request,
        project_id=payload.project_id,
        browser_key=payload.browser_key,
        service=payload.service,
        environment=payload.environment,
        repository=repository,
    )
    return BrowserTelemetryTokenIssueResponse(
        token=issued.token,
        expires_at=datetime.fromtimestamp(issued.expires_at, tz=UTC),
        expires_in_seconds=issued.expires_in_seconds,
    )


@router.post("/error", response_model=TelemetryAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_error(
    payload: TelemetryErrorRequest,
    repository: PostgresTelemetryRepository = Depends(get_telemetry_repository),
    publisher: IncidentEventPublisher = Depends(get_incident_event_publisher),
    outbox_signaler: OutboxSignaler = Depends(get_outbox_signaler),
    _auth: None = Depends(require_telemetry_ingest_access),
    _rate_limit: None = Depends(enforce_telemetry_rate_limit),
) -> TelemetryAcceptedResponse:
    telemetry = NormalizedTelemetry.from_validated_request(
        project_id=payload.project_id,
        environment=payload.environment,
        service=payload.service,
        error_message=payload.error_message,
        stacktrace=payload.stacktrace,
        request=payload.request,
        response=payload.response,
        commit_sha=payload.commit_sha,
        timestamp=payload.timestamp,
    )
    incident_event = publisher.build_telemetry_received(telemetry)

    outbox_event_id = await repository.insert_event_with_outbox(telemetry, incident_event)
    await outbox_signaler.signal(
        event_id=outbox_event_id,
        event_type=incident_event.event_type.value,
    )
    logger.info(
        "telemetry_error_accepted telemetry_id=%s fingerprint=%s project_id=%s service=%s environment=%s outbox_event_id=%s",
        telemetry.id,
        telemetry.fingerprint,
        telemetry.project_id,
        telemetry.service,
        telemetry.environment.value,
        outbox_event_id,
    )

    return TelemetryAcceptedResponse(
        telemetry_id=telemetry.id,
        fingerprint=telemetry.fingerprint,
    )


@router.post("/heartbeat", response_model=TelemetryHeartbeatAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_heartbeat(
    request: Request,
    payload: TelemetryHeartbeatRequest,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> TelemetryHeartbeatAcceptedResponse:
    await authorize_telemetry_ingest_payload(request, payload, repository)
    await enforce_telemetry_payload_rate_limit(request, payload)
    heartbeat = await repository.upsert_project_telemetry_heartbeat(
        project_id=payload.project_id,
        service=payload.service,
        environment=payload.environment.value,
        last_seen_at=payload.timestamp,
        commit_sha=payload.commit_sha,
    )
    return TelemetryHeartbeatAcceptedResponse(
        project_id=heartbeat.project_id,
        service=heartbeat.service,
        environment=heartbeat.environment.value,
        last_seen_at=heartbeat.last_seen_at,
    )
