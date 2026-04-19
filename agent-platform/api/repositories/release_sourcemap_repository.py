from __future__ import annotations

from uuid import uuid4

import asyncpg

from api.core.errors import PersistenceError
from models.release_sourcemap import ReleaseSourcemapRecord

INSERT_RELEASE_SOURCEMAP_SQL = """
INSERT INTO release_sourcemaps (
    id,
    project_id,
    release,
    dist,
    artifact_id,
    bundle_path
) VALUES (
    $1, $2, $3, $4, $5, $6
)
ON CONFLICT (project_id, release, dist, bundle_path) DO UPDATE
SET artifact_id = EXCLUDED.artifact_id,
    created_at = NOW()
RETURNING *;
"""

GET_RELEASE_SOURCEMAP_SQL = """
SELECT *
FROM release_sourcemaps
WHERE project_id = $1
  AND release = $2
  AND dist = $3
  AND bundle_path = $4
LIMIT 1;
"""


class ReleaseSourcemapRepository:
    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self._pool = pool

    async def upsert_release_sourcemap(
        self,
        *,
        project_id: str,
        release: str,
        dist: str,
        artifact_id: str,
        bundle_path: str,
    ) -> ReleaseSourcemapRecord:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for release sourcemap storage.")
        try:
            async with self._pool.acquire() as connection:
                row = await connection.fetchrow(
                    INSERT_RELEASE_SOURCEMAP_SQL,
                    str(uuid4()),
                    project_id,
                    release,
                    dist,
                    artifact_id,
                    bundle_path,
                )
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to persist release sourcemap metadata.") from exc
        if row is None:
            raise PersistenceError("Release sourcemap upsert returned no row.")
        return ReleaseSourcemapRecord.from_db_row(row)

    async def get_release_sourcemap(
        self,
        *,
        project_id: str,
        release: str,
        dist: str,
        bundle_path: str,
    ) -> ReleaseSourcemapRecord | None:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for release sourcemap reads.")
        try:
            async with self._pool.acquire() as connection:
                row = await connection.fetchrow(
                    GET_RELEASE_SOURCEMAP_SQL,
                    project_id,
                    release,
                    dist,
                    bundle_path,
                )
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to read release sourcemap metadata.") from exc
        if row is None:
            return None
        return ReleaseSourcemapRecord.from_db_row(row)
