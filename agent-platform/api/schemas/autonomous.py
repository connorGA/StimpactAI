from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from harness.schemas.autonomous import (
    AutonomousArtifactPaths,
    AutonomousApprovalStatus,
    AutonomousExecutionMode,
    AutonomousPolicyDecision,
    AutonomousPromotionStatus,
    AutonomousRepairRunRecord,
    AutonomousRunEvent,
    AutonomousRunOutcome,
)
from harness.schemas.initializer import FeatureSeed


class AutonomousRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_root: str | None = Field(default=None, max_length=4096)
    objective: str | None = Field(default=None, max_length=1_000)
    initializer_summary: str | None = Field(default=None, max_length=2_000)
    execution_mode: AutonomousExecutionMode = AutonomousExecutionMode.REPAIR_ONLY
    requested_backend: str | None = Field(default=None, max_length=64)
    require_human_approval: bool | None = None
    allow_writeback: bool | None = None
    max_steps: int = Field(default=20, ge=1, le=50)
    benchmark_scenario_id: str | None = Field(default=None, max_length=128)
    benchmark_bug_class: str | None = Field(default=None, max_length=128)
    feature_seeds: list[FeatureSeed] = Field(default_factory=list)


class AutonomousRunQueuedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: AutonomousRepairRunRecord
    async_job_id: str | None = None


class AutonomousRunDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: AutonomousRepairRunRecord
    events: list[AutonomousRunEvent] = Field(default_factory=list)
    outcome: AutonomousRunOutcome | None = None
    artifact_paths: AutonomousArtifactPaths


class AutonomousRunApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_status: AutonomousApprovalStatus


class AutonomousRunPromotionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_writeback: bool = False
    status: AutonomousPromotionStatus = AutonomousPromotionStatus.READY
    policy: AutonomousPolicyDecision | None = None
