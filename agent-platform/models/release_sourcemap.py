from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ReleaseSourcemapRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    release: str
    dist: str
    artifact_id: str
    bundle_path: str
    created_at: datetime

    @classmethod
    def from_db_row(cls, row: Any) -> "ReleaseSourcemapRecord":
        return cls(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            release=str(row["release"]),
            dist=str(row["dist"]),
            artifact_id=str(row["artifact_id"]),
            bundle_path=str(row["bundle_path"]),
            created_at=row["created_at"],
        )
