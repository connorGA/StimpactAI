from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from models.failure_classification import FailureCategory, FailureClassification
from models.incident import IncidentEventRecord, IncidentRecord, IncidentSeverity, IncidentStatus
from models.artifact import ArtifactRecord, ArtifactStorageBackend, ArtifactType
from models.async_job import AsyncJobStatus
from models.patch import PatchRunRecord, PatchRunStatus
from models.root_cause import RootCauseAnalysis
from models.sandbox import (
    SandboxRunAttemptRecord,
    SandboxRunRecord,
    SandboxRunStatus,
    SandboxRunStepRecord,
)
from shared.types.telemetry import Environment


class IncidentSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    fingerprint: str
    service: str
    environment: Environment
    title: str
    status: IncidentStatus
    severity: IncidentSeverity
    first_seen_at: datetime
    last_seen_at: datetime
    event_count: int
    latest_telemetry_id: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, incident: IncidentRecord) -> "IncidentSummaryResponse":
        return cls(**incident.model_dump())


class IncidentEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    telemetry_id: str
    event_type: str
    error_message: str
    stacktrace: str
    request_payload: dict[str, Any] | list[Any] | str | None = None
    response_payload: dict[str, Any] | list[Any] | str | None = None
    payload: dict[str, Any] | list[Any] | str
    occurred_at: datetime
    created_at: datetime

    @classmethod
    def from_record(cls, incident_event: IncidentEventRecord) -> "IncidentEventResponse":
        return cls(
            id=incident_event.id,
            telemetry_id=incident_event.telemetry_id,
            event_type=incident_event.event_type,
            error_message=incident_event.error_message,
            stacktrace=incident_event.stacktrace,
            request_payload=incident_event.request_payload,
            response_payload=incident_event.response_payload,
            payload=incident_event.payload,
            occurred_at=incident_event.occurred_at,
            created_at=incident_event.created_at,
        )


class IncidentListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[IncidentSummaryResponse] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class IncidentCountBreakdownResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    count: int = Field(ge=0)


class IncidentActivityPointResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    count: int = Field(ge=0)


class IncidentReportingOverviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = None
    total_visible_incidents: int = Field(ge=0)
    open_incidents: int = Field(ge=0)
    critical_incidents: int = Field(ge=0)
    total_event_volume: int = Field(ge=0)
    latest_incident_at: datetime | None = None
    service_counts: list[IncidentCountBreakdownResponse] = Field(default_factory=list)
    environment_counts: list[IncidentCountBreakdownResponse] = Field(default_factory=list)
    severity_counts: list[IncidentCountBreakdownResponse] = Field(default_factory=list)
    recent_incident_activity: list[IncidentActivityPointResponse] = Field(default_factory=list)
    daily_incident_activity: list[IncidentActivityPointResponse] = Field(default_factory=list)


class IncidentDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident: IncidentSummaryResponse
    events: list[IncidentEventResponse] = Field(default_factory=list)


class IncidentClassificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str
    category: FailureCategory
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    matched_signals: list[str] = Field(default_factory=list)
    inspected_event_count: int = Field(ge=0)

    @classmethod
    def from_classification(
        cls,
        *,
        incident_id: str,
        classification: FailureClassification,
    ) -> "IncidentClassificationResponse":
        return cls(
            incident_id=incident_id,
            **classification.model_dump(),
        )


class CodeCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str
    symbol: str | None = None
    match_reason: str
    matched_terms: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class GitSignalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str
    commit_sha: str
    commit_summary: str
    committed_at: datetime | None = None
    relevance_reason: str


class CodeSnippetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str
    symbol: str | None = None
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str
    match_reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class RootCauseEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suspected_component: str | None = None
    evidence_summary: str
    stack_trace_signals: list[str] = Field(default_factory=list)
    search_terms: list[str] = Field(default_factory=list)
    code_candidates: list[CodeCandidateResponse] = Field(default_factory=list)
    code_snippets: list[CodeSnippetResponse] = Field(default_factory=list)
    git_signals: list[GitSignalResponse] = Field(default_factory=list)
    evidence_confidence: float = Field(ge=0.0, le=1.0)
    latest_commit_sha: str | None = None
    inspected_event_count: int = Field(ge=0)


class RootCauseReasoningResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_cause_hypothesis: str
    reasoning_summary: str
    alternative_hypotheses: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class IncidentRootCauseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str
    category: FailureCategory
    category_summary: str
    category_confidence: float = Field(ge=0.0, le=1.0)
    evidence: RootCauseEvidenceResponse
    reasoning: RootCauseReasoningResponse

    @classmethod
    def from_analysis(cls, analysis: RootCauseAnalysis) -> "IncidentRootCauseResponse":
        return cls(**analysis.model_dump(mode="json"))


class PatchTargetFileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    reason: str


class IncidentPatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    incident_id: str
    repo_profile_id: str | None = None
    status: PatchRunStatus
    patch_summary: str
    rationale: str
    target_files: list[PatchTargetFileResponse] = Field(default_factory=list)
    unified_diff: str
    verification_steps: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    model_name: str
    based_on_commit_sha: str | None = None
    diff_line_count: int = Field(ge=0)
    file_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: PatchRunRecord) -> "IncidentPatchResponse":
        return cls(**record.model_dump(mode="json"))


class IncidentSandboxRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    incident_id: str
    patch_run_id: str
    repo_profile_id: str | None = None
    async_job_id: str | None = None
    status: SandboxRunStatus
    executor_backend: str
    external_job_id: str | None = None
    install_command: str | None = None
    reproduce_command: str
    verify_command: str
    reproduction_succeeded: bool
    patch_applied: bool
    verification_succeeded: bool
    summary: str
    execution_log: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: SandboxRunRecord) -> "IncidentSandboxRunResponse":
        return cls(**record.model_dump(mode="json"))


class SandboxRunStepResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    sandbox_run_id: str
    step_name: str
    status: SandboxRunStatus
    command: str | None = None
    summary: str
    artifact_id: str | None = None
    exit_code: int | None = None
    started_at: datetime
    finished_at: datetime | None = None
    created_at: datetime

    @classmethod
    def from_record(cls, record: SandboxRunStepRecord) -> "SandboxRunStepResponse":
        return cls(**record.model_dump(mode="json"))


class SandboxRunAttemptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    sandbox_run_id: str
    async_job_id: str | None = None
    attempt_number: int
    status: SandboxRunStatus
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None

    @classmethod
    def from_record(cls, record: SandboxRunAttemptRecord) -> "SandboxRunAttemptResponse":
        return cls(**record.model_dump(mode="json"))


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    incident_id: str | None = None
    patch_run_id: str | None = None
    sandbox_run_id: str | None = None
    artifact_type: ArtifactType
    storage_backend: ArtifactStorageBackend
    bucket_name: str
    object_key: str
    uri: str
    content_type: str
    size_bytes: int
    checksum_sha256: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: ArtifactRecord) -> "ArtifactResponse":
        return cls(**record.model_dump(mode="json"))


class SandboxRunQueuedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sandbox_run: IncidentSandboxRunResponse
    async_job_id: str
    async_job_status: AsyncJobStatus


class IncidentSandboxRunDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: IncidentSandboxRunResponse
    steps: list[SandboxRunStepResponse] = Field(default_factory=list)
    attempts: list[SandboxRunAttemptResponse] = Field(default_factory=list)
    artifacts: list[ArtifactResponse] = Field(default_factory=list)
