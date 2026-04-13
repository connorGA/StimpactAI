from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from api.core.config import get_outbox_stale_lock_seconds
from api.events.redis_bus import OutboxSignalBus
from api.repositories.outbox_repository import OutboxRepository
from services.incident_creation import IncidentCreationService

if TYPE_CHECKING:
    from services.autonomous_runs import AutonomousRunService

logger = logging.getLogger(__name__)


class OutboxDispatcher:
    def __init__(
        self,
        repository: OutboxRepository,
        incident_creation_service: IncidentCreationService,
        signal_bus: OutboxSignalBus | None = None,
        autonomous_run_service: AutonomousRunService | None = None,
    ) -> None:
        self._repository = repository
        self._incident_creation_service = incident_creation_service
        self._signal_bus = signal_bus
        self._autonomous_run_service = autonomous_run_service
        self._last_signal_id = "$"

    async def run_once(self, *, batch_size: int = 100) -> int:
        await self._repository.reclaim_stale_events(stale_after_seconds=get_outbox_stale_lock_seconds())
        events = await self._repository.lease_pending_events(limit=batch_size)

        for event in events:
            event_id = str(event["id"])
            event_type = str(event["event_type"])

            try:
                await self._dispatch(event)
                await self._repository.mark_processed(event_id)
            except Exception as exc:
                logger.exception("Outbox dispatch failed", extra={"event_id": event_id, "event_type": event_type})
                await self._repository.mark_failed(
                    event_id,
                    retry_delay_seconds=30,
                    error_message=str(exc),
                )

        return len(events)

    async def run_once_or_wait(self, *, batch_size: int = 100) -> int:
        processed = await self.run_once(batch_size=batch_size)
        if processed > 0 or self._signal_bus is None:
            return processed

        signals = await self._signal_bus.wait_for_signal(last_id=self._last_signal_id)
        if signals:
            self._last_signal_id = signals[-1]["stream_id"]

        return await self.run_once(batch_size=batch_size)

    async def _dispatch(self, event: dict[str, object]) -> None:
        event_type = str(event["event_type"])
        payload = _coerce_payload(event["payload"])

        if event_type == "telemetry.received":
            result = await self._incident_creation_service.process_telemetry_received(payload)
            logger.info(
                "Telemetry incident processed",
                extra={
                    "event_id": str(event["id"]),
                    "incident_id": result.incident_id,
                    "created_new_incident": result.created_new_incident,
                    "attached_telemetry": result.attached_telemetry,
                },
            )
            if result.created_new_incident and self._autonomous_run_service is not None:
                await self._trigger_autonomous_run(result.incident_id)
            return

        logger.warning("Ignoring unsupported outbox event", extra={"event_type": event_type})

    async def _trigger_autonomous_run(self, incident_id: str) -> None:
        from api.schemas.autonomous import AutonomousRunCreateRequest
        from harness.schemas.autonomous import AutonomousExecutionMode

        try:
            request = AutonomousRunCreateRequest(
                execution_mode=AutonomousExecutionMode.REPAIR_AND_PROPOSE,
            )
            detail = await self._autonomous_run_service.start_run(incident_id, request)
            logger.info(
                "Autonomous repair run queued for new incident",
                extra={
                    "incident_id": incident_id,
                    "run_id": detail.run.id,
                    "async_job_id": detail.run.async_job_id,
                },
            )
        except Exception:
            logger.exception(
                "Failed to trigger autonomous run for new incident",
                extra={"incident_id": incident_id},
            )


def _coerce_payload(payload: object) -> dict[str, Any]:
    if isinstance(payload, dict):
        return {str(key): value for key, value in payload.items()}

    if isinstance(payload, str):
        decoded = json.loads(payload)
        if isinstance(decoded, dict):
            return {str(key): value for key, value in decoded.items()}

    raise ValueError("Outbox payload must be a JSON object.")
