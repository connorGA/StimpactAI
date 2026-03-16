from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.core.errors import register_exception_handlers
from api.events.publisher import IncidentEventPublisher
from api.routes.incidents import (
    get_failure_classifier,
    get_incident_repository,
    get_root_cause_analysis_service,
    router as incidents_router,
)
from api.routes.telemetry import (
    get_incident_event_publisher,
    get_outbox_signaler,
    get_telemetry_repository,
    router as telemetry_router,
)
from models.failure_classification import FailureCategory, FailureClassification
from models.incident import IncidentEventRecord, IncidentRecord, IncidentSeverity, IncidentStatus
from models.root_cause import RootCauseAnalysis, RootCauseEvidence, RootCauseReasoning
from shared.events.incident_events import IncidentEvent, IncidentEventType
from shared.types.telemetry import Environment


def build_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(telemetry_router)
    app.include_router(incidents_router)
    return app


class RecordingTelemetryRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    async def insert_event_with_outbox(self, telemetry: object, incident_event: object) -> str:
        self.calls.append((telemetry, incident_event))
        return "outbox-1"


class RecordingOutboxSignaler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def signal(self, *, event_id: str, event_type: str) -> None:
        self.calls.append((event_id, event_type))


class StubIncidentRepository:
    def __init__(self) -> None:
        now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
        self.incident = IncidentRecord(
            id="incident-1",
            project_id="project-1",
            fingerprint="fingerprint-1",
            service="billing-api",
            environment=Environment.PRODUCTION,
            title="billing-api: Database timeout",
            status=IncidentStatus.OPEN,
            severity=IncidentSeverity.CRITICAL,
            first_seen_at=now,
            last_seen_at=now,
            event_count=2,
            latest_telemetry_id="telemetry-2",
            created_at=now,
            updated_at=now,
        )
        self.events = [
            IncidentEventRecord(
                id="event-1",
                incident_id="incident-1",
                telemetry_id="telemetry-2",
                event_type="telemetry.received",
                error_message="Database timeout",
                stacktrace="Traceback:\nline 1",
                request_payload={"method": "POST"},
                response_payload={"status_code": 503},
                payload={"environment": "production"},
                occurred_at=now,
                created_at=now,
            )
        ]
        self.last_list_kwargs: dict[str, object] | None = None

    async def list_incidents(
        self,
        *,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[IncidentRecord], int]:
        self.last_list_kwargs = {
            "project_id": project_id,
            "status": status,
            "limit": limit,
            "offset": offset,
        }
        return [self.incident], 1

    async def get_incident(self, incident_id: str) -> IncidentRecord | None:
        return self.incident if incident_id == self.incident.id else None

    async def list_incident_events(self, incident_id: str, *, limit: int = 100) -> list[IncidentEventRecord]:
        assert incident_id == self.incident.id
        assert limit >= 1
        return self.events[:limit]


class StubFailureClassifier:
    def classify(
        self,
        incident: IncidentRecord,
        events: list[IncidentEventRecord],
    ) -> FailureClassification:
        assert incident.id == "incident-1"
        assert len(events) == 1
        return FailureClassification(
            category=FailureCategory.DATABASE_FAILURE,
            confidence=0.91,
            summary="The billing-api incident is most likely a database failure based on database, postgres.",
            matched_signals=["database", "postgres"],
            inspected_event_count=len(events),
        )


class StubRootCauseAnalysisService:
    async def analyze_incident(
        self,
        incident_id: str,
        *,
        event_limit: int = 50,
    ) -> RootCauseAnalysis:
        assert incident_id == "incident-1"
        assert event_limit == 20
        return RootCauseAnalysis(
            incident_id=incident_id,
            category=FailureCategory.DATABASE_FAILURE,
            category_summary="The billing-api incident is most likely a database failure based on database, postgres.",
            category_confidence=0.91,
            evidence=RootCauseEvidence(
                suspected_component="agent-platform/api/repositories/incident_repository.py",
                evidence_summary="Stack signals and code search both point toward the incident repository path.",
                stack_trace_signals=["incident_repository.py", "fetchrow"],
                search_terms=["database", "postgres", "fetchrow"],
                code_candidates=[],
                git_signals=[],
                evidence_confidence=0.72,
                latest_commit_sha="abc123",
                inspected_event_count=1,
            ),
            reasoning=RootCauseReasoning(
                root_cause_hypothesis="A database query path is timing out inside the incident repository layer.",
                reasoning_summary="The grounded evidence points to the repository layer handling database reads.",
                alternative_hypotheses=["An upstream connection-pool issue is also possible."],
                confidence=0.78,
            ),
        )


