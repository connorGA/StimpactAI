from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from api.db.postgres import PostgresConnectionManager, get_postgres_manager
from api.events.publisher import IncidentEventPublisher, get_incident_event_publisher
from api.events.outbox_signaler import OutboxSignaler
from api.repositories.telemetry_repository import PostgresTelemetryRepository
from api.schemas.telemetry import TelemetryAcceptedResponse, TelemetryErrorRequest
from models.normalized_telemetry import NormalizedTelemetry

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


def get_telemetry_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> PostgresTelemetryRepository:
    return PostgresTelemetryRepository(manager.pool)


def get_outbox_signaler(request: Request) -> OutboxSignaler:
    return request.app.state.outbox_signaler


@router.post("/error", response_model=TelemetryAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_error(
    payload: TelemetryErrorRequest,
    repository: PostgresTelemetryRepository = Depends(get_telemetry_repository),
    publisher: IncidentEventPublisher = Depends(get_incident_event_publisher),
    outbox_signaler: OutboxSignaler = Depends(get_outbox_signaler),
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

    return TelemetryAcceptedResponse(
        telemetry_id=telemetry.id,
        fingerprint=telemetry.fingerprint,
    )
