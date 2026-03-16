from __future__ import annotations

from models.incident import IncidentProcessingResult, IncidentSeverity
from workers.outbox_dispatcher import OutboxDispatcher


class StubOutboxRepository:
    def __init__(self, events: list[dict[str, object]]) -> None:
        self.events = events
        self.processed_ids: list[str] = []
        self.failed_calls: list[tuple[str, int, str]] = []

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

    async def process_telemetry_received(self, payload: dict[str, object]) -> IncidentProcessingResult:
        self.payloads.append(payload)
        return IncidentProcessingResult(
            incident_id="incident-1",
            created_new_incident=True,
            attached_telemetry=True,
            severity=IncidentSeverity.CRITICAL,
            event_count=1,
        )


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
