from __future__ import annotations

from datetime import UTC, datetime
import json
import logging

import asyncpg
from fastapi import APIRouter, Depends, Request, status

from api.core.config import get_process_outbox_inline
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
from api.repositories.artifact_repository import ArtifactRepository
from api.repositories.release_sourcemap_repository import ReleaseSourcemapRepository
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
from services.artifact_storage import S3ArtifactStorage
from services.stacktrace_symbolication import StacktraceSymbolicationService

router = APIRouter(prefix="/telemetry", tags=["telemetry"])
logger = logging.getLogger(__name__)


async def _process_telemetry_outbox_inline(
    *,
    pool: asyncpg.Pool,
    outbox_event_id: str,
    incident_payload: dict[str, object],
) -> None:
    from openai import AsyncOpenAI

    from api.core.config import (
        get_openai_api_key,
        get_telemetry_classifier_enabled,
        get_telemetry_classifier_frequency_threshold,
        get_telemetry_classifier_model,
        get_telemetry_classifier_window_minutes,
    )
    from api.repositories.control_plane_repository import ControlPlaneRepository
    from api.repositories.async_job_repository import AsyncJobRepository
    from api.repositories.autonomous_repository import AutonomousRunRepository
    from api.repositories.fingerprint_classification_repository import (
        FingerprintClassificationRepository,
    )
    from api.repositories.incident_repository import IncidentRepository
    from api.repositories.outbox_repository import OutboxRepository
    from api.repositories.patch_repository import PatchRepository
    from api.repositories.telemetry_repository import PostgresTelemetryRepository
    from services.autonomous_runs import AutonomousRunService
    from services.autonomous_trigger import trigger_autonomous_run_for_new_incident
    from services.incident_creation import IncidentCreationService
    from services.provider_integration_service import ProviderIntegrationService
    from services.aws_secrets_manager import AwsSecretsManagerReader, AwsSecretsManagerWriter
    from services.telemetry_classifier import TelemetryClassifier

    incident_repository = IncidentRepository(pool)
    control_plane_repository = ControlPlaneRepository(pool)
    telemetry_repository = PostgresTelemetryRepository(pool)
    classifier: TelemetryClassifier | None = None
    if get_telemetry_classifier_enabled():
        openai_key = get_openai_api_key()
        classifier = TelemetryClassifier(
            fingerprint_repository=FingerprintClassificationRepository(pool),
            telemetry_repository=telemetry_repository,
            openai_client=AsyncOpenAI(api_key=openai_key) if openai_key else None,
            openai_model=get_telemetry_classifier_model() if openai_key else None,
            frequency_window_minutes=get_telemetry_classifier_window_minutes(),
            frequency_threshold=get_telemetry_classifier_frequency_threshold(),
        )
    creation = IncidentCreationService(
        incident_repository,
        control_plane_repository=control_plane_repository,
        classifier=classifier,
        telemetry_repository=telemetry_repository,
    )
    result = await creation.process_telemetry_received(incident_payload)
    # region agent log
    with open("/Users/connor/Desktop/StimpactAi/.cursor/debug-31f43d.log", "a", encoding="utf-8") as debug_log:
        debug_log.write(json.dumps({"sessionId": "31f43d", "runId": result.incident_id or "suppressed", "hypothesisId": "H6", "location": "agent-platform/api/routes/telemetry.py:90", "message": "inline telemetry evaluated for autonomous trigger", "data": {"outboxEventId": outbox_event_id, "incidentId": result.incident_id, "createdNewIncident": result.created_new_incident, "attachedTelemetry": result.attached_telemetry, "suppressed": result.suppressed}, "timestamp": int(datetime.now(UTC).timestamp() * 1000)}) + "\n")
    # endregion
    if result.attached_telemetry and result.incident_id is not None:
        autonomous_service = AutonomousRunService(
            incident_repository,
            async_job_repository=AsyncJobRepository(pool),
            autonomous_repository=AutonomousRunRepository(pool),
            control_plane_repository=control_plane_repository,
            patch_repository=PatchRepository(pool),
            provider_integration_service=ProviderIntegrationService(
                control_plane_repository,
                secrets_writer=AwsSecretsManagerWriter(),
                secrets_reader=AwsSecretsManagerReader(),
            ),
        )
        await trigger_autonomous_run_for_new_incident(
            incident_id=result.incident_id,
            autonomous_run_service=autonomous_service,
            processing_result=result,
        )
    outbox = OutboxRepository(pool)
    await outbox.mark_processed(outbox_event_id)


def get_telemetry_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> PostgresTelemetryRepository:
    return PostgresTelemetryRepository(manager.pool)


def get_control_plane_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> ControlPlaneRepository:
    return ControlPlaneRepository(manager.pool)


def get_stacktrace_symbolication_service(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> StacktraceSymbolicationService:
    return StacktraceSymbolicationService(
        sourcemap_repository=ReleaseSourcemapRepository(manager.pool),
        artifact_repository=ArtifactRepository(manager.pool),
        artifact_storage=S3ArtifactStorage(),
    )


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
    request: Request,
    payload: TelemetryErrorRequest,
    repository: PostgresTelemetryRepository = Depends(get_telemetry_repository),
    publisher: IncidentEventPublisher = Depends(get_incident_event_publisher),
    outbox_signaler: OutboxSignaler = Depends(get_outbox_signaler),
    symbolication_service: StacktraceSymbolicationService = Depends(get_stacktrace_symbolication_service),
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
        release=payload.release,
        dist=payload.dist,
        session_id=payload.session_id,
        user=payload.user,
        tags=payload.tags,
        contexts=payload.contexts,
        breadcrumbs=payload.breadcrumbs,
        timestamp=payload.timestamp,
        handled=payload.handled,
    )
    if telemetry.release:
        symbolicated_stacktrace = await symbolication_service.symbolicate(
            project_id=telemetry.project_id,
            release=telemetry.release,
            dist=telemetry.dist,
            stacktrace=telemetry.stacktrace,
        )
        if symbolicated_stacktrace:
            telemetry.stacktrace = symbolicated_stacktrace
    incident_event = publisher.build_telemetry_received(telemetry)

    outbox_event_id = await repository.insert_event_with_outbox(telemetry, incident_event)
    await outbox_signaler.signal(
        event_id=outbox_event_id,
        event_type=incident_event.event_type.value,
    )

    if get_process_outbox_inline():
        postgres = getattr(request.app.state, "postgres", None)
        pool = postgres.pool if postgres is not None else None
        if pool is not None:
            try:
                await _process_telemetry_outbox_inline(
                    pool=pool,
                    outbox_event_id=outbox_event_id,
                    incident_payload=incident_event.model_dump(mode="json"),
                )
                logger.info(
                    "telemetry_outbox_processed_inline telemetry_id=%s outbox_event_id=%s",
                    telemetry.id,
                    outbox_event_id,
                )
            except Exception:
                logger.exception(
                    "telemetry_outbox_inline_failed telemetry_id=%s outbox_event_id=%s",
                    telemetry.id,
                    outbox_event_id,
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
