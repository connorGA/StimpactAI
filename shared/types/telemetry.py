from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Environment(StrEnum):
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"
    TEST = "test"


class HttpRequestContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    method: str | None = Field(default=None, max_length=16)
    url: str | None = Field(default=None, max_length=2048)
    headers: dict[str, str] = Field(default_factory=dict)
    query_params: dict[str, Any] = Field(default_factory=dict)
    body: dict[str, Any] | list[Any] | str | None = None
    client_ip: str | None = Field(default=None, max_length=64)
    request_id: str | None = Field(default=None, max_length=128)


class HttpResponseContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    status_code: int | None = Field(default=None, ge=100, le=599)
    headers: dict[str, str] = Field(default_factory=dict)
    body: dict[str, Any] | list[Any] | str | None = None


class TelemetryEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=128)
    environment: Environment
    service: str = Field(min_length=1, max_length=128)
    commit_sha: str | None = Field(default=None, max_length=64)
    timestamp: datetime
    handled: bool | None = Field(
        default=None,
        description=(
            "Whether the error was caught/handled at the call site before being reported. "
            "True indicates the caller explicitly captured a known error (e.g. a failed login) "
            "and treats this as a user-facing outcome rather than an unhandled exception."
        ),
    )
