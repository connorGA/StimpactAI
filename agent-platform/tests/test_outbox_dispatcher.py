from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.schemas.autonomous import AutonomousApprovalStatus, AutonomousRunStatus
from models.incident import IncidentProcessingResult, IncidentSeverity
from services.autonomous_trigger import trigger_autonomous_run_for_new_incident
from workers.outbox_dispatcher import OutboxDispatcher


class StubOutboxRepository:
    def __init__(self, events: list[dict[str, object]]) -> None:
        self.events = events
        self.processed_ids: list[str] = []
        self.failed_calls: list[tuple[str, int, str]] = []
        self.reclaimed_with: list[int] = []

    async def reclaim_stale_events(self, *, stale_after_seconds: int = 300) -> list[dict[str, object]]:
        self.reclaimed_with.append(stale_after_seconds)
        return []

    async def lease_pending_events(self, *, limit: int = 100) -> list[dict[str, object]]:
        return self.events[:limit]

    async def mark_processed(self, event_id: str) -> None:
        self.processed_ids.append(event_id)

    async def mark_failed(
        self,
        event_id: str,
        *,
        retry_delay_seconds: int,
        error_message: str,
    ) -> None:
        self.failed_calls.append((event_id, retry_delay_seconds, error_message))


class StubIncidentCreationService:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []
        self.result = IncidentProcessingResult(
            incident_id="incident-1",
            created_new_incident=True,
            attached_telemetry=True,
            severity=IncidentSeverity.CRITICAL,
            event_count=1,
        )

    async def process_telemetry_received(self, payload: dict[str, object]) -> IncidentProcessingResult:
        self.payloads.append(payload)
        return self.result


async def test_outbox_dispatcher_processes_supported_events() -> None:
    repository = StubOutboxRepository(
        [
            {
                "id": "event-1",
                "event_type": "telemetry.received",
                "payload": {"telemetry_id": "telemetry-1"},
            }
        ]
    )
    service = StubIncidentCreationService()
    dispatcher = OutboxDispatcher(repository, service)

    processed = await dispatcher.run_once()

    assert processed == 1
    assert service.payloads == [{"telemetry_id": "telemetry-1"}]
    assert repository.processed_ids == ["event-1"]
    assert repository.failed_calls == []
    assert repository.reclaimed_with == [300]


async def test_outbox_dispatcher_marks_invalid_payloads_as_failed() -> None:
    repository = StubOutboxRepository(
        [
            {
                "id": "event-2",
                "event_type": "telemetry.received",
                "payload": "not-json",
            }
        ]
    )
    service = StubIncidentCreationService()
    dispatcher = OutboxDispatcher(repository, service)

    processed = await dispatcher.run_once()

    assert processed == 1
    assert repository.processed_ids == []
    assert len(repository.failed_calls) == 1
    failed_id, retry_delay, error_message = repository.failed_calls[0]
    assert failed_id == "event-2"
    assert retry_delay == 30
    assert "Expecting value" in error_message
    assert repository.reclaimed_with == [300]


class StubAutonomousRunService:
    def __init__(self, runs: list[object] | None = None) -> None:
        self._runs = runs or []
        self.start_calls: list[dict[str, object]] = []

    async def list_runs(self, incident_id: str):
        _ = incident_id
        return self._runs

    async def start_run(self, incident_id: str, request):
        self.start_calls.append({"incident_id": incident_id, "request": request})
        return SimpleNamespace(run=SimpleNamespace(id="run-2", async_job_id="job-2"))


