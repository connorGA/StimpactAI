from __future__ import annotations

from uuid import uuid4

import asyncpg

from api.core.errors import PersistenceError
from models.sandbox import (
    SandboxRunAttemptRecord,
    SandboxRunRecord,
    SandboxRunStatus,
    SandboxRunStepRecord,
)

GET_LATEST_SANDBOX_RUN_SQL = """
SELECT *
FROM sandbox_runs
WHERE incident_id = $1
ORDER BY created_at DESC
LIMIT 1;
"""

GET_SANDBOX_RUN_SQL = """
SELECT *
FROM sandbox_runs
WHERE id = $1
LIMIT 1;
"""

LIST_SANDBOX_RUNS_SQL = """
SELECT *
FROM sandbox_runs
WHERE incident_id = $1
ORDER BY created_at DESC
LIMIT $2;
"""

LIST_ACTIVE_KUBERNETES_SANDBOX_RUNS_SQL = """
SELECT *
FROM sandbox_runs
WHERE status = 'running'
  AND executor_backend = 'kubernetes'
  AND external_job_id IS NOT NULL
ORDER BY created_at ASC
LIMIT $1;
"""

INSERT_SANDBOX_RUN_SQL = """
INSERT INTO sandbox_runs (
    id,
    incident_id,
    patch_run_id,
    repo_profile_id,
    async_job_id,
    status,
    executor_backend,
    external_job_id,
    install_command,
    reproduce_command,
    verify_command,
    reproduction_succeeded,
    patch_applied,
    verification_succeeded,
    summary,
    execution_log
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16
)
RETURNING *;
"""

UPDATE_SANDBOX_RUN_SQL = """
UPDATE sandbox_runs
SET status = COALESCE($2, status),
    external_job_id = COALESCE($3, external_job_id),
    reproduction_succeeded = COALESCE($4, reproduction_succeeded),
    patch_applied = COALESCE($5, patch_applied),
    verification_succeeded = COALESCE($6, verification_succeeded),
    summary = COALESCE($7, summary),
    execution_log = COALESCE($8, execution_log),
    updated_at = NOW()
WHERE id = $1
RETURNING *;
"""

INSERT_SANDBOX_RUN_STEP_SQL = """
INSERT INTO sandbox_run_steps (
    id,
    sandbox_run_id,
    step_name,
    status,
    command,
    summary,
    artifact_id,
    exit_code,
    started_at,
    finished_at
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, NOW(), CASE WHEN $9 THEN NOW() ELSE NULL END
)
RETURNING *;
"""

LIST_SANDBOX_RUN_STEPS_SQL = """
SELECT *
FROM sandbox_run_steps
WHERE sandbox_run_id = $1
ORDER BY created_at ASC;
"""

INSERT_SANDBOX_RUN_ATTEMPT_SQL = """
INSERT INTO sandbox_run_attempts (
    id,
    sandbox_run_id,
    async_job_id,
    attempt_number,
    status,
    error_message,
    started_at,
    finished_at
) VALUES (
    $1, $2, $3, $4, $5, $6, NOW(), CASE WHEN $7 THEN NOW() ELSE NULL END
)
RETURNING *;
"""

LIST_SANDBOX_RUN_ATTEMPTS_SQL = """
SELECT *
FROM sandbox_run_attempts
WHERE sandbox_run_id = $1
ORDER BY attempt_number ASC, started_at ASC;
"""


