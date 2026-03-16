from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from models.incident import IncidentEventRecord, IncidentRecord, IncidentSeverity, IncidentStatus
from shared.types.telemetry import Environment


class IncidentSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
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

    @classmethod
    def from_record(cls, incident: IncidentRecord) -> "IncidentSummaryResponse":
        return cls(**incident.model_dump())


class IncidentEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
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
    def from_record(cls, incident_event: IncidentEventRecord) -> "IncidentEventResponse":
        return cls(
            id=incident_event.id,
            telemetry_id=incident_event.telemetry_id,
            event_type=incident_event.event_type,
            error_message=incident_event.error_message,
            stacktrace=incident_event.stacktrace,
            request_payload=incident_event.request_payload,
            response_payload=incident_event.response_payload,
            payload=incident_event.payload,
            occurred_at=incident_event.occurred_at,
            created_at=incident_event.created_at,
        )


class IncidentListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[IncidentSummaryResponse] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class IncidentDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident: IncidentSummaryResponse
    events: list[IncidentEventResponse] = Field(default_factory=list)
