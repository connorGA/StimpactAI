from __future__ import annotations

import logging

import asyncpg
from fastapi import FastAPI, Request

from api.core.config import get_bool_env, get_database_url, is_valid_database_url
from api.db.migrations import apply_pending_migrations

logger = logging.getLogger(__name__)


class PostgresConnectionManager:
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or get_database_url()
        self._run_migrations = get_bool_env("AGENT_PLATFORM_RUN_MIGRATIONS", True)
        self._pool: asyncpg.Pool | None = None

    @property
    def pool(self) -> asyncpg.Pool | None:
        return self._pool

    async def connect(self) -> None:
        if not self._database_url:
            logger.warning("DATABASE_URL is not configured; persistence is disabled.")
            return

        if not is_valid_database_url(self._database_url):
            raise ValueError(
                "DATABASE_URL must be a Postgres connection string like "
                "'postgresql://postgres:password@host:5432/postgres'. "
                "A Supabase project URL such as 'https://<project>.supabase.co' will not work here."
            )
            return

        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                dsn=self._database_url,
                min_size=1,
                max_size=5,
                command_timeout=10,
            )
            if self._run_migrations:
                await apply_pending_migrations(self._pool)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


def install_postgres(app: FastAPI) -> PostgresConnectionManager:
    manager = PostgresConnectionManager()
    app.state.postgres = manager
    return manager


def get_postgres_manager(request: Request) -> PostgresConnectionManager:
    return request.app.state.postgres
