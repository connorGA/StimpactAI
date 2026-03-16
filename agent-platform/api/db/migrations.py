from __future__ import annotations

from pathlib import Path

import asyncpg

CREATE_MIGRATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


async def apply_pending_migrations(
    pool: asyncpg.Pool,
    *,
    migrations_dir: Path | None = None,
) -> None:
    base_dir = Path(__file__).resolve().parents[2]
    target_dir = migrations_dir or base_dir / "db" / "migrations"

    migration_files = sorted(path for path in target_dir.glob("*.sql") if path.is_file())
    if not migration_files:
        return

    async with pool.acquire() as connection:
        await connection.execute(CREATE_MIGRATIONS_TABLE_SQL)
        applied_versions = {
            row["version"]
            for row in await connection.fetch("SELECT version FROM schema_migrations")
        }

        for migration_file in migration_files:
            version = migration_file.stem
            if version in applied_versions:
                continue

            sql = migration_file.read_text(encoding="utf-8").strip()
            if not sql:
                continue

            async with connection.transaction():
                await connection.execute(sql)
                await connection.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1)",
                    version,
                )
