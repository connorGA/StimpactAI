from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from shared.types.telemetry import HttpRequestContext, HttpResponseContext, TelemetryEnvelope


class TelemetryErrorRequest(TelemetryEnvelope):
    error_message: str = Field(min_length=1, max_length=10_000)
    stacktrace: str = Field(min_length=1, max_length=50_000)
    request: HttpRequestContext | None = None
    response: HttpResponseContext | None = None

    @field_validator("project_id", "service", "error_message", "stacktrace")
    @classmethod
    def ensure_non_empty_trimmed_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("commit_sha", "release", "dist", "session_id")
    @classmethod
    def normalize_optional_value(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip().lower()
        return normalized or None


class TelemetryAcceptedResponse(BaseModel):
    status: Literal["accepted"] = "accepted"
    telemetry_id: str
    fingerprint: str


class BrowserTelemetryTokenIssueRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=128)
    browser_key: str = Field(min_length=1, max_length=512)
    service: str = Field(min_length=1, max_length=128)
    environment: str = Field(default="production", min_length=1, max_length=32)

    @field_validator("project_id", "browser_key", "service", "environment")
    @classmethod
    def ensure_non_empty_trimmed_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class BrowserTelemetryTokenIssueResponse(BaseModel):
    token_type: Literal["bearer"] = "bearer"
    token: str
    expires_at: datetime
    expires_in_seconds: int


class TelemetryHeartbeatRequest(TelemetryEnvelope):
    @field_validator("project_id", "service")
    @classmethod
    def ensure_non_empty_trimmed_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("commit_sha", "release", "dist", "session_id")
    @classmethod
    def normalize_optional_value(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None


class TelemetryHeartbeatAcceptedResponse(BaseModel):
    status: Literal["accepted"] = "accepted"
    project_id: str
    service: str
    environment: str
    last_seen_at: datetime
