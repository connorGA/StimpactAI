from __future__ import annotations

from datetime import UTC, datetime

import pytest

from models.incident import IncidentProcessingResult, IncidentSeverity, TelemetryRecord
from services.incident_creation import (
    IncidentCreationService,
    build_incident_title,
    determine_incident_severity,
)
from shared.events.incident_events import IncidentEvent
from shared.types.telemetry import Environment


def build_telemetry(
    *,
    environment: Environment = Environment.PRODUCTION,
    request_method: str | None = "GET",
    status_code: int | None = 500,
    error_message: str = "Unhandled exception",
) -> TelemetryRecord:
    now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
    request_payload = {"method": request_method} if request_method is not None else None
    response_payload = {"status_code": status_code} if status_code is not None else None
    return TelemetryRecord(
        id="telemetry-1",
        project_id="project-1",
        environment=environment,
        service="billing-api",
        error_message=error_message,
        stacktrace="Traceback:\nline 1",
        fingerprint="fingerprint-1",
        request_payload=request_payload,
        response_payload=response_payload,
        commit_sha="abc123",
        occurred_at=now,
        received_at=now,
    )


@pytest.mark.parametrize(
    ("telemetry", "expected"),
    [
        (build_telemetry(status_code=503), IncidentSeverity.CRITICAL),
        (build_telemetry(status_code=400), IncidentSeverity.HIGH),
        (build_telemetry(status_code=None, request_method="POST"), IncidentSeverity.HIGH),
        (build_telemetry(status_code=200), IncidentSeverity.MEDIUM),
        (build_telemetry(environment=Environment.STAGING, status_code=503), IncidentSeverity.HIGH),
        (build_telemetry(environment=Environment.STAGING, status_code=404), IncidentSeverity.MEDIUM),
        (build_telemetry(environment=Environment.DEVELOPMENT, status_code=503), IncidentSeverity.LOW),
    ],
)
def test_determine_incident_severity(telemetry: TelemetryRecord, expected: IncidentSeverity) -> None:
    assert determine_incident_severity(telemetry) is expected


def test_build_incident_title_trims_and_truncates_message() -> None:
    title = build_incident_title(
        build_telemetry(error_message="   ".join(["timeout"] * 30)),
    )

    assert title.startswith("billing-api: timeout timeout")
    assert len(title) <= len("billing-api: ") + 120


class RecordingIncidentRepository:
    def __init__(self, telemetry: TelemetryRecord) -> None:
        self.telemetry = telemetry
        self.attach_kwargs: dict[str, object] | None = None

    async def get_telemetry(self, telemetry_id: str) -> TelemetryRecord:
        assert telemetry_id == self.telemetry.id
        return self.telemetry

    async def attach_to_incident(self, **kwargs: object) -> IncidentProcessingResult:
        self.attach_kwargs = kwargs
        return IncidentProcessingResult(
            incident_id="incident-1",
            created_new_incident=True,
            attached_telemetry=True,
            severity=kwargs["severity"],
            event_count=1,
        )


@pytest.mark.asyncio
async def test_process_telemetry_received_derives_severity_title_and_payload() -> None:
    telemetry = build_telemetry(status_code=500, error_message=" Payment gateway timed out ")
    repository = RecordingIncidentRepository(telemetry)
    service = IncidentCreationService(repository)
    event = IncidentEvent(
        telemetry_id=telemetry.id,
        project_id=telemetry.project_id,
        fingerprint=telemetry.fingerprint,
        payload={"service": telemetry.service},
    )

    result = await service.process_telemetry_received(event.model_dump(mode="json"))

    assert result.incident_id == "incident-1"
    assert repository.attach_kwargs is not None
    assert repository.attach_kwargs["severity"] is IncidentSeverity.CRITICAL
    assert repository.attach_kwargs["title"] == "billing-api: Payment gateway timed out"
    assert repository.attach_kwargs["event_type"] == "telemetry.received"


class _StubClassifier:
    def __init__(self, verdict):
        self._verdict = verdict

    async def classify(self, _normalized):
        return self._verdict


class _StubTelemetryRepo:
    def __init__(self) -> None:
        self.updates: list[tuple[str, str, str | None, str]] = []

    async def update_classification(
        self, telemetry_id: str, *, classification: str, reason: str | None, source: str
    ) -> None:
        self.updates.append((telemetry_id, classification, reason, source))


@pytest.mark.asyncio
async def test_process_telemetry_suppressed_when_classifier_says_user_error() -> None:
    from services.telemetry_classifier import Classification, ClassificationResult

    telemetry = build_telemetry(
        status_code=403,
        error_message="Invalid credentials",
        request_method="POST",
    )
    repository = RecordingIncidentRepository(telemetry)
    telemetry_repo = _StubTelemetryRepo()
    classifier = _StubClassifier(
        ClassificationResult(
            classification=Classification.USER_ERROR,
            reason="Auth endpoint rejected credentials",
            source="rules",
        )
    )
    service = IncidentCreationService(
        repository,
        classifier=classifier,
        telemetry_repository=telemetry_repo,
    )
    event = IncidentEvent(
        telemetry_id=telemetry.id,
        project_id=telemetry.project_id,
        fingerprint=telemetry.fingerprint,
        payload={"service": telemetry.service},
    )

    result = await service.process_telemetry_received(event.model_dump(mode="json"))

    assert result.suppressed is True
    assert result.created_new_incident is False
    assert result.incident_id is None
    assert result.classification == "user_error"
    assert repository.attach_kwargs is None
    assert telemetry_repo.updates == [
        (telemetry.id, "user_error", "Auth endpoint rejected credentials", "rules")
    ]


@pytest.mark.asyncio
async def test_process_telemetry_ambiguous_creates_incident_with_human_approval() -> None:
    from services.telemetry_classifier import Classification, ClassificationResult

    telemetry = build_telemetry(status_code=404)
    repository = RecordingIncidentRepository(telemetry)
    classifier = _StubClassifier(
        ClassificationResult(
            classification=Classification.CODE_AMBIGUOUS,
            reason="Unclear without human review",
            source="default",
        )
    )
    service = IncidentCreationService(repository, classifier=classifier)
    event = IncidentEvent(
        telemetry_id=telemetry.id,
        project_id=telemetry.project_id,
        fingerprint=telemetry.fingerprint,
        payload={"service": telemetry.service},
    )

    result = await service.process_telemetry_received(event.model_dump(mode="json"))

    assert result.suppressed is False
    assert result.created_new_incident is True
    assert result.requires_human_approval is True
    assert result.classification == "code_ambiguous"
