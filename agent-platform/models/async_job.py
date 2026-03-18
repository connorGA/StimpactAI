from __future__ import annotations

from datetime import datetime
from enum import StrEnum
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AsyncJobType(StrEnum):
    SANDBOX_RUN = "sandbox_run"
    AUTONOMOUS_REPAIR = "autonomous_repair"


class AsyncJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AsyncJobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    job_type: AsyncJobType
    status: AsyncJobStatus
    dedupe_key: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    attempts: int = Field(ge=0)
    available_at: datetime
    lease_expires_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_db_row(cls, row: Any) -> "AsyncJobRecord":
        payload = row["payload"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return cls(
            id=str(row["id"]),
            job_type=AsyncJobType(str(row["job_type"])),
            status=AsyncJobStatus(str(row["status"])),
            dedupe_key=row["dedupe_key"],
            payload=payload,
            attempts=int(row["attempts"]),
            available_at=row["available_at"],
            lease_expires_at=row["lease_expires_at"],
            last_error=row["last_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class JobAttemptRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    async_job_id: str
    worker_id: str
    status: AsyncJobStatus
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None

    @classmethod
    def from_db_row(cls, row: Any) -> "JobAttemptRecord":
        return cls(
            id=str(row["id"]),
            async_job_id=str(row["async_job_id"]),
            worker_id=str(row["worker_id"]),
            status=AsyncJobStatus(str(row["status"])),
            error_message=row["error_message"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )
