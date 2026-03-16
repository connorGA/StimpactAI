from __future__ import annotations

import json
from uuid import uuid4

import asyncpg

from api.core.errors import PersistenceError
from models.incident import (
    IncidentEventRecord,
    IncidentProcessingResult,
    IncidentRecord,
    IncidentSeverity,
    TelemetryRecord,
)

SELECT_TELEMETRY_SQL = """
SELECT
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
FROM telemetry_events
WHERE id = $1
LIMIT 1;
"""

SELECT_INCIDENT_BY_TELEMETRY_SQL = """
SELECT incidents.*
FROM incident_events
JOIN incidents ON incidents.id = incident_events.incident_id
WHERE incident_events.telemetry_id = $1
LIMIT 1;
"""

SELECT_OPEN_INCIDENT_FOR_UPDATE_SQL = """
SELECT *
FROM incidents
WHERE project_id = $1
  AND fingerprint = $2
  AND status = 'open'
ORDER BY created_at ASC
FOR UPDATE
LIMIT 1;
"""

INSERT_INCIDENT_SQL = """
INSERT INTO incidents (
    id,
    project_id,
    fingerprint,
    service,
    environment,
    title,
    status,
    severity,
    first_seen_at,
    last_seen_at,
    event_count,
    latest_telemetry_id
) VALUES (
    $1, $2, $3, $4, $5, $6, 'open', $7, $8, $9, 1, $10
)
RETURNING *;
"""

UPDATE_INCIDENT_SQL = """
UPDATE incidents
SET last_seen_at = GREATEST(last_seen_at, $2),
    event_count = event_count + 1,
    latest_telemetry_id = $3,
    severity = $4,
    updated_at = NOW()
WHERE id = $1
RETURNING *;
"""

INSERT_INCIDENT_EVENT_SQL = """
INSERT INTO incident_events (
    id,
    incident_id,
    telemetry_id,
    event_type,
    error_message,
    stacktrace,
    request_payload,
    response_payload,
    payload,
    occurred_at
) VALUES (
    $1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9::jsonb, $10
)
ON CONFLICT (telemetry_id) DO NOTHING
RETURNING id;
"""

LIST_INCIDENTS_SQL = """
SELECT *
FROM incidents
WHERE ($1::text IS NULL OR project_id = $1)
  AND ($2::text IS NULL OR status = $2)
ORDER BY last_seen_at DESC, created_at DESC
LIMIT $3
OFFSET $4;
"""

COUNT_INCIDENTS_SQL = """
SELECT COUNT(*) AS total
FROM incidents
WHERE ($1::text IS NULL OR project_id = $1)
  AND ($2::text IS NULL OR status = $2);
"""

GET_INCIDENT_BY_ID_SQL = """
SELECT *
FROM incidents
WHERE id = $1
LIMIT 1;
"""

LIST_INCIDENT_EVENTS_SQL = """
SELECT
    id,
    incident_id,
    telemetry_id,
    event_type,
    error_message,
    stacktrace,
    request_payload,
    response_payload,
    payload,
    occurred_at,
    created_at
FROM incident_events
WHERE incident_id = $1
ORDER BY occurred_at DESC, created_at DESC
LIMIT $2;
"""


