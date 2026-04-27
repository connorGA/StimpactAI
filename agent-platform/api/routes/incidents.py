from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI

from api.core.config import (
    get_openai_api_key,
    get_openai_failure_classify_model,
    get_openai_patch_model,
    get_openai_rca_model,
)
from api.core.errors import APIError
from api.core.security import require_project_list_access, require_project_read_access
from api.db.postgres import PostgresConnectionManager, get_postgres_manager
from api.repositories.artifact_repository import ArtifactRepository
from api.repositories.async_job_repository import AsyncJobRepository
from api.repositories.autonomous_repository import AutonomousRunRepository
from api.repositories.control_plane_repository import ControlPlaneRepository
from api.repositories.fingerprint_classification_repository import (
    FingerprintClassificationRepository,
)
from api.repositories.incident_repository import IncidentRepository
from api.repositories.patch_repository import PatchRepository
from api.repositories.sandbox_repository import SandboxRepository
from api.repositories.telemetry_repository import PostgresTelemetryRepository
from api.routes.control_plane import get_provider_integration_service
from api.schemas.autonomous import (
    AutonomousRunApprovalRequest,
    AutonomousRunCreateRequest,
    AutonomousRunDetailResponse,
    AutonomousRunQueuedResponse,
)
from api.schemas.incidents import (
    ArtifactResponse,
    IncidentClassificationResponse,
    IncidentCountBreakdownResponse,
    IncidentDetailResponse,
    IncidentEventResponse,
    IncidentPatchResponse,
    IncidentReportingOverviewResponse,
    IncidentRootCauseResponse,
    IncidentActivityPointResponse,
    IncidentSandboxRunDetailResponse,
    IncidentSandboxRunResponse,
    IncidentListResponse,
    EscalateNoiseFingerprintRequest,
    EscalateNoiseFingerprintResponse,
    ReclassifyFingerprintRequest,
    ReclassifyFingerprintResponse,
    SandboxRunAttemptResponse,
    SandboxRunQueuedResponse,
    SandboxRunStepResponse,
    IncidentSummaryResponse,
    SuppressedFingerprintListResponse,
    SuppressedFingerprintResponse,
    SuppressionSummaryResponse,
)
from harness.schemas.autonomous import AutonomousRepairRunRecord, AutonomousRunStatus
from models.incident import IncidentStatus
from models.sandbox import SandboxRunStatus
from services.autonomous_runs import AutonomousRunService
from services.autonomous_trigger import trigger_autonomous_run_for_new_incident
from services.incident_creation import IncidentCreationService
from services.code_context import CodeContextService
from services.failure_classifier import FailureClassifier
from services.patch_generation import PatchGenerationService
from services.provider_integration_service import ProviderIntegrationService
from services.root_cause_analysis import (
    RootCauseAnalysisService,
    RootCauseAnalyzer,
    RootCauseReasoner,
)
from services.sandbox_verification import SandboxVerificationService
from shared.events.incident_events import IncidentEvent

router = APIRouter(prefix="/incidents", tags=["incidents"])


def get_incident_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> IncidentRepository:
    return IncidentRepository(manager.pool)


def get_patch_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> PatchRepository:
    return PatchRepository(manager.pool)


def get_sandbox_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> SandboxRepository:
    return SandboxRepository(manager.pool)


def get_control_plane_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> ControlPlaneRepository:
    return ControlPlaneRepository(manager.pool)


def get_async_job_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> AsyncJobRepository:
    return AsyncJobRepository(manager.pool)


def get_artifact_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> ArtifactRepository:
    return ArtifactRepository(manager.pool)


def get_autonomous_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> AutonomousRunRepository:
    return AutonomousRunRepository(manager.pool)


def get_telemetry_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> PostgresTelemetryRepository:
    return PostgresTelemetryRepository(manager.pool)


def get_fingerprint_classification_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> FingerprintClassificationRepository:
    return FingerprintClassificationRepository(manager.pool)


def get_failure_classifier() -> FailureClassifier:
    api_key = get_openai_api_key()
    if api_key is None:
        return FailureClassifier()
    return FailureClassifier(
        openai_client=AsyncOpenAI(api_key=api_key),
        model=get_openai_failure_classify_model(),
    )


def get_code_context_service() -> CodeContextService:
    return CodeContextService()


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


