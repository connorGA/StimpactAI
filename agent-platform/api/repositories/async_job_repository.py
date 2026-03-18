from __future__ import annotations

import json
from uuid import uuid4

import asyncpg

from api.core.errors import PersistenceError
from models.async_job import AsyncJobRecord, AsyncJobStatus, AsyncJobType, JobAttemptRecord

INSERT_ASYNC_JOB_SQL = """
INSERT INTO async_jobs (
    id, job_type, status, dedupe_key, payload, available_at
) VALUES (
    $1, $2, $3, $4, $5::jsonb, NOW()
)
RETURNING *;
"""

LEASE_ASYNC_JOBS_SQL = """
WITH candidates AS (
    SELECT id
    FROM async_jobs
    WHERE status = 'queued'
      AND available_at <= NOW()
      AND ($3::text IS NULL OR job_type = $3)
    ORDER BY created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT $1
)
UPDATE async_jobs AS jobs
SET status = 'running',
    attempts = jobs.attempts + 1,
    lease_expires_at = NOW() + ($2 * INTERVAL '1 second'),
    updated_at = NOW()
FROM candidates
WHERE jobs.id = candidates.id
RETURNING jobs.*;
"""

MARK_ASYNC_JOB_STATUS_SQL = """
UPDATE async_jobs
SET status = $2,
    last_error = $3,
    lease_expires_at = NULL,
    updated_at = NOW()
WHERE id = $1
RETURNING *;
"""

GET_ASYNC_JOB_SQL = """
SELECT *
FROM async_jobs
WHERE id = $1
LIMIT 1;
"""

INSERT_JOB_ATTEMPT_SQL = """
INSERT INTO job_attempts (
    id, async_job_id, worker_id, status, error_message, started_at, finished_at
) VALUES (
    $1, $2, $3, $4, $5, NOW(), CASE WHEN $6 THEN NOW() ELSE NULL END
)
RETURNING *;
"""


class AsyncJobRepository:
    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self._pool = pool

    async def create_job(
        self,
        *,
        job_type: AsyncJobType,
        payload: dict[str, object],
        dedupe_key: str | None = None,
        status: AsyncJobStatus = AsyncJobStatus.QUEUED,
    ) -> AsyncJobRecord:
        row = await self._fetchrow(
            INSERT_ASYNC_JOB_SQL,
            str(uuid4()),
            job_type.value,
            status.value,
            dedupe_key,
            json.dumps(payload),
        )
        return AsyncJobRecord.from_db_row(row)

    async def lease_jobs(
        self,
        *,
        limit: int = 10,
        lease_seconds: int = 300,
        job_type: AsyncJobType | None = None,
    ) -> list[AsyncJobRecord]:
        rows = await self._fetch(
            LEASE_ASYNC_JOBS_SQL,
            limit,
            lease_seconds,
            job_type.value if job_type is not None else None,
        )
        return [AsyncJobRecord.from_db_row(row) for row in rows]

    async def mark_job_status(
        self,
        job_id: str,
        *,
        status: AsyncJobStatus,
        last_error: str | None = None,
    ) -> AsyncJobRecord:
        row = await self._fetchrow(
            MARK_ASYNC_JOB_STATUS_SQL,
            job_id,
            status.value,
            last_error,
        )
        return AsyncJobRecord.from_db_row(row)

    async def get_job(self, job_id: str) -> AsyncJobRecord | None:
        row = await self._fetchrow(GET_ASYNC_JOB_SQL, job_id, allow_missing=True)
        if row is None:
            return None
        return AsyncJobRecord.from_db_row(row)

    async def create_job_attempt(
        self,
        *,
        async_job_id: str,
        worker_id: str,
        status: AsyncJobStatus,
        error_message: str | None = None,
        finished: bool = False,
    ) -> JobAttemptRecord:
        row = await self._fetchrow(
            INSERT_JOB_ATTEMPT_SQL,
            str(uuid4()),
            async_job_id,
            worker_id,
            status.value,
            error_message,
            finished,
        )
        return JobAttemptRecord.from_db_row(row)

    async def _fetchrow(self, query: str, *params: object, allow_missing: bool = False):
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for async job operations.")
        try:
            async with self._pool.acquire() as connection:
                row = await connection.fetchrow(query, *params)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to execute an async job query.") from exc
        if row is None and not allow_missing:
            raise PersistenceError("Async job query returned no row.")
        return row

    async def _fetch(self, query: str, *params: object):
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for async job operations.")
        try:
            async with self._pool.acquire() as connection:
                return await connection.fetch(query, *params)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to execute an async job query.") from exc
