from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from harness.schemas.autonomous import (
    AutonomousArtifactPaths,
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
    max_steps: int = Field(default=8, ge=1, le=50)
    feature_seeds: list[FeatureSeed] = Field(default_factory=list)


class AutonomousRunQueuedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: AutonomousRepairRunRecord


class AutonomousRunDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: AutonomousRepairRunRecord
    events: list[AutonomousRunEvent] = Field(default_factory=list)
    outcome: AutonomousRunOutcome | None = None
    artifact_paths: AutonomousArtifactPaths
