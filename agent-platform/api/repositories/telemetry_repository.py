from __future__ import annotations

import json
from uuid import uuid4

import asyncpg

from api.core.errors import PersistenceError
from models.normalized_telemetry import NormalizedTelemetry
from shared.events.incident_events import IncidentEvent

INSERT_TELEMETRY_EVENT_SQL = """
INSERT INTO telemetry_events (
    id,
    project_id,
    environment,
    service,
    error_message,
    stacktrace,
    fingerprint,
    request_payload,
    response_payload,
    commit_sha,
    occurred_at,
    received_at
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10, $11, $12
);
"""

INSERT_OUTBOX_EVENT_SQL = """
INSERT INTO outbox_events (
    id,
    aggregate_type,
    aggregate_id,
    event_type,
    payload
) VALUES (
    $1, $2, $3, $4, $5::jsonb
);
"""


class PostgresTelemetryRepository:
    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self._pool = pool

    async def insert_event_with_outbox(
        self,
        telemetry: NormalizedTelemetry,
        incident_event: IncidentEvent,
    ) -> str:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for telemetry ingestion.")

        request_payload = telemetry.request.model_dump(mode="json") if telemetry.request else None
        response_payload = telemetry.response.model_dump(mode="json") if telemetry.response else None

        try:
            async with self._pool.acquire() as connection:
                async with connection.transaction():
                    await connection.execute(
                        INSERT_TELEMETRY_EVENT_SQL,
                        telemetry.id,
                        telemetry.project_id,
                        telemetry.environment.value,
                        telemetry.service,
                        telemetry.error_message,
                        telemetry.stacktrace,
                        telemetry.fingerprint,
                        json.dumps(request_payload) if request_payload is not None else None,
                        json.dumps(response_payload) if response_payload is not None else None,
                        telemetry.commit_sha,
                        telemetry.occurred_at,
                        telemetry.received_at,
                    )
                    await connection.execute(
                        INSERT_OUTBOX_EVENT_SQL,
                        outbox_event_id := str(uuid4()),
                        "telemetry_event",
                        telemetry.id,
                        incident_event.event_type.value,
                        json.dumps(incident_event.model_dump(mode="json")),
                    )
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to persist telemetry event and outbox message.") from exc

        return outbox_event_id
