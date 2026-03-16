from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class IncidentEventType(StrEnum):
    TELEMETRY_RECEIVED = "telemetry.received"


class IncidentEvent(BaseModel):
    event_type: IncidentEventType = IncidentEventType.TELEMETRY_RECEIVED
    telemetry_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    fingerprint: str = Field(min_length=1)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)
