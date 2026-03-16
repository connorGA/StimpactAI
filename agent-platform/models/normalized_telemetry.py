from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from shared.types.telemetry import Environment, HttpRequestContext, HttpResponseContext


def build_fingerprint(
    *,
    project_id: str,
    environment: Environment,
    service: str,
    error_message: str,
    stacktrace: str,
) -> str:
    canonical_error = " ".join(error_message.split()).lower()
    canonical_stacktrace = "\n".join(line.strip() for line in stacktrace.strip().splitlines() if line.strip())
    digest_source = "::".join(
        [
            project_id.strip().lower(),
            environment.value,
            service.strip().lower(),
            canonical_error,
            canonical_stacktrace,
        ]
    )
    return sha256(digest_source.encode("utf-8")).hexdigest()


class NormalizedTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    environment: Environment
    service: str
    error_message: str
    stacktrace: str
    fingerprint: str
    request: HttpRequestContext | None = None
    response: HttpResponseContext | None = None
    commit_sha: str | None = None
    occurred_at: datetime
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_validated_request(
        cls,
        *,
        project_id: str,
        environment: Environment,
        service: str,
        error_message: str,
        stacktrace: str,
        request: HttpRequestContext | None,
        response: HttpResponseContext | None,
        commit_sha: str | None,
        timestamp: datetime,
    ) -> "NormalizedTelemetry":
        normalized_error_message = " ".join(error_message.split())
        normalized_stacktrace = "\n".join(
            line.strip() for line in stacktrace.strip().splitlines() if line.strip()
        )

        return cls(
            project_id=project_id.strip(),
            environment=environment,
            service=service.strip(),
            error_message=normalized_error_message,
            stacktrace=normalized_stacktrace,
            fingerprint=build_fingerprint(
                project_id=project_id,
                environment=environment,
                service=service,
                error_message=normalized_error_message,
                stacktrace=normalized_stacktrace,
            ),
            request=request,
            response=response,
            commit_sha=commit_sha,
            occurred_at=timestamp.astimezone(UTC),
        )
