from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from openai import AsyncOpenAI

from api.core.config import get_openai_api_key, get_openai_patch_model, get_openai_rca_model
from api.core.errors import APIError
from api.db.postgres import PostgresConnectionManager, get_postgres_manager
from api.repositories.artifact_repository import ArtifactRepository
from api.repositories.async_job_repository import AsyncJobRepository
from api.repositories.control_plane_repository import ControlPlaneRepository
from api.repositories.incident_repository import IncidentRepository
from api.repositories.patch_repository import PatchRepository
from api.repositories.sandbox_repository import SandboxRepository
from api.schemas.incidents import (
    ArtifactResponse,
    IncidentClassificationResponse,
    IncidentDetailResponse,
    IncidentEventResponse,
    IncidentPatchResponse,
    IncidentRootCauseResponse,
    IncidentSandboxRunDetailResponse,
    IncidentSandboxRunResponse,
    IncidentListResponse,
    SandboxRunAttemptResponse,
    SandboxRunQueuedResponse,
    SandboxRunStepResponse,
    IncidentSummaryResponse,
)
from models.async_job import AsyncJobStatus
from models.incident import IncidentStatus
from services.code_context import CodeContextService
from services.failure_classifier import FailureClassifier
from services.patch_generation import PatchGenerationService
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
    patch_generation: PatchGenerationService = Depends(get_patch_generation_service),
) -> SandboxVerificationService:
    return SandboxVerificationService(
        incident_repository,
        sandbox_repository,
        control_plane_repository=control_plane_repository,
        async_job_repository=async_job_repository,
        artifact_repository=artifact_repository,
        patch_generation=patch_generation,
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


@router.get(
    "/{incident_id}/patch",
    response_model=IncidentPatchResponse,
    status_code=status.HTTP_200_OK,
)
async def get_or_generate_patch(
    incident_id: str,
    service: PatchGenerationService = Depends(get_patch_generation_service),
    event_limit: int = Query(default=50, ge=1, le=200),
    refresh: bool = Query(default=False),
) -> IncidentPatchResponse:
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
    incident_id: str,
    service: SandboxVerificationService = Depends(get_sandbox_verification_service),
) -> IncidentSandboxRunResponse:
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
    incident_id: str,
    service: SandboxVerificationService = Depends(get_sandbox_verification_service),
    event_limit: int = Query(default=50, ge=1, le=200),
    refresh_patch: bool = Query(default=False),
) -> SandboxRunQueuedResponse:
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
    incident_id: str,
    service: SandboxVerificationService = Depends(get_sandbox_verification_service),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[IncidentSandboxRunResponse]:
    runs = await service.list_runs(incident_id, limit=limit)
    return [IncidentSandboxRunResponse.from_record(run) for run in runs]


@router.get(
    "/{incident_id}/sandbox-runs/{sandbox_run_id}",
    response_model=IncidentSandboxRunDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def get_sandbox_run_detail(
    incident_id: str,
    sandbox_run_id: str,
    service: SandboxVerificationService = Depends(get_sandbox_verification_service),
    sandbox_repository: SandboxRepository = Depends(get_sandbox_repository),
    artifact_repository: ArtifactRepository = Depends(get_artifact_repository),
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
    "/{incident_id}/sandbox-runs",
    response_model=SandboxRunQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_sandbox_run(
    incident_id: str,
    service: SandboxVerificationService = Depends(get_sandbox_verification_service),
    event_limit: int = Query(default=50, ge=1, le=200),
    refresh_patch: bool = Query(default=False),
) -> SandboxRunQueuedResponse:
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
