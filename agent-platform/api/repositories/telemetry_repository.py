from __future__ import annotations

import json
from datetime import datetime
from typing import Any
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
    handled,
    occurred_at,
    received_at
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10, $11, $12, $13
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

UPDATE_TELEMETRY_CLASSIFICATION_SQL = """
UPDATE telemetry_events
   SET classification = $2,
       classification_reason = $3,
       classification_source = $4,
       classified_at = NOW()
 WHERE id = $1;
"""

COUNT_RECENT_BY_FINGERPRINT_SQL = """
SELECT COUNT(*)::BIGINT AS count
  FROM telemetry_events
 WHERE project_id = $1
   AND fingerprint = $2
   AND occurred_at >= $3;
"""

SELECT_SUPPRESSED_TELEMETRY_SQL = """
SELECT
    te.project_id,
    te.fingerprint,
    te.classification,
    te.classification_reason,
    te.classification_source,
    MIN(te.service) AS service,
    MIN(te.error_message) AS error_message,
    MAX(te.occurred_at) AS last_occurred_at,
    MIN(te.occurred_at) AS first_occurred_at,
    COUNT(*)::BIGINT AS occurrence_count,
    MAX(te.classified_at) AS last_classified_at
  FROM telemetry_events te
 WHERE te.project_id = $1
   AND te.classification IN ('user_error', 'code_ambiguous')
 GROUP BY te.project_id, te.fingerprint, te.classification, te.classification_reason, te.classification_source
 ORDER BY last_occurred_at DESC
 LIMIT $2;
"""

SELECT_SUPPRESSED_SUMMARY_SQL = """
SELECT
    classification,
    COUNT(*)::BIGINT AS event_count,
    COUNT(DISTINCT fingerprint)::BIGINT AS unique_fingerprints
  FROM telemetry_events
 WHERE project_id = $1
   AND classification IN ('user_error', 'code_ambiguous')
   AND occurred_at >= $2
 GROUP BY classification;
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
                        telemetry.handled,
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

    async def update_classification(
        self,
        telemetry_id: str,
        *,
        classification: str,
        reason: str | None,
        source: str,
    ) -> None:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for telemetry updates.")
        try:
            async with self._pool.acquire() as connection:
                await connection.execute(
                    UPDATE_TELEMETRY_CLASSIFICATION_SQL,
                    telemetry_id,
                    classification,
                    reason,
                    source,
                )
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to persist telemetry classification.") from exc

    async def count_recent_by_fingerprint(
        self,
        *,
        project_id: str,
        fingerprint: str,
        since: datetime,
    ) -> int:
        if self._pool is None:
            return 0
        try:
            async with self._pool.acquire() as connection:
                row = await connection.fetchrow(
                    COUNT_RECENT_BY_FINGERPRINT_SQL,
                    project_id,
                    fingerprint,
                    since,
                )
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to count telemetry by fingerprint.") from exc
        if row is None:
            return 0
        return int(row["count"])

    async def list_suppressed(
        self,
        *,
        project_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if self._pool is None:
            return []
        try:
            async with self._pool.acquire() as connection:
                rows = await connection.fetch(
                    SELECT_SUPPRESSED_TELEMETRY_SQL,
                    project_id,
                    max(1, min(limit, 200)),
                )
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to load suppressed telemetry.") from exc
        return [dict(row) for row in rows]

    async def suppression_summary(
        self,
        *,
        project_id: str,
        since: datetime,
    ) -> dict[str, dict[str, int]]:
        if self._pool is None:
            return {}
        try:
            async with self._pool.acquire() as connection:
                rows = await connection.fetch(
                    SELECT_SUPPRESSED_SUMMARY_SQL,
                    project_id,
                    since,
                )
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to load suppression summary.") from exc
        return {
            str(row["classification"]): {
                "event_count": int(row["event_count"]),
                "unique_fingerprints": int(row["unique_fingerprints"]),
            }
            for row in rows
        }