@pytest.mark.asyncio
async def test_outbox_dispatcher_does_not_trigger_autonomous_run_for_suppressed_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = StubOutboxRepository(
        [
            {
                "id": "event-3",
                "event_type": "telemetry.received",
                "payload": {"telemetry_id": "telemetry-1"},
            }
        ]
    )
    service = StubIncidentCreationService()
    service.result = IncidentProcessingResult(
        incident_id=None,
        created_new_incident=False,
        attached_telemetry=False,
        severity=IncidentSeverity.HIGH,
        event_count=0,
        suppressed=True,
        classification="user_error",
        classification_source="rules",
    )
    trigger_calls: list[dict[str, object]] = []

    async def _fake_trigger(**kwargs):
        trigger_calls.append(kwargs)

    monkeypatch.setattr("workers.outbox_dispatcher.trigger_autonomous_run_for_new_incident", _fake_trigger)

    dispatcher = OutboxDispatcher(repository, service, autonomous_run_service=StubAutonomousRunService())
    processed = await dispatcher.run_once()

    assert processed == 1
    assert repository.processed_ids == ["event-3"]
    assert trigger_calls == []


@pytest.mark.asyncio
async def test_outbox_dispatcher_propagates_human_approval_requirement_to_autonomous_trigger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = StubOutboxRepository(
        [
            {
                "id": "event-4",
                "event_type": "telemetry.received",
                "payload": {"telemetry_id": "telemetry-1"},
            }
        ]
    )
    service = StubIncidentCreationService()
    service.result = IncidentProcessingResult(
        incident_id="incident-7",
        created_new_incident=True,
        attached_telemetry=True,
        severity=IncidentSeverity.MEDIUM,
        event_count=1,
        classification="code_ambiguous",
        classification_source="llm",
        requires_human_approval=True,
    )
    trigger_calls: list[dict[str, object]] = []

    async def _fake_trigger(**kwargs):
        trigger_calls.append(kwargs)

    monkeypatch.setattr("workers.outbox_dispatcher.trigger_autonomous_run_for_new_incident", _fake_trigger)
    autonomous_service = StubAutonomousRunService()

    dispatcher = OutboxDispatcher(repository, service, autonomous_run_service=autonomous_service)
    processed = await dispatcher.run_once()

    assert processed == 1
    assert repository.processed_ids == ["event-4"]
    assert trigger_calls == [
        {
            "incident_id": "incident-7",
            "autonomous_run_service": autonomous_service,
            "processing_result": service.result,
        }
    ]


@pytest.mark.asyncio
async def test_outbox_dispatcher_triggers_for_existing_incident_with_new_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = StubOutboxRepository(
        [
            {
                "id": "event-5",
                "event_type": "telemetry.received",
                "payload": {"telemetry_id": "telemetry-2"},
            }
        ]
    )
    service = StubIncidentCreationService()
    service.result = IncidentProcessingResult(
        incident_id="incident-8",
        created_new_incident=False,
        attached_telemetry=True,
        severity=IncidentSeverity.HIGH,
        event_count=3,
    )
    trigger_calls: list[dict[str, object]] = []

    async def _fake_trigger(**kwargs):
        trigger_calls.append(kwargs)

    monkeypatch.setattr("workers.outbox_dispatcher.trigger_autonomous_run_for_new_incident", _fake_trigger)
    autonomous_service = StubAutonomousRunService()

    dispatcher = OutboxDispatcher(repository, service, autonomous_run_service=autonomous_service)
    processed = await dispatcher.run_once()

    assert processed == 1
    assert repository.processed_ids == ["event-5"]
    assert trigger_calls == [
        {
            "incident_id": "incident-8",
            "autonomous_run_service": autonomous_service,
            "processing_result": service.result,
        }
    ]


@pytest.mark.asyncio
async def test_autonomous_trigger_skips_when_latest_run_is_active() -> None:
    service = StubAutonomousRunService(
        runs=[
            SimpleNamespace(
                id="run-1",
                status=AutonomousRunStatus.RUNNING,
                approval_status=AutonomousApprovalStatus.APPROVED,
            )
        ]
    )

    await trigger_autonomous_run_for_new_incident(
        incident_id="incident-9",
        autonomous_run_service=service,
        processing_result=IncidentProcessingResult(
            incident_id="incident-9",
            created_new_incident=False,
            attached_telemetry=True,
            severity=IncidentSeverity.HIGH,
            event_count=2,
        ),
    )

    assert service.start_calls == []
