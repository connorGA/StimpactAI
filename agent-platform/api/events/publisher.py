from __future__ import annotations

import logging

from models.normalized_telemetry import NormalizedTelemetry
from shared.events.incident_events import IncidentEvent

logger = logging.getLogger(__name__)


class IncidentEventPublisher:
    def build_telemetry_received(self, telemetry: NormalizedTelemetry) -> IncidentEvent:
        event = IncidentEvent(
            telemetry_id=telemetry.id,
            project_id=telemetry.project_id,
            fingerprint=telemetry.fingerprint,
            payload={
                "environment": telemetry.environment.value,
                "service": telemetry.service,
                "error_message": telemetry.error_message,
                "release": telemetry.release,
                "dist": telemetry.dist,
                "session_id": telemetry.session_id,
                "user": telemetry.user.model_dump(mode="json") if telemetry.user else None,
                "tags": telemetry.tags,
                "contexts": telemetry.contexts,
                "breadcrumbs": [item.model_dump(mode="json") for item in telemetry.breadcrumbs],
                "occurred_at": telemetry.occurred_at.isoformat(),
            },
        )

        logger.info(
            "Prepared telemetry incident event",
            extra={
                "telemetry_id": telemetry.id,
                "project_id": telemetry.project_id,
                "fingerprint": telemetry.fingerprint,
            },
        )

        # TODO: Have the outbox worker consume this event and invoke incident correlation in Task 2.
        # TODO: Add an external broker fan-out only if additional consumers require it later.

        return event


def get_incident_event_publisher() -> IncidentEventPublisher:
    return IncidentEventPublisher()
