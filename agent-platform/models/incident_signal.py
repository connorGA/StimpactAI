from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from models.normalized_telemetry import NormalizedTelemetry


class IncidentSignalSource(StrEnum):
    TELEMETRY_ERROR = "telemetry_error"
    CI_FAILURE = "ci_failure"
    DEPLOY_EVENT = "deploy_event"
    PROVIDER_CHECK = "provider_check"
    EXTERNAL_ALERT = "external_alert"
    MANUAL_REPORT = "manual_report"


class IncidentSignal(BaseModel):
    """Normalized incident evidence that can come from telemetry or future signal sources."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    source: IncidentSignalSource
    project_id: str = Field(min_length=1)
    service: str = Field(min_length=1)
    environment: str = Field(min_length=1)
    fingerprint: str = Field(min_length=1)
    title: str = Field(min_length=1)
    message: str = Field(min_length=1)
    commit_sha: str | None = None
    release: str | None = None
    occurred_at: datetime
    evidence: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def from_telemetry(cls, telemetry: NormalizedTelemetry) -> "IncidentSignal":
        return cls(
            id=telemetry.id,
            source=IncidentSignalSource.TELEMETRY_ERROR,
            project_id=telemetry.project_id,
            service=telemetry.service,
            environment=telemetry.environment.value,
            fingerprint=telemetry.fingerprint,
            title=f"{telemetry.service}: {telemetry.error_message}",
            message=telemetry.error_message,
            commit_sha=telemetry.commit_sha,
            release=telemetry.release,
            occurred_at=telemetry.occurred_at,
            evidence={
                "telemetry_id": telemetry.id,
                "stacktrace": telemetry.stacktrace,
                "handled": telemetry.handled,
                "request": telemetry.request.model_dump(mode="json") if telemetry.request else None,
                "response": telemetry.response.model_dump(mode="json") if telemetry.response else None,
                "tags": telemetry.tags,
                "contexts": telemetry.contexts,
            },
        )