class SandboxRepository:
    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self._pool = pool

    async def get_latest_sandbox_run(self, incident_id: str) -> SandboxRunRecord | None:
        row = await self._fetchrow(GET_LATEST_SANDBOX_RUN_SQL, incident_id, allow_missing=True)
        if row is None:
            return None
        return SandboxRunRecord.from_db_row(row)

    async def get_sandbox_run(self, sandbox_run_id: str) -> SandboxRunRecord | None:
        row = await self._fetchrow(GET_SANDBOX_RUN_SQL, sandbox_run_id, allow_missing=True)
        if row is None:
            return None
        return SandboxRunRecord.from_db_row(row)

    async def list_sandbox_runs(self, incident_id: str, *, limit: int = 20) -> list[SandboxRunRecord]:
        rows = await self._fetch(LIST_SANDBOX_RUNS_SQL, incident_id, limit)
        return [SandboxRunRecord.from_db_row(row) for row in rows]

    async def list_active_kubernetes_runs(self, *, limit: int = 50) -> list[SandboxRunRecord]:
        rows = await self._fetch(LIST_ACTIVE_KUBERNETES_SANDBOX_RUNS_SQL, limit)
        return [SandboxRunRecord.from_db_row(row) for row in rows]

    async def create_sandbox_run(
        self,
        *,
        incident_id: str,
        patch_run_id: str,
        repo_profile_id: str | None = None,
        async_job_id: str | None = None,
        status: SandboxRunStatus,
        executor_backend: str = "local",
        external_job_id: str | None = None,
        install_command: str | None,
        reproduce_command: str,
        verify_command: str,
        reproduction_succeeded: bool,
        patch_applied: bool,
        verification_succeeded: bool,
        summary: str,
        execution_log: str,
    ) -> SandboxRunRecord:
        row = await self._fetchrow(
            INSERT_SANDBOX_RUN_SQL,
            str(uuid4()),
            incident_id,
            patch_run_id,
            repo_profile_id,
            async_job_id,
            status.value,
            executor_backend,
            external_job_id,
            install_command,
            reproduce_command,
            verify_command,
            reproduction_succeeded,
            patch_applied,
            verification_succeeded,
            summary,
            execution_log,
        )
        return SandboxRunRecord.from_db_row(row)

    async def update_sandbox_run(
        self,
        sandbox_run_id: str,
        *,
        status: SandboxRunStatus | None = None,
        external_job_id: str | None = None,
        reproduction_succeeded: bool | None = None,
        patch_applied: bool | None = None,
        verification_succeeded: bool | None = None,
        summary: str | None = None,
        execution_log: str | None = None,
    ) -> SandboxRunRecord:
        row = await self._fetchrow(
            UPDATE_SANDBOX_RUN_SQL,
            sandbox_run_id,
            status.value if status is not None else None,
            external_job_id,
            reproduction_succeeded,
            patch_applied,
            verification_succeeded,
            summary,
            execution_log,
        )
        return SandboxRunRecord.from_db_row(row)

    async def create_sandbox_run_step(
        self,
        *,
        sandbox_run_id: str,
        step_name: str,
        status: SandboxRunStatus,
        command: str | None,
        summary: str,
        artifact_id: str | None,
        exit_code: int | None,
        finished: bool,
    ) -> SandboxRunStepRecord:
        row = await self._fetchrow(
            INSERT_SANDBOX_RUN_STEP_SQL,
            str(uuid4()),
            sandbox_run_id,
            step_name,
            status.value,
            command,
            summary,
            artifact_id,
            exit_code,
            finished,
        )
        return SandboxRunStepRecord.from_db_row(row)

    async def list_sandbox_run_steps(self, sandbox_run_id: str) -> list[SandboxRunStepRecord]:
        rows = await self._fetch(LIST_SANDBOX_RUN_STEPS_SQL, sandbox_run_id)
        return [SandboxRunStepRecord.from_db_row(row) for row in rows]

    async def create_sandbox_run_attempt(
        self,
        *,
        sandbox_run_id: str,
        async_job_id: str | None,
        attempt_number: int,
        status: SandboxRunStatus,
        error_message: str | None,
        finished: bool,
    ) -> SandboxRunAttemptRecord:
        row = await self._fetchrow(
            INSERT_SANDBOX_RUN_ATTEMPT_SQL,
            str(uuid4()),
            sandbox_run_id,
            async_job_id,
            attempt_number,
            status.value,
            error_message,
            finished,
        )
        return SandboxRunAttemptRecord.from_db_row(row)

    async def list_sandbox_run_attempts(self, sandbox_run_id: str) -> list[SandboxRunAttemptRecord]:
        rows = await self._fetch(LIST_SANDBOX_RUN_ATTEMPTS_SQL, sandbox_run_id)
        return [SandboxRunAttemptRecord.from_db_row(row) for row in rows]

    async def _fetchrow(self, query: str, *params: object, allow_missing: bool = False):
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for sandbox runs.")
        try:
            async with self._pool.acquire() as connection:
                row = await connection.fetchrow(query, *params)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to fetch sandbox run data.") from exc
        if row is None and not allow_missing:
            raise PersistenceError("Sandbox query returned no row.")
        return row

    async def _fetch(self, query: str, *params: object):
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for sandbox runs.")
        try:
            async with self._pool.acquire() as connection:
                return await connection.fetch(query, *params)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to fetch sandbox run data.") from exc