def get_patch_generation_service(
    incident_repository: IncidentRepository = Depends(get_incident_repository),
    patch_repository: PatchRepository = Depends(get_patch_repository),
    classifier: FailureClassifier = Depends(get_failure_classifier),
    code_context: CodeContextService = Depends(get_code_context_service),
) -> PatchGenerationService:
    api_key = get_openai_api_key()
    if api_key is None:
        raise APIError(
            "OPENAI_API_KEY is not configured for patch generation.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="openai_unconfigured",
        )

    return PatchGenerationService(
        incident_repository,
        patch_repository,
        classifier=classifier,
        code_context=code_context,
        client=AsyncOpenAI(api_key=api_key),
        model=get_openai_patch_model(),
    )


def get_sandbox_verification_service(
    incident_repository: IncidentRepository = Depends(get_incident_repository),
    sandbox_repository: SandboxRepository = Depends(get_sandbox_repository),
    control_plane_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    async_job_repository: AsyncJobRepository = Depends(get_async_job_repository),
    artifact_repository: ArtifactRepository = Depends(get_artifact_repository),
    patch_repository: PatchRepository = Depends(get_patch_repository),
    patch_generation: PatchGenerationService = Depends(get_patch_generation_service),
) -> SandboxVerificationService:
    return SandboxVerificationService(
        incident_repository,
        sandbox_repository,
        control_plane_repository=control_plane_repository,
        async_job_repository=async_job_repository,
        artifact_repository=artifact_repository,
        patch_repository=patch_repository,
        patch_generation=patch_generation,
    )


def get_autonomous_run_service(
    request: Request,
    incident_repository: IncidentRepository = Depends(get_incident_repository),
    async_job_repository: AsyncJobRepository = Depends(get_async_job_repository),
    control_plane_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    autonomous_repository: AutonomousRunRepository = Depends(get_autonomous_repository),
    patch_repository: PatchRepository = Depends(get_patch_repository),
    sandbox_verification_service: SandboxVerificationService = Depends(get_sandbox_verification_service),
    provider_integration_service: ProviderIntegrationService = Depends(get_provider_integration_service),
) -> AutonomousRunService:
    existing = getattr(request.app.state, "autonomous_run_service", None)
    if isinstance(existing, AutonomousRunService):
        return existing
    service = AutonomousRunService(
        incident_repository,
        async_job_repository=async_job_repository,
        autonomous_repository=autonomous_repository,
        control_plane_repository=control_plane_repository,
        patch_repository=patch_repository,
        sandbox_verification_service=sandbox_verification_service,
        provider_integration_service=provider_integration_service,
    )
    request.app.state.autonomous_run_service = service
    return service


async def _require_incident_access(
    *,
    request: Request,
    incident_id: str,
    incident_repository: IncidentRepository,
    security_repository: ControlPlaneRepository,
):
    incident = await incident_repository.get_incident(incident_id)
    if incident is None:
        raise APIError(
            f"Incident {incident_id} was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="incident_not_found",
        )
    await require_project_read_access(request, incident.project_id, repository=security_repository)
    return incident


@router.get("", response_model=IncidentListResponse, status_code=status.HTTP_200_OK)
async def list_incidents(
    request: Request,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    project_id: str | None = Query(default=None, min_length=1, max_length=128),
    status_filter: Annotated[IncidentStatus | None, Query(alias="status")] = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> IncidentListResponse:
    await require_project_list_access(request, project_id, repository=security_repository)
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


@router.patch(
    "/{incident_id}/acknowledge",
    response_model=IncidentSummaryResponse,
    status_code=status.HTTP_200_OK,
)
async def acknowledge_incident(
    request: Request,
    incident_id: str,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> IncidentSummaryResponse:
    await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    updated = await repository.update_incident_status(
        incident_id,
        IncidentStatus.ACKNOWLEDGED,
    )
    return IncidentSummaryResponse.from_record(updated)


@router.patch(
    "/{incident_id}/resolve",
    response_model=IncidentSummaryResponse,
    status_code=status.HTTP_200_OK,
)
async def resolve_incident(
    request: Request,
    incident_id: str,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> IncidentSummaryResponse:
    await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    updated = await repository.update_incident_status(incident_id, IncidentStatus.RESOLVED)
    return IncidentSummaryResponse.from_record(updated)


@router.patch(
    "/{incident_id}/reopen",
    response_model=IncidentSummaryResponse,
    status_code=status.HTTP_200_OK,
)
async def reopen_incident(
    request: Request,
    incident_id: str,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> IncidentSummaryResponse:
    await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    updated = await repository.update_incident_status(incident_id, IncidentStatus.OPEN)
    return IncidentSummaryResponse.from_record(updated)


@router.get(
    "/noise",
    response_model=SuppressedFingerprintListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_suppressed_telemetry(
    request: Request,
    project_id: str = Query(min_length=1, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
    telemetry_repository: PostgresTelemetryRepository = Depends(get_telemetry_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> SuppressedFingerprintListResponse:
    await require_project_read_access(request, project_id, repository=security_repository)
    rows = await telemetry_repository.list_suppressed(
        project_id=project_id,
        limit=limit,
    )
    items = [
        SuppressedFingerprintResponse(
            project_id=str(row["project_id"]),
            fingerprint=str(row["fingerprint"]),
            classification=str(row["classification"]),
            classification_reason=(
                str(row["classification_reason"]) if row.get("classification_reason") else None
            ),
            classification_source=(
                str(row["classification_source"]) if row.get("classification_source") else None
            ),
            service=str(row["service"]),
            error_message=str(row["error_message"]),
            first_occurred_at=row["first_occurred_at"],
            last_occurred_at=row["last_occurred_at"],
            occurrence_count=int(row["occurrence_count"]),
            last_classified_at=row.get("last_classified_at"),
        )
        for row in rows
    ]
    return SuppressedFingerprintListResponse(items=items)


@router.get(
    "/noise/summary",
    response_model=SuppressionSummaryResponse,
    status_code=status.HTTP_200_OK,
)
async def get_suppression_summary(
    request: Request,
    project_id: str = Query(min_length=1, max_length=128),
    window_minutes: int = Query(default=60 * 24, ge=1, le=60 * 24 * 30),
    telemetry_repository: PostgresTelemetryRepository = Depends(get_telemetry_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> SuppressionSummaryResponse:
    await require_project_read_access(request, project_id, repository=security_repository)
    since = datetime.now(UTC) - timedelta(minutes=window_minutes)
    summary = await telemetry_repository.suppression_summary(
        project_id=project_id,
        since=since,
    )
    user_error = summary.get("user_error", {"event_count": 0, "unique_fingerprints": 0})
    ambiguous = summary.get("code_ambiguous", {"event_count": 0, "unique_fingerprints": 0})
    return SuppressionSummaryResponse(
        project_id=project_id,
        window_minutes=window_minutes,
        user_error_event_count=int(user_error.get("event_count", 0)),
        user_error_unique_fingerprints=int(user_error.get("unique_fingerprints", 0)),
        code_ambiguous_event_count=int(ambiguous.get("event_count", 0)),
        code_ambiguous_unique_fingerprints=int(ambiguous.get("unique_fingerprints", 0)),
    )


@router.post(
    "/noise/{fingerprint}/reclassify",
    response_model=ReclassifyFingerprintResponse,
    status_code=status.HTTP_200_OK,
)
async def reclassify_fingerprint(
    request: Request,
    fingerprint: str,
    payload: ReclassifyFingerprintRequest,
    fingerprint_repository: FingerprintClassificationRepository = Depends(
        get_fingerprint_classification_repository
    ),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ReclassifyFingerprintResponse:
    """Persist a manual classification override for this fingerprint.

    The classifier consults this table on future telemetry; it does **not** enqueue
    an autonomous repair by itself. Treat-as-bug removes the fingerprint from the
    suppressed-telemetry list (noise UI) and causes matching future events to be
    classified as ``code_bug``, which can then open incidents per normal ingest rules.
    """

    await require_project_read_access(
        request,
        payload.project_id,
        repository=security_repository,
    )
    allowed = {"code_bug", "user_error", "code_ambiguous"}
    classification = payload.classification.strip().lower()
    if classification not in allowed:
        raise APIError(
            f"Unsupported classification '{payload.classification}'. Expected one of {sorted(allowed)}.",
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_classification",
        )
    await fingerprint_repository.put(
        project_id=payload.project_id,
        fingerprint=fingerprint,
        classification=classification,
        reason=payload.reason,
        source="manual",
    )
    return ReclassifyFingerprintResponse(
        project_id=payload.project_id,
        fingerprint=fingerprint,
        classification=classification,
        reason=payload.reason,
    )


@router.post(
    "/noise/{fingerprint}/escalate",
    response_model=EscalateNoiseFingerprintResponse,
    status_code=status.HTTP_200_OK,
)
async def escalate_noise_fingerprint(
    request: Request,
    fingerprint: str,
    payload: EscalateNoiseFingerprintRequest,
    fingerprint_repository: FingerprintClassificationRepository = Depends(
        get_fingerprint_classification_repository
    ),
    incident_repository: IncidentRepository = Depends(get_incident_repository),
    telemetry_repository: PostgresTelemetryRepository = Depends(get_telemetry_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    autonomous_run_service: AutonomousRunService = Depends(get_autonomous_run_service),
) -> EscalateNoiseFingerprintResponse:
    """Treat fingerprint as ``code_bug``, open or refresh an incident from latest telemetry, queue repair."""

    await require_project_read_access(
        request,
        payload.project_id,
        repository=security_repository,
    )
    await fingerprint_repository.put(
        project_id=payload.project_id,
        fingerprint=fingerprint,
        classification="code_bug",
        reason=payload.reason,
        source="manual",
    )
    telemetry_id = await telemetry_repository.get_latest_telemetry_id_for_fingerprint(
        project_id=payload.project_id,
        fingerprint=fingerprint,
    )
    if telemetry_id is None:
        raise APIError(
            "No telemetry events exist for this fingerprint in the project.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="telemetry_not_found",
        )
    telemetry = await incident_repository.get_telemetry(telemetry_id)
    event = IncidentEvent(
        telemetry_id=telemetry.id,
        project_id=telemetry.project_id,
        fingerprint=telemetry.fingerprint,
        occurred_at=telemetry.occurred_at,
        payload={
            "environment": telemetry.environment.value,
            "service": telemetry.service,
            "error_message": telemetry.error_message,
            "occurred_at": telemetry.occurred_at.isoformat(),
        },
    )
    creation = IncidentCreationService(
        incident_repository,
        control_plane_repository=security_repository,
        classifier=None,
        telemetry_repository=None,
    )
    result = await creation.process_telemetry_received(event.model_dump(mode="json"))
    if result.suppressed or result.incident_id is None:
        raise APIError(
            "Could not open an incident for this fingerprint after reclassification.",
            status_code=status.HTTP_409_CONFLICT,
            code="noise_escalate_failed",
        )
    incident_id = result.incident_id
    runs_before = {run.id for run in await autonomous_run_service.list_runs(incident_id)}
    await trigger_autonomous_run_for_new_incident(
        incident_id=incident_id,
        autonomous_run_service=autonomous_run_service,
        processing_result=result,
    )
    runs_after = await autonomous_run_service.list_runs(incident_id)
    new_runs = [run for run in runs_after if run.id not in runs_before]
    new_run = new_runs[0] if new_runs else None
    trigger_skipped = new_run is None and bool(runs_after)
    return EscalateNoiseFingerprintResponse(
        project_id=payload.project_id,
        fingerprint=fingerprint,
        incident_id=incident_id,
        telemetry_id=telemetry_id,
        created_new_incident=result.created_new_incident,
        attached_telemetry=result.attached_telemetry,
        autonomous_run_id=new_run.id if new_run is not None else None,
        async_job_id=new_run.async_job_id if new_run is not None else None,
        autonomous_trigger_skipped=trigger_skipped,
    )


@router.get(
    "/reporting/overview",
    response_model=IncidentReportingOverviewResponse,
    status_code=status.HTTP_200_OK,
)
async def get_incident_reporting_overview(
    request: Request,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    project_id: str | None = Query(default=None, min_length=1, max_length=128),
) -> IncidentReportingOverviewResponse:
    await require_project_list_access(request, project_id, repository=security_repository)
    incidents, _total = await repository.list_incidents(
        project_id=project_id,
        status=None,
        limit=500,
        offset=0,
    )
    uptime_pct = 100.0
    uptime_delta_pp = 0.0
    avg_sec: float | None = None
    avg_delta_sec: float | None = None
    agent_pct: float | None = None
    agent_delta_pp: float | None = None
    open_n = sum(1 for incident in incidents if incident.status == IncidentStatus.OPEN)
    if project_id:
        live = await repository.fetch_live_operations_metrics(project_id)
        uptime_pct = live.uptime_percent_last_30d
        uptime_delta_pp = live.uptime_percent_last_30d - live.uptime_percent_prior_30d
        avg_sec = live.avg_agent_response_seconds_last_30d
        if (
            live.avg_agent_response_seconds_last_30d is not None
            and live.avg_agent_response_seconds_prior_30d is not None
        ):
            avg_delta_sec = (
                live.avg_agent_response_seconds_last_30d
                - live.avg_agent_response_seconds_prior_30d
            )
        agent_pct = live.agent_resolution_percent_last_30d
        if (
            live.agent_resolution_percent_last_30d is not None
            and live.agent_resolution_percent_prior_30d is not None
        ):
            agent_delta_pp = (
                live.agent_resolution_percent_last_30d
                - live.agent_resolution_percent_prior_30d
            )
        open_n = live.open_incidents
    return IncidentReportingOverviewResponse(
        project_id=project_id,
        total_visible_incidents=len(incidents),
        open_incidents=open_n,
        critical_incidents=sum(1 for incident in incidents if incident.severity.value == "critical"),
        total_event_volume=sum(incident.event_count for incident in incidents),
        latest_incident_at=max((incident.last_seen_at for incident in incidents), default=None),
        service_counts=_build_count_breakdown(incident.service for incident in incidents),
        environment_counts=_build_count_breakdown(incident.environment.value for incident in incidents),
        severity_counts=_build_count_breakdown(
            (incident.severity.value for incident in incidents),
            preferred_order=["critical", "high", "medium", "low"],
        ),
        recent_incident_activity=_build_recent_activity(incidents),
        daily_incident_activity=_build_daily_activity(incidents),
        uptime_percent_last_30d=uptime_pct,
        uptime_delta_pp=uptime_delta_pp,
        avg_agent_response_seconds_last_30d=avg_sec,
        avg_agent_response_delta_seconds=avg_delta_sec,
        agent_resolution_percent_last_30d=agent_pct,
        agent_resolution_delta_pp=agent_delta_pp,
    )


async def _stream_incident_live_updates_impl(
    request: Request,
    project_id: str = Query(min_length=1, max_length=128),
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    autonomous_service: AutonomousRunService = Depends(get_autonomous_run_service),
) -> StreamingResponse:
    return await _stream_incident_live_updates_impl(
        request=request,
        project_id=project_id,
        repository=repository,
        security_repository=security_repository,
        autonomous_service=autonomous_service,
    )


@router.get("/{incident_id}", response_model=IncidentDetailResponse, status_code=status.HTTP_200_OK)
async def get_incident(
    request: Request,
    incident_id: str,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    event_limit: int = Query(default=100, ge=1, le=500),
) -> IncidentDetailResponse:
    incident = await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
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
    request: Request,
    incident_id: str,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    classifier: FailureClassifier = Depends(get_failure_classifier),
    event_limit: int = Query(default=50, ge=1, le=200),
) -> IncidentClassificationResponse:
    incident = await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    events = await repository.list_incident_events(incident_id, limit=event_limit)
    classification = await classifier.classify_async(incident, events)
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
    request: Request,
    incident_id: str,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: RootCauseAnalysisService = Depends(get_root_cause_analysis_service),
    event_limit: int = Query(default=50, ge=1, le=200),
) -> IncidentRootCauseResponse:
    await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    analysis = await service.analyze_incident(incident_id, event_limit=event_limit)
    return IncidentRootCauseResponse.from_analysis(analysis)


@router.get(
    "/{incident_id}/patch",
    response_model=IncidentPatchResponse,
    status_code=status.HTTP_200_OK,
)
async def get_or_generate_patch(
    request: Request,
    incident_id: str,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: PatchGenerationService = Depends(get_patch_generation_service),
    event_limit: int = Query(default=50, ge=1, le=200),
    refresh: bool = Query(default=False),
) -> IncidentPatchResponse:
    await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    patch_run = await service.get_or_generate_patch(
        incident_id,
        refresh=refresh,
        event_limit=event_limit,
    )
    return IncidentPatchResponse.from_record(patch_run)


@router.get(
    "/{incident_id}/sandbox-run",
    response_model=IncidentSandboxRunResponse,
    status_code=status.HTTP_200_OK,
)
async def get_latest_sandbox_run(
    request: Request,
    incident_id: str,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: SandboxVerificationService = Depends(get_sandbox_verification_service),
) -> IncidentSandboxRunResponse:
    await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    run = await service.get_latest_run(incident_id)
    if run is None:
        raise APIError(
            f"No sandbox run has been recorded yet for incident {incident_id}.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="sandbox_run_not_found",
        )
    return IncidentSandboxRunResponse.from_record(run)


@router.post(
    "/{incident_id}/sandbox-run",
    response_model=SandboxRunQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def execute_sandbox_run(
    request: Request,
    incident_id: str,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: SandboxVerificationService = Depends(get_sandbox_verification_service),
    event_limit: int = Query(default=50, ge=1, le=200),
    refresh_patch: bool = Query(default=False),
) -> SandboxRunQueuedResponse:
    await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    run, job = await service.queue_sandbox_run(
        incident_id,
        event_limit=event_limit,
        refresh_patch=refresh_patch,
    )
    return SandboxRunQueuedResponse(
        sandbox_run=IncidentSandboxRunResponse.from_record(run),
        async_job_id=job.id,
        async_job_status=job.status,
    )


@router.get(
    "/{incident_id}/sandbox-runs",
    response_model=list[IncidentSandboxRunResponse],
    status_code=status.HTTP_200_OK,
)
async def list_sandbox_runs(
    request: Request,
    incident_id: str,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: SandboxVerificationService = Depends(get_sandbox_verification_service),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[IncidentSandboxRunResponse]:
    await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    runs = await service.list_runs(incident_id, limit=limit)
    return [IncidentSandboxRunResponse.from_record(run) for run in runs]


@router.get(
    "/{incident_id}/sandbox-runs/{sandbox_run_id}",
    response_model=IncidentSandboxRunDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def get_sandbox_run_detail(
    request: Request,
    incident_id: str,
    sandbox_run_id: str,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: SandboxVerificationService = Depends(get_sandbox_verification_service),
    sandbox_repository: SandboxRepository = Depends(get_sandbox_repository),
    artifact_repository: ArtifactRepository = Depends(get_artifact_repository),
) -> IncidentSandboxRunDetailResponse:
    await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    run = await service.get_run(incident_id, sandbox_run_id)
    steps = await sandbox_repository.list_sandbox_run_steps(sandbox_run_id)
    attempts = await sandbox_repository.list_sandbox_run_attempts(sandbox_run_id)
    artifacts = await artifact_repository.list_sandbox_run_artifacts(sandbox_run_id)
    return IncidentSandboxRunDetailResponse(
        run=IncidentSandboxRunResponse.from_record(run),
        steps=[SandboxRunStepResponse.from_record(step) for step in steps],
        attempts=[SandboxRunAttemptResponse.from_record(attempt) for attempt in attempts],
        artifacts=[ArtifactResponse.from_record(artifact) for artifact in artifacts],
    )


async def _load_sandbox_run_detail_response(
    *,
    incident_id: str,
    sandbox_run_id: str,
    service: SandboxVerificationService,
    sandbox_repository: SandboxRepository,
    artifact_repository: ArtifactRepository,
) -> IncidentSandboxRunDetailResponse:
    run = await service.get_run(incident_id, sandbox_run_id)
    steps = await sandbox_repository.list_sandbox_run_steps(sandbox_run_id)
    attempts = await sandbox_repository.list_sandbox_run_attempts(sandbox_run_id)
    artifacts = await artifact_repository.list_sandbox_run_artifacts(sandbox_run_id)
    return IncidentSandboxRunDetailResponse(
        run=IncidentSandboxRunResponse.from_record(run),
        steps=[SandboxRunStepResponse.from_record(step) for step in steps],
        attempts=[SandboxRunAttemptResponse.from_record(attempt) for attempt in attempts],
        artifacts=[ArtifactResponse.from_record(artifact) for artifact in artifacts],
    )


@router.post(
    "/{incident_id}/autonomous-runs",
    response_model=AutonomousRunQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_autonomous_run(
    request: Request,
    incident_id: str,
    body: AutonomousRunCreateRequest,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: AutonomousRunService = Depends(get_autonomous_run_service),
) -> AutonomousRunQueuedResponse:
    await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    detail = await service.start_run(incident_id, body)
    return AutonomousRunQueuedResponse(run=detail.run, async_job_id=detail.run.async_job_id)


@router.get(
    "/{incident_id}/autonomous-runs",
    response_model=list[AutonomousRepairRunRecord],
    status_code=status.HTTP_200_OK,
)
async def list_autonomous_runs(
    request: Request,
    incident_id: str,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: AutonomousRunService = Depends(get_autonomous_run_service),
) -> list[AutonomousRepairRunRecord]:
    await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    return await service.list_runs(incident_id)


@router.get(
    "/{incident_id}/autonomous-runs/latest",
    response_model=AutonomousRunDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def get_latest_autonomous_run(
    request: Request,
    incident_id: str,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: AutonomousRunService = Depends(get_autonomous_run_service),
) -> AutonomousRunDetailResponse:
    await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    return await service.get_latest_run_detail(incident_id)


@router.get(
    "/{incident_id}/autonomous-runs/{run_id}",
    response_model=AutonomousRunDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def get_autonomous_run_detail(
    request: Request,
    incident_id: str,
    run_id: str,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: AutonomousRunService = Depends(get_autonomous_run_service),
) -> AutonomousRunDetailResponse:
    await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    return await service.get_run_detail(incident_id, run_id)


@router.post(
    "/{incident_id}/autonomous-runs/{run_id}/approval",
    response_model=AutonomousRunDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def approve_autonomous_run(
    request: Request,
    incident_id: str,
    run_id: str,
    body: AutonomousRunApprovalRequest,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: AutonomousRunService = Depends(get_autonomous_run_service),
) -> AutonomousRunDetailResponse:
    await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    return await service.approve_run(incident_id, run_id, body)


@router.post(
    "/{incident_id}/autonomous-runs/{run_id}/promote",
    response_model=AutonomousRunDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def promote_autonomous_run(
    request: Request,
    incident_id: str,
    run_id: str,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: AutonomousRunService = Depends(get_autonomous_run_service),
) -> AutonomousRunDetailResponse:
    await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    return await service.promote_run(incident_id, run_id)


@router.get(
    "/{incident_id}/autonomous-runs/{run_id}/events",
    status_code=status.HTTP_200_OK,
)
async def stream_autonomous_run_events(
    incident_id: str,
    run_id: str,
    request: Request,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: AutonomousRunService = Depends(get_autonomous_run_service),
) -> StreamingResponse:
    await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    initial_detail = await service.get_run_detail(incident_id, run_id)

    async def event_generator():
        yield _format_sse(initial_detail.model_dump(mode="json"))
        if service.is_terminal(initial_detail.run):
            return
        last_updated_at = initial_detail.run.updated_at
        last_event_count = len(initial_detail.events)
        while True:
            if await request.is_disconnected():
                break
            await asyncio.sleep(1)
            try:
                detail = await service.get_run_detail(incident_id, run_id)
            except APIError:
                break
            if detail.run.updated_at != last_updated_at or len(detail.events) != last_event_count:
                yield _format_sse(detail.model_dump(mode="json"))
                last_updated_at = detail.run.updated_at
                last_event_count = len(detail.events)
            else:
                yield ": keep-alive\n\n"
            if service.is_terminal(detail.run):
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/{incident_id}/sandbox-runs/{sandbox_run_id}/events",
    status_code=status.HTTP_200_OK,
)
async def stream_sandbox_run_events(
    incident_id: str,
    sandbox_run_id: str,
    request: Request,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: SandboxVerificationService = Depends(get_sandbox_verification_service),
    sandbox_repository: SandboxRepository = Depends(get_sandbox_repository),
    artifact_repository: ArtifactRepository = Depends(get_artifact_repository),
) -> StreamingResponse:
    await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    initial_detail = await _load_sandbox_run_detail_response(
        incident_id=incident_id,
        sandbox_run_id=sandbox_run_id,
        service=service,
        sandbox_repository=sandbox_repository,
        artifact_repository=artifact_repository,
    )

    async def event_generator():
        yield _format_sse(initial_detail.model_dump(mode="json"))
        if initial_detail.run.status in {SandboxRunStatus.SUCCEEDED, SandboxRunStatus.FAILED}:
            return
        last_updated_at = initial_detail.run.updated_at
        last_step_count = len(initial_detail.steps)
        last_attempt_count = len(initial_detail.attempts)
        while True:
            if await request.is_disconnected():
                break
            await asyncio.sleep(1)
            try:
                detail = await _load_sandbox_run_detail_response(
                    incident_id=incident_id,
                    sandbox_run_id=sandbox_run_id,
                    service=service,
                    sandbox_repository=sandbox_repository,
                    artifact_repository=artifact_repository,
                )
            except APIError:
                break
            if (
                detail.run.updated_at != last_updated_at
                or len(detail.steps) != last_step_count
                or len(detail.attempts) != last_attempt_count
            ):
                yield _format_sse(detail.model_dump(mode="json"))
                last_updated_at = detail.run.updated_at
                last_step_count = len(detail.steps)
                last_attempt_count = len(detail.attempts)
            else:
                yield ": keep-alive\n\n"
            if detail.run.status in {SandboxRunStatus.SUCCEEDED, SandboxRunStatus.FAILED}:
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/live-stream", status_code=status.HTTP_200_OK)
async def stream_incident_live_updates(
    request: Request,
    project_id: str = Query(min_length=1, max_length=128),
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    autonomous_service: AutonomousRunService = Depends(get_autonomous_run_service),
) -> StreamingResponse:
    await require_project_list_access(request, project_id, repository=security_repository)

    async def build_snapshot() -> dict[str, object]:
        incidents, _total = await repository.list_incidents(
            project_id=project_id,
            status=None,
            limit=100,
            offset=0,
        )
        transitions: list[dict[str, object]] = []
        open_incidents = 0
        repairing_incidents = 0
        for incident in incidents:
            if incident.status is IncidentStatus.OPEN:
                open_incidents += 1
            try:
                detail = await autonomous_service.get_latest_run_detail(incident.id)
            except APIError:
                continue
            if detail.run.status in {
                AutonomousRunStatus.RUNNING,
                AutonomousRunStatus.QUEUED,
            }:
                repairing_incidents += 1
            transitions.append(
                {
                    "incident_id": incident.id,
                    "incident_title": incident.title,
                    "run_id": detail.run.id,
                    "status": detail.run.status.value,
                    "phase": detail.run.phase.value,
                    "updated_at": detail.run.updated_at.isoformat(),
                    "last_event": detail.events[-1].summary if detail.events else None,
                    "promotion_url": detail.run.promotion_url,
                }
            )
        transitions.sort(key=lambda item: str(item["updated_at"]), reverse=True)
        return {
            "project_id": project_id,
            "open_incidents": open_incidents,
            "repairing_incidents": repairing_incidents,
            "recent_transitions": transitions[:8],
        }

    initial_snapshot = await build_snapshot()

    async def event_generator():
        yield _format_sse(initial_snapshot)
        last_serialized = json.dumps(initial_snapshot, sort_keys=True)
        while True:
            if await request.is_disconnected():
                break
            await asyncio.sleep(1)
            try:
                snapshot = await build_snapshot()
            except APIError:
                break
            serialized = json.dumps(snapshot, sort_keys=True)
            if serialized != last_serialized:
                yield _format_sse(snapshot)
                last_serialized = serialized
            else:
                yield ": keep-alive\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{incident_id}/sandbox-runs",
    response_model=SandboxRunQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_sandbox_run(
    request: Request,
    incident_id: str,
    repository: IncidentRepository = Depends(get_incident_repository),
    security_repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: SandboxVerificationService = Depends(get_sandbox_verification_service),
    event_limit: int = Query(default=50, ge=1, le=200),
    refresh_patch: bool = Query(default=False),
) -> SandboxRunQueuedResponse:
    await _require_incident_access(
        request=request,
        incident_id=incident_id,
        incident_repository=repository,
        security_repository=security_repository,
    )
    run, job = await service.queue_sandbox_run(
        incident_id,
        event_limit=event_limit,
        refresh_patch=refresh_patch,
    )
    return SandboxRunQueuedResponse(
        sandbox_run=IncidentSandboxRunResponse.from_record(run),
        async_job_id=job.id,
        async_job_status=job.status,
    )


def _format_sse(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, sort_keys=True)}\n\n"


def _build_count_breakdown(
    values,
    *,
    preferred_order: list[str] | None = None,
) -> list[IncidentCountBreakdownResponse]:
    counts = Counter(values)
    if preferred_order is not None:
        return [
            IncidentCountBreakdownResponse(label=label, count=counts.get(label, 0))
            for label in preferred_order
        ]
    return [
        IncidentCountBreakdownResponse(label=label, count=count)
        for label, count in counts.most_common()
    ]


def _build_recent_activity(incidents: list) -> list[IncidentActivityPointResponse]:
    now = datetime.now(UTC)
    buckets: list[IncidentActivityPointResponse] = []
    for hour_offset in range(20, -1, -4):
        bucket_start = now - timedelta(hours=hour_offset)
        bucket_end = bucket_start + timedelta(hours=4)
        label = bucket_start.strftime("%H:%M")
        count = sum(
            1
            for incident in incidents
            if bucket_start <= incident.last_seen_at < bucket_end
        )
        buckets.append(IncidentActivityPointResponse(label=label, count=count))
    return buckets


def _build_daily_activity(incidents: list) -> list[IncidentActivityPointResponse]:
    now = datetime.now(UTC)
    buckets: list[IncidentActivityPointResponse] = []
    for day_offset in range(6, -1, -1):
        day = (now - timedelta(days=day_offset)).date()
        label = day.strftime("%a")
        count = sum(1 for incident in incidents if incident.last_seen_at.date() == day)
        buckets.append(IncidentActivityPointResponse(label=label, count=count))
    return buckets
