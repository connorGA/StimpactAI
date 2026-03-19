from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AutonomousRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AutonomousRunPhase(StrEnum):
    INITIALIZER = "initializer"
    CODING = "coding"
    VERIFICATION = "verification"
    RECOVERY = "recovery"
    COMPLETED = "completed"
    FAILED = "failed"


class AutonomousExecutionMode(StrEnum):
    INVESTIGATE_ONLY = "investigate_only"
    REPAIR_ONLY = "repair_only"
    REPAIR_AND_PROPOSE = "repair_and_propose"


class AutonomousApprovalStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AutonomousPromotionStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    READY = "ready"
    PROPOSED = "proposed"
    BLOCKED = "blocked"


class AutonomousEventType(StrEnum):
    RUN_STARTED = "run_started"
    PHASE_CHANGED = "phase_changed"
    SESSION_INITIALIZED = "session_initialized"
    INITIALIZER_OUTPUT_GENERATED = "initializer_output_generated"
    INITIALIZER_OUTPUT_PERSISTED = "initializer_output_persisted"
    CODING_SESSION_READY = "coding_session_ready"
    DECISION_MADE = "decision_made"
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    VERIFICATION_STATE_UPDATED = "verification_state_updated"
    GIT_CHECKPOINT_CREATED = "git_checkpoint_created"
    RECOVERY_INVOKED = "recovery_invoked"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


class AutonomousDecisionAction(StrEnum):
    INVOKE_TOOL = "invoke_tool"
    COMPLETE = "complete"
    FAIL = "fail"


class AutonomousDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=1_000)
    rationale: str | None = Field(default=None, max_length=2_000)
    action: AutonomousDecisionAction = AutonomousDecisionAction.INVOKE_TOOL
    selected_tool: str | None = Field(default=None, max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)
    arguments_summary: str | None = Field(default=None, max_length=1_000)
    feature_id: str | None = Field(default=None, max_length=128)
    verification_kind: str | None = Field(default=None, max_length=64)

    @field_validator("arguments", mode="before")
    @classmethod
    def normalize_arguments(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError("arguments must be a dictionary when provided")
        return value


class AutonomousLoopState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_index: int = Field(ge=0, default=0)
    max_steps: int = Field(ge=1, default=12)
    checkpoint_ref: str | None = Field(default=None, max_length=256)
    recovery_attempts: int = Field(ge=0, default=0)
    consecutive_failures: int = Field(ge=0, default=0)
    stagnation_count: int = Field(ge=0, default=0)
    last_tool_name: str | None = Field(default=None, max_length=128)
    recent_tool_names: list[str] = Field(default_factory=list, max_length=12)
    last_tool_ok: bool | None = None
    last_tool_result: dict[str, Any] = Field(default_factory=dict)
    last_failure: AutonomousToolFailure | None = None
    recent_failure_signatures: list[str] = Field(default_factory=list, max_length=8)


class AutonomousToolFailureClass(StrEnum):
    VALIDATION = "validation"
    VERIFICATION = "verification"
    TOOL_ERROR = "tool_error"
    STAGNATION = "stagnation"
    EXCEPTION = "exception"
    UNKNOWN = "unknown"


class AutonomousToolFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1, max_length=128)
    failure_class: AutonomousToolFailureClass
    message: str = Field(min_length=1, max_length=2_000)
    hint: str | None = Field(default=None, max_length=1_000)
    signature: str = Field(min_length=1, max_length=512)
    repeated_count: int = Field(ge=1, default=1)
    details: dict[str, Any] = Field(default_factory=dict)


class AutonomousVerificationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=64)
    kind: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=1_000)
    passed: bool
    command: str | None = Field(default=None, max_length=8_000)
    recorded_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class AutonomousPolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto_run_allowed: bool = False
    requires_human_approval: bool = False
    allow_writeback: bool = False
    allowed_execution_backends: list[str] = Field(default_factory=list)
    allowed_tool_categories: list[str] = Field(default_factory=list)
    require_browser_verification: bool = False
    max_repair_attempts: int = Field(ge=1, default=1)
    max_retry_budget: int = Field(ge=0, default=0)
    reasons: list[str] = Field(default_factory=list)


class AutonomousRepairRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    incident_id: str | None = Field(default=None, max_length=128)
    async_job_id: str | None = Field(default=None, max_length=128)
    repo_profile_id: str | None = Field(default=None, max_length=128)
    patch_run_id: str | None = Field(default=None, max_length=128)
    sandbox_run_id: str | None = Field(default=None, max_length=128)
    promotion_branch_name: str | None = Field(default=None, max_length=256)
    promotion_url: str | None = Field(default=None, max_length=2048)
    repository_root: str = Field(min_length=1, max_length=4096)
    objective: str = Field(min_length=1, max_length=1_000)
    status: AutonomousRunStatus
    phase: AutonomousRunPhase
    execution_mode: AutonomousExecutionMode = AutonomousExecutionMode.REPAIR_ONLY
    approval_status: AutonomousApprovalStatus = AutonomousApprovalStatus.NOT_REQUIRED
    promotion_status: AutonomousPromotionStatus = AutonomousPromotionStatus.NOT_REQUESTED
    initializer_session_id: str | None = Field(default=None, max_length=128)
    coding_session_id: str | None = Field(default=None, max_length=128)
    last_error: str | None = Field(default=None, max_length=4_000)
    benchmark_scenario_id: str | None = Field(default=None, max_length=128)
    benchmark_bug_class: str | None = Field(default=None, max_length=128)
    latest_verification: AutonomousVerificationEvidence | None = None
    policy: AutonomousPolicyDecision = Field(default_factory=AutonomousPolicyDecision)
    loop_state: AutonomousLoopState = Field(default_factory=AutonomousLoopState)
    created_at: datetime
    updated_at: datetime


class AutonomousRunEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    event_type: AutonomousEventType
    phase: AutonomousRunPhase
    summary: str = Field(min_length=1, max_length=1_000)
    decision: AutonomousDecision | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AutonomousRunSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: AutonomousRepairRunRecord
    events: list[AutonomousRunEvent] = Field(default_factory=list)


class AutonomousRunOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=128)
    incident_id: str | None = Field(default=None, max_length=128)
    status: AutonomousRunStatus
    phase: AutonomousRunPhase
    objective: str = Field(min_length=1, max_length=1_000)
    repository_root: str = Field(min_length=1, max_length=4096)
    benchmark_scenario_id: str | None = Field(default=None, max_length=128)
    benchmark_bug_class: str | None = Field(default=None, max_length=128)
    execution_mode: AutonomousExecutionMode = AutonomousExecutionMode.REPAIR_ONLY
    approval_status: AutonomousApprovalStatus = AutonomousApprovalStatus.NOT_REQUIRED
    promotion_status: AutonomousPromotionStatus = AutonomousPromotionStatus.NOT_REQUESTED
    checkpoint_ref: str | None = Field(default=None, max_length=256)
    recovery_attempts: int = Field(ge=0, default=0)
    stagnation_count: int = Field(ge=0, default=0)
    total_steps: int = Field(ge=0, default=0)
    total_decisions: int = Field(ge=0, default=0)
    total_tool_calls: int = Field(ge=0, default=0)
    total_events: int = Field(ge=0, default=0)
    last_error: str | None = Field(default=None, max_length=4_000)
    latest_verification: AutonomousVerificationEvidence | None = None
    final_success: bool = False
    fresh_verification_satisfied: bool = False
    failure_class: AutonomousToolFailureClass | None = None
    policy: AutonomousPolicyDecision = Field(default_factory=AutonomousPolicyDecision)
    created_at: datetime
    completed_at: datetime


class AutonomousArtifactPaths(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_path: str = Field(min_length=1, max_length=4096)
    events_path: str = Field(min_length=1, max_length=4096)
    outcome_path: str | None = Field(default=None, max_length=4096)