class IncidentRepository:
    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self._pool = pool

    async def get_telemetry(self, telemetry_id: str) -> TelemetryRecord:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for incident creation.")

        try:
            async with self._pool.acquire() as connection:
                row = await connection.fetchrow(SELECT_TELEMETRY_SQL, telemetry_id)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to read telemetry for incident creation.") from exc

        if row is None:
            raise PersistenceError(f"Telemetry event {telemetry_id} was not found.")

        return TelemetryRecord.from_db_row(row)

    async def list_incidents(
        self,
        *,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[IncidentRecord], int]:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for incident reads.")

        try:
            async with self._pool.acquire() as connection:
                rows = await connection.fetch(
                    LIST_INCIDENTS_SQL,
                    project_id,
                    status,
                    limit,
                    offset,
                )
                total_row = await connection.fetchrow(
                    COUNT_INCIDENTS_SQL,
                    project_id,
                    status,
                )
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to list incidents.") from exc

        total = int(total_row["total"]) if total_row is not None else 0
        return [IncidentRecord.from_db_row(row) for row in rows], total

    async def get_incident(self, incident_id: str) -> IncidentRecord | None:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for incident reads.")

        try:
            async with self._pool.acquire() as connection:
                row = await connection.fetchrow(GET_INCIDENT_BY_ID_SQL, incident_id)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to fetch incident.") from exc

        if row is None:
            return None

        return IncidentRecord.from_db_row(row)

    async def list_incident_events(
        self,
        incident_id: str,
        *,
        limit: int = 100,
    ) -> list[IncidentEventRecord]:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for incident reads.")

        try:
            async with self._pool.acquire() as connection:
                rows = await connection.fetch(
                    LIST_INCIDENT_EVENTS_SQL,
                    incident_id,
                    limit,
                )
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to fetch incident events.") from exc

        return [IncidentEventRecord.from_db_row(row) for row in rows]

    async def attach_to_incident(
        self,
        *,
        telemetry: TelemetryRecord,
        event_type: str,
        event_payload: dict[str, object],
        severity: IncidentSeverity,
        title: str,
    ) -> IncidentProcessingResult:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for incident creation.")

        request_payload = telemetry.request_payload
        response_payload = telemetry.response_payload

        try:
            async with self._pool.acquire() as connection:
                async with connection.transaction():
                    existing_incident_row = await connection.fetchrow(
                        SELECT_INCIDENT_BY_TELEMETRY_SQL,
                        telemetry.id,
                    )
                    if existing_incident_row is not None:
                        incident = IncidentRecord.from_db_row(existing_incident_row)
                        return IncidentProcessingResult(
                            incident_id=incident.id,
                            created_new_incident=False,
                            attached_telemetry=False,
                            severity=incident.severity,
                            event_count=incident.event_count,
                        )

                    incident_row = await connection.fetchrow(
                        SELECT_OPEN_INCIDENT_FOR_UPDATE_SQL,
                        telemetry.project_id,
                        telemetry.fingerprint,
                    )
                    created_new_incident = False

                    if incident_row is None:
                        try:
                            incident_row = await connection.fetchrow(
                                INSERT_INCIDENT_SQL,
                                str(uuid4()),
                                telemetry.project_id,
                                telemetry.fingerprint,
                                telemetry.service,
                                telemetry.environment.value,
                                title,
                                severity.value,
                                telemetry.occurred_at,
                                telemetry.occurred_at,
                                telemetry.id,
                            )
                            created_new_incident = True
                        except asyncpg.UniqueViolationError:
                            incident_row = await connection.fetchrow(
                                SELECT_OPEN_INCIDENT_FOR_UPDATE_SQL,
                                telemetry.project_id,
                                telemetry.fingerprint,
                            )

                    if incident_row is None:
                        raise PersistenceError("Failed to load or create the target incident.")

                    incident = IncidentRecord.from_db_row(incident_row)
                    merged_severity = _max_severity(incident.severity, severity)

                    if created_new_incident:
                        updated_incident = incident
                    else:
                        updated_incident_row = await connection.fetchrow(
                            UPDATE_INCIDENT_SQL,
                            incident.id,
                            telemetry.occurred_at,
                            telemetry.id,
                            merged_severity.value,
                        )
                        if updated_incident_row is None:
                            raise PersistenceError(f"Failed to update incident {incident.id}.")
                        updated_incident = IncidentRecord.from_db_row(updated_incident_row)

                    incident_event_insert = await connection.fetchrow(
                        INSERT_INCIDENT_EVENT_SQL,
                        str(uuid4()),
                        updated_incident.id,
                        telemetry.id,
                        event_type,
                        telemetry.error_message,
                        telemetry.stacktrace,
                        json.dumps(request_payload) if request_payload is not None else None,
                        json.dumps(response_payload) if response_payload is not None else None,
                        json.dumps(event_payload),
                        telemetry.occurred_at,
                    )

                    attached_telemetry = incident_event_insert is not None
                    if not attached_telemetry:
                        return IncidentProcessingResult(
                            incident_id=updated_incident.id,
                            created_new_incident=created_new_incident,
                            attached_telemetry=False,
                            severity=updated_incident.severity,
                            event_count=updated_incident.event_count,
                        )

                    return IncidentProcessingResult(
                        incident_id=updated_incident.id,
                        created_new_incident=created_new_incident,
                        attached_telemetry=True,
                        severity=updated_incident.severity,
                        event_count=updated_incident.event_count,
                    )
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to attach telemetry to an incident.") from exc


def _max_severity(current: IncidentSeverity, candidate: IncidentSeverity) -> IncidentSeverity:
    order = {
        IncidentSeverity.LOW: 0,
        IncidentSeverity.MEDIUM: 1,
        IncidentSeverity.HIGH: 2,
        IncidentSeverity.CRITICAL: 3,
    }
    return current if order[current] >= order[candidate] else candidate
