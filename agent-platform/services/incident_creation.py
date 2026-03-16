from __future__ import annotations

from typing import Any

from api.repositories.incident_repository import IncidentRepository
from models.incident import IncidentProcessingResult, IncidentSeverity, TelemetryRecord
from shared.events.incident_events import IncidentEvent
from shared.types.telemetry import Environment


class IncidentCreationService:
    def __init__(self, repository: IncidentRepository) -> None:
        self._repository = repository

    async def process_telemetry_received(self, payload: dict[str, Any]) -> IncidentProcessingResult:
        event = IncidentEvent.model_validate(payload)
        telemetry = await self._repository.get_telemetry(event.telemetry_id)
        severity = determine_incident_severity(telemetry)
        title = build_incident_title(telemetry)

        return await self._repository.attach_to_incident(
            telemetry=telemetry,
            event_type=event.event_type.value,
            event_payload=event.model_dump(mode="json"),
            severity=severity,
            title=title,
        )


def determine_incident_severity(telemetry: TelemetryRecord) -> IncidentSeverity:
    status_code = _extract_response_status_code(telemetry.response_payload)
    request_method = _extract_request_method(telemetry.request_payload)

    if telemetry.environment == Environment.PRODUCTION:
        if status_code is not None and status_code >= 500:
            return IncidentSeverity.CRITICAL
        if request_method in {"POST", "PUT", "PATCH", "DELETE"}:
            return IncidentSeverity.HIGH
        if status_code is not None and status_code >= 400:
            return IncidentSeverity.HIGH
        return IncidentSeverity.MEDIUM

    if telemetry.environment == Environment.STAGING:
        if status_code is not None and status_code >= 500:
            return IncidentSeverity.HIGH
        if status_code is not None and status_code >= 400:
            return IncidentSeverity.MEDIUM
        return IncidentSeverity.LOW

    return IncidentSeverity.LOW


def build_incident_title(telemetry: TelemetryRecord) -> str:
    normalized_message = " ".join(telemetry.error_message.split())
    suffix = normalized_message[:117] + "..." if len(normalized_message) > 120 else normalized_message
    return f"{telemetry.service}: {suffix}"


def _extract_response_status_code(payload: dict[str, Any] | list[Any] | str | None) -> int | None:
    if not isinstance(payload, dict):
        return None

    value = payload.get("status_code")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _extract_request_method(payload: dict[str, Any] | list[Any] | str | None) -> str | None:
    if not isinstance(payload, dict):
        return None

    value = payload.get("method")
    if isinstance(value, str) and value.strip():
        return value.strip().upper()
    return None
