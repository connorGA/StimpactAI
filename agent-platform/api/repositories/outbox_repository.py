from __future__ import annotations

from typing import Any

import asyncpg

from api.core.errors import PersistenceError

RECLAIM_STALE_OUTBOX_EVENTS_SQL = """
UPDATE outbox_events
SET status = 'pending',
    locked_at = NULL,
    available_at = NOW(),
    last_error = COALESCE(last_error, 'Recovered after stale outbox lease expired.')
WHERE status = 'processing'
  AND locked_at IS NOT NULL
  AND locked_at <= NOW() - ($1 * INTERVAL '1 second')
RETURNING
    id,
    aggregate_type,
    aggregate_id,
    event_type,
    payload,
    status,
    attempts,
    available_at,
    locked_at,
    processed_at,
    last_error,
    created_at;
"""

LEASE_OUTBOX_EVENTS_SQL = """
WITH candidates AS (
    SELECT id
    FROM outbox_events
    WHERE status = 'pending'
      AND available_at <= NOW()
    ORDER BY created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT $1
)
UPDATE outbox_events AS outbox
SET status = 'processing',
    locked_at = NOW(),
    attempts = outbox.attempts + 1
FROM candidates
WHERE outbox.id = candidates.id
RETURNING
    outbox.id,
    outbox.aggregate_type,
    outbox.aggregate_id,
    outbox.event_type,
    outbox.payload,
    outbox.status,
    outbox.attempts,
    outbox.available_at,
    outbox.locked_at,
    outbox.processed_at,
    outbox.last_error,
    outbox.created_at;
"""

MARK_OUTBOX_EVENT_PROCESSED_SQL = """
UPDATE outbox_events
SET status = 'processed',
    processed_at = NOW(),
    locked_at = NULL,
    last_error = NULL
WHERE id = $1;
"""

MARK_OUTBOX_EVENT_FAILED_SQL = """
UPDATE outbox_events
SET status = 'pending',
    locked_at = NULL,
    available_at = NOW() + ($2 * INTERVAL '1 second'),
    last_error = $3
WHERE id = $1;
"""


class OutboxRepository:
    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self._pool = pool

    async def lease_pending_events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for outbox processing.")

        try:
            async with self._pool.acquire() as connection:
                rows = await connection.fetch(LEASE_OUTBOX_EVENTS_SQL, limit)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to lease outbox events.") from exc

        return [dict(row) for row in rows]

    async def reclaim_stale_events(self, *, stale_after_seconds: int = 300) -> list[dict[str, Any]]:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for outbox processing.")
        try:
            async with self._pool.acquire() as connection:
                rows = await connection.fetch(RECLAIM_STALE_OUTBOX_EVENTS_SQL, stale_after_seconds)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to reclaim stale outbox events.") from exc
        return [dict(row) for row in rows]

    async def mark_processed(self, event_id: str) -> None:
        await self._execute_status_update(MARK_OUTBOX_EVENT_PROCESSED_SQL, event_id)

    async def mark_failed(self, event_id: str, *, retry_delay_seconds: int, error_message: str) -> None:
        await self._execute_status_update(
            MARK_OUTBOX_EVENT_FAILED_SQL,
            event_id,
            retry_delay_seconds,
            error_message[:1000],
        )

    async def _execute_status_update(self, query: str, *params: object) -> None:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for outbox processing.")

        try:
            async with self._pool.acquire() as connection:
                await connection.execute(query, *params)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to update outbox event status.") from exc
