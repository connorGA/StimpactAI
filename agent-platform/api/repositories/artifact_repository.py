from __future__ import annotations

from uuid import uuid4

import asyncpg

from api.core.errors import PersistenceError
from models.artifact import ArtifactRecord, ArtifactStorageBackend, ArtifactType

INSERT_ARTIFACT_SQL = """
INSERT INTO artifacts (
    id,
    incident_id,
    patch_run_id,
    sandbox_run_id,
    artifact_type,
    storage_backend,
    bucket_name,
    object_key,
    uri,
    content_type,
    size_bytes,
    checksum_sha256
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
)
RETURNING *;
"""

LIST_SANDBOX_RUN_ARTIFACTS_SQL = """
SELECT *
FROM artifacts
WHERE sandbox_run_id = $1
ORDER BY created_at ASC;
"""


class ArtifactRepository:
    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self._pool = pool

    async def create_artifact(
        self,
        *,
        incident_id: str | None,
        patch_run_id: str | None,
        sandbox_run_id: str | None,
        artifact_type: ArtifactType,
        storage_backend: ArtifactStorageBackend,
        bucket_name: str,
        object_key: str,
        uri: str,
        content_type: str,
        size_bytes: int,
        checksum_sha256: str | None,
    ) -> ArtifactRecord:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for artifact operations.")
        try:
            async with self._pool.acquire() as connection:
                row = await connection.fetchrow(
                    INSERT_ARTIFACT_SQL,
                    str(uuid4()),
                    incident_id,
                    patch_run_id,
                    sandbox_run_id,
                    artifact_type.value,
                    storage_backend.value,
                    bucket_name,
                    object_key,
                    uri,
                    content_type,
                    size_bytes,
                    checksum_sha256,
                )
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to create artifact metadata.") from exc
        if row is None:
            raise PersistenceError("Artifact creation returned no row.")
        return ArtifactRecord.from_db_row(row)

    async def list_sandbox_run_artifacts(self, sandbox_run_id: str) -> list[ArtifactRecord]:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for artifact operations.")
        try:
            async with self._pool.acquire() as connection:
                rows = await connection.fetch(LIST_SANDBOX_RUN_ARTIFACTS_SQL, sandbox_run_id)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to list sandbox artifacts.") from exc
        return [ArtifactRecord.from_db_row(row) for row in rows]
