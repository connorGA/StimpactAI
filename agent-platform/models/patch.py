from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _decode_json_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


class PatchRunStatus(StrEnum):
    GENERATED = "generated"
    FAILED = "failed"


class PatchTargetFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    reason: str


class PatchProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patch_summary: str
    rationale: str
    target_files: list[PatchTargetFile] = Field(default_factory=list)
    unified_diff: str
    verification_steps: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class PatchRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    incident_id: str
    repo_profile_id: str | None = None
    status: PatchRunStatus
    patch_summary: str
    rationale: str
    target_files: list[PatchTargetFile] = Field(default_factory=list)
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
    def from_db_row(cls, row: Any) -> "PatchRunRecord":
        raw_target_files = _decode_json_value(row["target_files"]) or []
        raw_verification_steps = _decode_json_value(row["verification_steps"]) or []
        return cls(
            id=str(row["id"]),
            incident_id=str(row["incident_id"]),
            repo_profile_id=str(row["repo_profile_id"]) if row["repo_profile_id"] is not None else None,
            status=PatchRunStatus(str(row["status"])),
            patch_summary=str(row["patch_summary"]),
            rationale=str(row["rationale"]),
            target_files=[
                PatchTargetFile.model_validate(item)
                for item in raw_target_files
                if isinstance(item, dict)
            ],
            unified_diff=str(row["unified_diff"]),
            verification_steps=[str(item) for item in raw_verification_steps],
            confidence=float(row["confidence"]),
            model_name=str(row["model_name"]),
            based_on_commit_sha=row["based_on_commit_sha"],
            diff_line_count=int(row["diff_line_count"]),
            file_count=int(row["file_count"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
