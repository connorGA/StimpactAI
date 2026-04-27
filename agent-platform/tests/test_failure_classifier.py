from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.failure_classification import FailureCategory
from models.incident import IncidentEventRecord, IncidentRecord, IncidentSeverity, IncidentStatus
from services.failure_classifier import FailureClassifier
from shared.types.telemetry import Environment


def build_incident() -> IncidentRecord:
    now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
    return IncidentRecord(
        id="incident-1",
        project_id="project-1",
        fingerprint="fingerprint-1",
        service="billing-api",
        environment=Environment.PRODUCTION,
        title="billing-api: Incident under investigation",
        status=IncidentStatus.OPEN,
        severity=IncidentSeverity.CRITICAL,
        first_seen_at=now,
        last_seen_at=now,
        event_count=1,
        latest_telemetry_id="telemetry-1",
        created_at=now,
        updated_at=now,
    )


def build_event(
    *,
    error_message: str,
    stacktrace: str = "Traceback:\nline 1",
    response_status: int = 500,
) -> IncidentEventRecord:
    now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
    return IncidentEventRecord(
        id="event-1",
        incident_id="incident-1",
        telemetry_id="telemetry-1",
        event_type="telemetry.received",
        error_message=error_message,
        stacktrace=stacktrace,
        request_payload={"method": "POST"},
        response_payload={"status_code": response_status},
        payload={"environment": "production"},
        occurred_at=now,
        created_at=now,
    )


@pytest.mark.parametrize(
    ("event", "expected_category"),
    [
        (build_event(error_message="Database timeout while running postgres query"), FailureCategory.DATABASE_FAILURE),
        (build_event(error_message="Request failed: unauthorized", response_status=401), FailureCategory.AUTHORIZATION_FAILURE),
        (build_event(error_message="Validation failed: missing required field", response_status=422), FailureCategory.VALIDATION_FAILURE),
        (build_event(error_message="TypeError: cannot read properties of undefined"), FailureCategory.NULL_REFERENCE),
        (build_event(error_message="ECONNREFUSED connecting to upstream provider"), FailureCategory.DEPENDENCY_FAILURE),
        (build_event(error_message="Socket hang up while calling internal service"), FailureCategory.NETWORK_FAILURE),
    ],
)
def test_failure_classifier_returns_expected_category(
    event: IncidentEventRecord,
    expected_category: FailureCategory,
) -> None:
    classifier = FailureClassifier()

    result = classifier.classify(build_incident(), [event])

    assert result.category is expected_category
    assert result.confidence > 0.7
    assert result.inspected_event_count == 1


def test_failure_classifier_sync_fallback_is_never_unknown() -> None:
    classifier = FailureClassifier()
    event = build_event(error_message="Something odd happened", stacktrace="mysterious stack", response_status=500)

    result = classifier.classify(build_incident(), [event])

    assert result.category is FailureCategory.APPLICATION_BUG
    assert result.confidence < 0.6
    assert "heuristic" in result.summary.lower() or "application" in result.summary.lower()


async def test_classify_async_invokes_llm_when_rules_miss() -> None:
    content = (
        '{"category":"network_failure","confidence":0.81,'
        '"summary":"The billing-api failure aligns with a connection-level issue in the call path.",'
        '"matched_signals":["mysterious stack"]}'
    )
    create = AsyncMock(
        return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
    )
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=create)

    classifier = FailureClassifier(openai_client=client, model="gpt-4.1-mini")
    event = build_event(
        error_message="Something odd happened",
        stacktrace="mysterious stack",
        response_status=500,
    )
    result = await classifier.classify_async(build_incident(), [event])

    assert result.category is FailureCategory.NETWORK_FAILURE
    assert result.confidence == 0.81
    assert "connection" in result.summary.lower() or "billing" in result.summary.lower()
    create.assert_awaited_once()
