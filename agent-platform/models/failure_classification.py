from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FailureCategory(StrEnum):
    APPLICATION_BUG = "application_bug"
    AUTHORIZATION_FAILURE = "authorization_failure"
    CONFIGURATION_ERROR = "configuration_error"
    DATABASE_FAILURE = "database_failure"
    DEPENDENCY_FAILURE = "dependency_failure"
    NETWORK_FAILURE = "network_failure"
    NULL_REFERENCE = "null_reference"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    TIMEOUT = "timeout"
    VALIDATION_FAILURE = "validation_failure"
    UNKNOWN = "unknown"


class FailureClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: FailureCategory
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    matched_signals: list[str] = Field(default_factory=list)
    inspected_event_count: int = Field(ge=0)