def test_ingest_error_returns_accepted_response_and_signals_outbox() -> None:
    app = build_test_app()
    telemetry_repository = RecordingTelemetryRepository()
    outbox_signaler = RecordingOutboxSignaler()

    app.dependency_overrides[get_telemetry_repository] = lambda: telemetry_repository
    app.dependency_overrides[get_incident_event_publisher] = IncidentEventPublisher
    app.dependency_overrides[get_outbox_signaler] = lambda: outbox_signaler

    client = TestClient(app)
    response = client.post(
        "/telemetry/error",
        json={
            "project_id": "project-1",
            "environment": "production",
            "service": "billing-api",
            "error_message": "  Database timeout  ",
            "stacktrace": "Traceback:\nline 1\n",
            "request": {"method": "POST"},
            "response": {"status_code": 503},
            "commit_sha": "ABC123",
            "timestamp": "2026-03-16T12:00:00Z",
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert len(body["telemetry_id"]) > 10
    assert len(body["fingerprint"]) == 64
    assert len(telemetry_repository.calls) == 1
    assert outbox_signaler.calls == [("outbox-1", IncidentEventType.TELEMETRY_RECEIVED.value)]


def test_list_incidents_passes_filters_and_serializes_response() -> None:
    app = build_test_app()
    repository = StubIncidentRepository()
    app.dependency_overrides[get_incident_repository] = lambda: repository

    client = TestClient(app)
    response = client.get(
        "/incidents",
        params={"project_id": "project-1", "status": "open", "limit": 25, "offset": 5},
    )

    assert response.status_code == 200
    assert repository.last_list_kwargs == {
        "project_id": "project-1",
        "status": "open",
        "limit": 25,
        "offset": 5,
    }
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == "incident-1"
    assert body["items"][0]["severity"] == "critical"


def test_get_incident_returns_detail_payload() -> None:
    app = build_test_app()
    repository = StubIncidentRepository()
    app.dependency_overrides[get_incident_repository] = lambda: repository

    client = TestClient(app)
    response = client.get("/incidents/incident-1", params={"event_limit": 20})

    assert response.status_code == 200
    body = response.json()
    assert body["incident"]["id"] == "incident-1"
    assert body["events"][0]["telemetry_id"] == "telemetry-2"


def test_get_missing_incident_returns_not_found() -> None:
    app = build_test_app()
    repository = StubIncidentRepository()
    app.dependency_overrides[get_incident_repository] = lambda: repository

    client = TestClient(app)
    response = client.get("/incidents/missing-incident")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "incident_not_found"


def test_get_incident_classification_returns_category_payload() -> None:
    app = build_test_app()
    repository = StubIncidentRepository()
    app.dependency_overrides[get_incident_repository] = lambda: repository
    app.dependency_overrides[get_failure_classifier] = StubFailureClassifier

    client = TestClient(app)
    response = client.get("/incidents/incident-1/classification", params={"event_limit": 20})

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == "incident-1"
    assert body["category"] == "database_failure"
    assert body["matched_signals"] == ["database", "postgres"]


def test_get_incident_root_cause_returns_analysis_payload() -> None:
    app = build_test_app()
    app.dependency_overrides[get_root_cause_analysis_service] = StubRootCauseAnalysisService

    client = TestClient(app)
    response = client.get("/incidents/incident-1/root-cause", params={"event_limit": 20})

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == "incident-1"
    assert body["category"] == "database_failure"
    assert body["reasoning"]["confidence"] == 0.78
    assert body["evidence"]["suspected_component"] == "agent-platform/api/repositories/incident_repository.py"
