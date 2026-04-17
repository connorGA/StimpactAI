from __future__ import annotations

from datetime import datetime
from typing import Any

import asyncpg

from api.core.errors import PersistenceError

UPSERT_CLASSIFICATION_SQL = """
INSERT INTO telemetry_fingerprint_classifications (
    project_id,
    fingerprint,
    classification,
    reason,
    source,
    confidence,
    model,
    classified_at,
    updated_at
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, NOW(), NOW()
)
ON CONFLICT (project_id, fingerprint)
DO UPDATE SET
    classification = EXCLUDED.classification,
    reason = EXCLUDED.reason,
    source = EXCLUDED.source,
    confidence = EXCLUDED.confidence,
    model = EXCLUDED.model,
    updated_at = NOW();
"""

SELECT_CLASSIFICATION_SQL = """
SELECT project_id, fingerprint, classification, reason, source, confidence, model,
       classified_at, updated_at
  FROM telemetry_fingerprint_classifications
 WHERE project_id = $1 AND fingerprint = $2
 LIMIT 1;
"""

DELETE_CLASSIFICATION_SQL = """
DELETE FROM telemetry_fingerprint_classifications
 WHERE project_id = $1 AND fingerprint = $2;
"""


class FingerprintClassificationRepository:
    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self._pool = pool

    async def get(
        self,
        *,
        project_id: str,
        fingerprint: str,
    ) -> dict[str, Any] | None:
        if self._pool is None:
            return None
        try:
            async with self._pool.acquire() as connection:
                row = await connection.fetchrow(
                    SELECT_CLASSIFICATION_SQL,
                    project_id,
                    fingerprint,
                )
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to load fingerprint classification.") from exc
        if row is None:
            return None
        return dict(row)

    async def put(
        self,
        *,
        project_id: str,
        fingerprint: str,
        classification: str,
        reason: str | None,
        source: str,
        confidence: float | None = None,
        model: str | None = None,
    ) -> None:
        if self._pool is None:
            return
        try:
            async with self._pool.acquire() as connection:
                await connection.execute(
                    UPSERT_CLASSIFICATION_SQL,
                    project_id,
                    fingerprint,
                    classification,
                    reason,
                    source,
                    confidence,
                    model,
                )
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to persist fingerprint classification.") from exc

    async def clear(
        self,
        *,
        project_id: str,
        fingerprint: str,
    ) -> None:
        if self._pool is None:
            return
        try:
            async with self._pool.acquire() as connection:
                await connection.execute(
                    DELETE_CLASSIFICATION_SQL,
                    project_id,
                    fingerprint,
                )
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to clear fingerprint classification.") from exc


# Protocol-friendly alias for dependency injection / testing.
_: object = FingerprintClassificationRepository  # keep symbol used so linters don't remove import
