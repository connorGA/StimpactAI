from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class SandboxRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SandboxRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    incident_id: str
    patch_run_id: str
    repo_profile_id: str | None = None
    async_job_id: str | None = None
    status: SandboxRunStatus
    executor_backend: str = "local"
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
    def from_db_row(cls, row: Any) -> "SandboxRunRecord":
        return cls(
            id=str(row["id"]),
            incident_id=str(row["incident_id"]),
            patch_run_id=str(row["patch_run_id"]),
            repo_profile_id=str(row["repo_profile_id"]) if row["repo_profile_id"] is not None else None,
            async_job_id=str(row["async_job_id"]) if row["async_job_id"] is not None else None,
            status=SandboxRunStatus(str(row["status"])),
            executor_backend=str(row["executor_backend"]),
            external_job_id=row["external_job_id"],
            install_command=row["install_command"],
            reproduce_command=str(row["reproduce_command"]),
            verify_command=str(row["verify_command"]),
            reproduction_succeeded=bool(row["reproduction_succeeded"]),
            patch_applied=bool(row["patch_applied"]),
            verification_succeeded=bool(row["verification_succeeded"]),
            summary=str(row["summary"]),
            execution_log=str(row["execution_log"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class SandboxRunStepRecord(BaseModel):
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
    def from_db_row(cls, row: Any) -> "SandboxRunStepRecord":
        return cls(
            id=str(row["id"]),
            sandbox_run_id=str(row["sandbox_run_id"]),
            step_name=str(row["step_name"]),
            status=SandboxRunStatus(str(row["status"])),
            command=row["command"],
            summary=str(row["summary"]),
            artifact_id=str(row["artifact_id"]) if row["artifact_id"] is not None else None,
            exit_code=int(row["exit_code"]) if row["exit_code"] is not None else None,
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            created_at=row["created_at"],
        )


class SandboxRunAttemptRecord(BaseModel):
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
    def from_db_row(cls, row: Any) -> "SandboxRunAttemptRecord":
        return cls(
            id=str(row["id"]),
            sandbox_run_id=str(row["sandbox_run_id"]),
            async_job_id=str(row["async_job_id"]) if row["async_job_id"] is not None else None,
            attempt_number=int(row["attempt_number"]),
            status=SandboxRunStatus(str(row["status"])),
            error_message=row["error_message"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )
