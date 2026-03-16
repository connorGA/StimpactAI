from __future__ import annotations

from datetime import UTC, datetime

from models.normalized_telemetry import NormalizedTelemetry, build_fingerprint
from shared.types.telemetry import Environment


def test_build_fingerprint_ignores_whitespace_and_case() -> None:
    first = build_fingerprint(
        project_id=" Project-123 ",
        environment=Environment.PRODUCTION,
        service="Payments",
        error_message=" Timeout  while charging ",
        stacktrace="Traceback:\n  line 1\n  line 2\n",
    )
    second = build_fingerprint(
        project_id="project-123",
        environment=Environment.PRODUCTION,
        service="payments",
        error_message="timeout while charging",
        stacktrace="Traceback:\nline 1\nline 2",
    )

    assert first == second


def test_from_validated_request_normalizes_payload_and_timestamp() -> None:
    telemetry = NormalizedTelemetry.from_validated_request(
        project_id="  acme-prod  ",
        environment=Environment.PRODUCTION,
        service="  backend-api  ",
        error_message="  ValueError: invalid order   ",
        stacktrace="  Traceback:\n    line 1\n\n    line 2  \n",
        request=None,
        response=None,
        commit_sha="abc123",
        timestamp=datetime(2026, 3, 16, 12, 30, tzinfo=UTC),
    )

    assert telemetry.project_id == "acme-prod"
    assert telemetry.service == "backend-api"
    assert telemetry.error_message == "ValueError: invalid order"
    assert telemetry.stacktrace == "Traceback:\nline 1\nline 2"
    assert telemetry.occurred_at == datetime(2026, 3, 16, 12, 30, tzinfo=UTC)
    assert len(telemetry.fingerprint) == 64
