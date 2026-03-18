from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class ArtifactStorageBackend(StrEnum):
    S3 = "s3"


class ArtifactType(StrEnum):
    EXECUTION_LOG = "execution_log"
    PATCH_DIFF = "patch_diff"
    TEST_REPORT = "test_report"
    SANDBOX_MANIFEST = "sandbox_manifest"
    SANDBOX_STEP_LOG = "sandbox_step_log"


class ArtifactRecord(BaseModel):
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
    def from_db_row(cls, row: Any) -> "ArtifactRecord":
        return cls(
            id=str(row["id"]),
            incident_id=str(row["incident_id"]) if row["incident_id"] is not None else None,
            patch_run_id=str(row["patch_run_id"]) if row["patch_run_id"] is not None else None,
            sandbox_run_id=str(row["sandbox_run_id"]) if row["sandbox_run_id"] is not None else None,
            artifact_type=ArtifactType(str(row["artifact_type"])),
            storage_backend=ArtifactStorageBackend(str(row["storage_backend"])),
            bucket_name=str(row["bucket_name"]),
            object_key=str(row["object_key"]),
            uri=str(row["uri"]),
            content_type=str(row["content_type"]),
            size_bytes=int(row["size_bytes"]),
            checksum_sha256=row["checksum_sha256"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
