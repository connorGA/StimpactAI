from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI

from api.core.config import get_openai_api_key, get_openai_patch_model, get_openai_rca_model
from api.core.errors import APIError
from api.core.security import require_project_list_access, require_project_read_access
from api.db.postgres import PostgresConnectionManager, get_postgres_manager
from api.repositories.artifact_repository import ArtifactRepository
from api.repositories.async_job_repository import AsyncJobRepository
from api.repositories.autonomous_repository import AutonomousRunRepository
from api.repositories.control_plane_repository import ControlPlaneRepository
from api.repositories.incident_repository import IncidentRepository
from api.repositories.patch_repository import PatchRepository
from api.repositories.sandbox_repository import SandboxRepository
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
    SandboxRunAttemptResponse,
    SandboxRunQueuedResponse,
    SandboxRunStepResponse,
    IncidentSummaryResponse,
)
from harness.schemas.autonomous import AutonomousRepairRunRecord
from models.incident import IncidentStatus
from services.autonomous_runs import AutonomousRunService
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


def get_failure_classifier() -> FailureClassifier:
    return FailureClassifier()


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
    return IncidentReportingOverviewResponse(
        project_id=project_id,
        total_visible_incidents=len(incidents),
        open_incidents=sum(1 for incident in incidents if incident.status == IncidentStatus.OPEN),
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
