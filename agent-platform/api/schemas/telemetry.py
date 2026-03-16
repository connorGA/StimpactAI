from __future__ import annotations

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

    @field_validator("commit_sha")
    @classmethod
    def normalize_commit_sha(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip().lower()
        return normalized or None


class TelemetryAcceptedResponse(BaseModel):
    status: Literal["accepted"] = "accepted"
    telemetry_id: str
    fingerprint: str
