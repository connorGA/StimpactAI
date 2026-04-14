from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from shared.types.telemetry import Environment


class IncidentStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class IncidentSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def _decode_json_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


class TelemetryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    environment: Environment
    service: str
    error_message: str
    stacktrace: str
    fingerprint: str
    request_payload: dict[str, Any] | list[Any] | str | None = None
    response_payload: dict[str, Any] | list[Any] | str | None = None
    commit_sha: str | None = None
    occurred_at: datetime
    received_at: datetime

    @classmethod
    def from_db_row(cls, row: Any) -> "TelemetryRecord":
        return cls(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            environment=Environment(str(row["environment"])),
            service=str(row["service"]),
            error_message=str(row["error_message"]),
            stacktrace=str(row["stacktrace"]),
            fingerprint=str(row["fingerprint"]),
            request_payload=_decode_json_value(row["request_payload"]),
            response_payload=_decode_json_value(row["response_payload"]),
            commit_sha=row["commit_sha"],
            occurred_at=row["occurred_at"],
            received_at=row["received_at"],
        )


class IncidentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    project_service_id: str | None = None
    repo_profile_id: str | None = None
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
    resolved_at: datetime | None = None
    resolution_source: str | None = None

    @classmethod
    def from_db_row(cls, row: Any) -> "IncidentRecord":
        return cls(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            project_service_id=str(row["project_service_id"]) if row["project_service_id"] is not None else None,
            repo_profile_id=str(row["repo_profile_id"]) if row["repo_profile_id"] is not None else None,
            fingerprint=str(row["fingerprint"]),
            service=str(row["service"]),
            environment=Environment(str(row["environment"])),
            title=str(row["title"]),
            status=IncidentStatus(str(row["status"])),
            severity=IncidentSeverity(str(row["severity"])),
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
            event_count=int(row["event_count"]),
            latest_telemetry_id=str(row["latest_telemetry_id"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            resolved_at=row["resolved_at"] if row["resolved_at"] is not None else None,
            resolution_source=(
                str(row["resolution_source"]) if row["resolution_source"] is not None else None
            ),
        )


class IncidentProcessingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str
    created_new_incident: bool
    attached_telemetry: bool
    severity: IncidentSeverity
    event_count: int


class IncidentEventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    incident_id: str
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
    def from_db_row(cls, row: Any) -> "IncidentEventRecord":
        return cls(
            id=str(row["id"]),
            incident_id=str(row["incident_id"]),
            telemetry_id=str(row["telemetry_id"]),
            event_type=str(row["event_type"]),
            error_message=str(row["error_message"]),
            stacktrace=str(row["stacktrace"]),
            request_payload=_decode_json_value(row["request_payload"]),
            response_payload=_decode_json_value(row["response_payload"]),
            payload=_decode_json_value(row["payload"]),
            occurred_at=row["occurred_at"],
            created_at=row["created_at"],
        )
