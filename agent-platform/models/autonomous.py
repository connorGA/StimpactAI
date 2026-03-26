from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from harness.schemas.autonomous import AutonomousRepairRunRecord, AutonomousRunOutcome
from harness.schemas.initializer import FeatureSeed


class AutonomousRunPersistenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    incident_id: str
    project_service_id: str | None = None
    repo_profile_id: str | None = None
    async_job_id: str | None = None
    feature_seeds: list[FeatureSeed] = Field(default_factory=list)
    initializer_summary: str
    max_steps: int = Field(ge=1, default=8)
    run: AutonomousRepairRunRecord
    outcome: AutonomousRunOutcome | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_db_row(cls, row: Any) -> "AutonomousRunPersistenceRecord":
        feature_seeds = row["feature_seeds"]
        if isinstance(feature_seeds, str):
            try:
                feature_seeds = json.loads(feature_seeds)
            except json.JSONDecodeError:
                feature_seeds = []
        if not isinstance(feature_seeds, list):
            feature_seeds = []
        raw_run = row["run_snapshot"]
        raw_outcome = row["outcome_snapshot"]
        if isinstance(raw_run, str):
            raw_run = json.loads(raw_run)
        if isinstance(raw_outcome, str):
            raw_outcome = json.loads(raw_outcome)
        if not isinstance(raw_run, dict):
            raise ValueError("autonomous run snapshot must be a JSON object")
        return cls(
            id=str(row["id"]),
            incident_id=str(row["incident_id"]),
            project_service_id=str(row["project_service_id"]) if row["project_service_id"] is not None else None,
            repo_profile_id=str(row["repo_profile_id"]) if row["repo_profile_id"] is not None else None,
            async_job_id=str(row["async_job_id"]) if row["async_job_id"] is not None else None,
            feature_seeds=[FeatureSeed.model_validate(item) for item in feature_seeds if isinstance(item, dict)],
            initializer_summary=str(row["initializer_summary"]),
            max_steps=int(row["max_steps"]),
            run=AutonomousRepairRunRecord.model_validate(raw_run),
            outcome=AutonomousRunOutcome.model_validate(raw_outcome) if isinstance(raw_outcome, dict) else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
