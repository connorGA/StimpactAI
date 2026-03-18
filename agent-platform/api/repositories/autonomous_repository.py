from __future__ import annotations

import json
from uuid import uuid4

import asyncpg

from api.core.errors import PersistenceError
from harness.schemas.autonomous import AutonomousRepairRunRecord, AutonomousRunOutcome
from harness.schemas.initializer import FeatureSeed
from models.autonomous import AutonomousRunPersistenceRecord

INSERT_AUTONOMOUS_RUN_SQL = """
INSERT INTO autonomous_runs (
    id,
    incident_id,
    repo_profile_id,
    async_job_id,
    feature_seeds,
    initializer_summary,
    max_steps,
    run_snapshot,
    outcome_snapshot
) VALUES (
    $1, $2, $3, $4, $5::jsonb, $6, $7, $8::jsonb, $9::jsonb
)
RETURNING *;
"""

UPDATE_AUTONOMOUS_RUN_SQL = """
UPDATE autonomous_runs
SET async_job_id = COALESCE($2, async_job_id),
    repo_profile_id = COALESCE($3, repo_profile_id),
    run_snapshot = $4::jsonb,
    outcome_snapshot = $5::jsonb,
    updated_at = NOW()
WHERE id = $1
RETURNING *;
"""

GET_AUTONOMOUS_RUN_SQL = """
SELECT *
FROM autonomous_runs
WHERE id = $1
LIMIT 1;
"""

LIST_AUTONOMOUS_RUNS_SQL = """
SELECT *
FROM autonomous_runs
WHERE incident_id = $1
ORDER BY created_at DESC;
"""

LIST_AUTONOMOUS_RUNS_BY_JOB_SQL = """
SELECT *
FROM autonomous_runs
WHERE async_job_id = $1
ORDER BY created_at DESC;
"""

LIST_AUTONOMOUS_RUNS_BY_PATCH_RUN_SQL = """
SELECT *
FROM autonomous_runs
WHERE (run_snapshot ->> 'patch_run_id') = $1
ORDER BY created_at DESC;
"""

INSERT_AUTONOMOUS_RUN_ATTEMPT_SQL = """
INSERT INTO autonomous_run_attempts (
    id,
    autonomous_run_id,
    async_job_id,
    attempt_number,
    status,
    error_message,
    started_at,
    finished_at
) VALUES (
    $1, $2, $3, $4, $5, $6, NOW(), CASE WHEN $7 THEN NOW() ELSE NULL END
);
"""


class AutonomousRunRepository:
    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self._pool = pool

    async def create_run(
        self,
        *,
        incident_id: str,
        repo_profile_id: str | None,
        async_job_id: str | None,
        feature_seeds: list[FeatureSeed],
        initializer_summary: str,
        max_steps: int,
        run: AutonomousRepairRunRecord,
        outcome: AutonomousRunOutcome | None = None,
    ) -> AutonomousRunPersistenceRecord:
        row = await self._fetchrow(
            INSERT_AUTONOMOUS_RUN_SQL,
            run.id,
            incident_id,
            repo_profile_id,
            async_job_id,
            json.dumps([seed.model_dump(mode="json") for seed in feature_seeds]),
            initializer_summary,
            max_steps,
            json.dumps(run.model_dump(mode="json")),
            json.dumps(outcome.model_dump(mode="json")) if outcome is not None else None,
        )
        return AutonomousRunPersistenceRecord.from_db_row(row)

    async def update_run(
        self,
        run_id: str,
        *,
        async_job_id: str | None,
        repo_profile_id: str | None,
        run: AutonomousRepairRunRecord,
        outcome: AutonomousRunOutcome | None = None,
    ) -> AutonomousRunPersistenceRecord:
        row = await self._fetchrow(
            UPDATE_AUTONOMOUS_RUN_SQL,
            run_id,
            async_job_id,
            repo_profile_id,
            json.dumps(run.model_dump(mode="json")),
            json.dumps(outcome.model_dump(mode="json")) if outcome is not None else None,
        )
        return AutonomousRunPersistenceRecord.from_db_row(row)

    async def get_run(self, run_id: str) -> AutonomousRunPersistenceRecord | None:
        row = await self._fetchrow(GET_AUTONOMOUS_RUN_SQL, run_id, allow_missing=True)
        if row is None:
            return None
        return AutonomousRunPersistenceRecord.from_db_row(row)

    async def list_runs(self, incident_id: str) -> list[AutonomousRunPersistenceRecord]:
        rows = await self._fetch(LIST_AUTONOMOUS_RUNS_SQL, incident_id)
        return [AutonomousRunPersistenceRecord.from_db_row(row) for row in rows]

    async def find_runs_by_job(self, async_job_id: str) -> list[AutonomousRunPersistenceRecord]:
        rows = await self._fetch(LIST_AUTONOMOUS_RUNS_BY_JOB_SQL, async_job_id)
        return [AutonomousRunPersistenceRecord.from_db_row(row) for row in rows]

    async def find_runs_by_patch_run(self, patch_run_id: str) -> list[AutonomousRunPersistenceRecord]:
        rows = await self._fetch(LIST_AUTONOMOUS_RUNS_BY_PATCH_RUN_SQL, patch_run_id)
        return [AutonomousRunPersistenceRecord.from_db_row(row) for row in rows]

    async def create_attempt(
        self,
        *,
        autonomous_run_id: str,
        async_job_id: str | None,
        attempt_number: int,
        status: str,
        error_message: str | None,
        finished: bool,
    ) -> None:
        await self._execute(
            INSERT_AUTONOMOUS_RUN_ATTEMPT_SQL,
            str(uuid4()),
            autonomous_run_id,
            async_job_id,
            attempt_number,
            status,
            error_message,
            finished,
        )

    async def _fetchrow(self, query: str, *params: object, allow_missing: bool = False):
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for autonomous runs.")
        try:
            async with self._pool.acquire() as connection:
                row = await connection.fetchrow(query, *params)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to execute an autonomous run query.") from exc
        if row is None and not allow_missing:
            raise PersistenceError("Autonomous run query returned no row.")
        return row

    async def _fetch(self, query: str, *params: object):
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for autonomous runs.")
        try:
            async with self._pool.acquire() as connection:
                return await connection.fetch(query, *params)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to execute an autonomous run query.") from exc

    async def _execute(self, query: str, *params: object) -> None:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for autonomous runs.")
        try:
            async with self._pool.acquire() as connection:
                await connection.execute(query, *params)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to execute an autonomous run write.") from exc
