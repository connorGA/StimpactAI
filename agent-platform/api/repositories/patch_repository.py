from __future__ import annotations

import json
from uuid import uuid4

import asyncpg

from api.core.errors import PersistenceError
from models.patch import PatchProposal, PatchRunRecord, PatchRunStatus

GET_LATEST_PATCH_RUN_SQL = """
SELECT *
FROM patch_runs
WHERE incident_id = $1
ORDER BY created_at DESC
LIMIT 1;
"""

INSERT_PATCH_RUN_SQL = """
INSERT INTO patch_runs (
    id,
    incident_id,
    status,
    patch_summary,
    rationale,
    target_files,
    unified_diff,
    verification_steps,
    confidence,
    model_name,
    based_on_commit_sha,
    diff_line_count,
    file_count
) VALUES (
    $1, $2, $3, $4, $5, $6::jsonb, $7, $8::jsonb, $9, $10, $11, $12, $13
)
RETURNING *;
"""


class PatchRepository:
    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self._pool = pool

    async def get_latest_patch_run(self, incident_id: str) -> PatchRunRecord | None:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for patch runs.")

        try:
            async with self._pool.acquire() as connection:
                row = await connection.fetchrow(GET_LATEST_PATCH_RUN_SQL, incident_id)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to fetch the latest patch run.") from exc

        if row is None:
            return None
        return PatchRunRecord.from_db_row(row)

    async def create_patch_run(
        self,
        *,
        incident_id: str,
        proposal: PatchProposal,
        model_name: str,
        based_on_commit_sha: str | None,
        diff_line_count: int,
        file_count: int,
        status: PatchRunStatus = PatchRunStatus.GENERATED,
    ) -> PatchRunRecord:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for patch runs.")

        try:
            async with self._pool.acquire() as connection:
                row = await connection.fetchrow(
                    INSERT_PATCH_RUN_SQL,
                    str(uuid4()),
                    incident_id,
                    status.value,
                    proposal.patch_summary,
                    proposal.rationale,
                    json.dumps([item.model_dump(mode="json") for item in proposal.target_files]),
                    proposal.unified_diff,
                    json.dumps(proposal.verification_steps),
                    proposal.confidence,
                    model_name,
                    based_on_commit_sha,
                    diff_line_count,
                    file_count,
                )
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to create the patch run.") from exc

        if row is None:
            raise PersistenceError("Patch run creation returned no row.")
        return PatchRunRecord.from_db_row(row)
