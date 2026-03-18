from __future__ import annotations

import json
from uuid import uuid4

import asyncpg

from api.core.errors import PersistenceError
from models.control_plane import (
    ProviderIntegrationRecord,
    ProviderIntegrationStatus,
    ProviderKind,
    ProviderRepositoryRecord,
    RepoProfileRecord,
    RuntimeKind,
    SecretBackend,
    SecretRefRecord,
)

INSERT_PROVIDER_INTEGRATION_SQL = """
INSERT INTO provider_integrations (
    id, provider, name, status, credentials_secret_ref_id, webhook_secret_ref_id, aws_region, metadata
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8::jsonb
)
RETURNING *;
"""

LIST_PROVIDER_INTEGRATIONS_SQL = """
SELECT *
FROM provider_integrations
ORDER BY created_at DESC;
"""

GET_PROVIDER_INTEGRATION_SQL = """
SELECT *
FROM provider_integrations
WHERE id = $1
LIMIT 1;
"""

FIND_PROVIDER_INTEGRATION_BY_METADATA_SQL = """
SELECT *
FROM provider_integrations
WHERE provider = $1
  AND jsonb_extract_path_text(metadata, $2) = $3
ORDER BY created_at DESC
LIMIT 1;
"""

UPDATE_PROVIDER_INTEGRATION_SQL = """
UPDATE provider_integrations
SET status = $2,
    credentials_secret_ref_id = $3,
    webhook_secret_ref_id = $4,
    aws_region = $5,
    metadata = $6::jsonb,
    updated_at = NOW()
WHERE id = $1
RETURNING *;
"""

INSERT_PROVIDER_REPOSITORY_SQL = """
INSERT INTO provider_repositories (
    id, provider_integration_id, provider, external_repository_id, owner, name, default_branch, clone_url
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8
)
RETURNING *;
"""

UPSERT_PROVIDER_REPOSITORY_SQL = """
INSERT INTO provider_repositories (
    id, provider_integration_id, provider, external_repository_id, owner, name, default_branch, clone_url
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8
)
ON CONFLICT (provider_integration_id, external_repository_id) DO UPDATE
SET owner = EXCLUDED.owner,
    name = EXCLUDED.name,
    default_branch = EXCLUDED.default_branch,
    clone_url = EXCLUDED.clone_url,
    updated_at = NOW()
RETURNING *;
"""

GET_PROVIDER_REPOSITORY_SQL = """
SELECT *
FROM provider_repositories
WHERE id = $1
LIMIT 1;
"""

LIST_PROVIDER_REPOSITORIES_SQL = """
SELECT *
FROM provider_repositories
WHERE provider_integration_id = $1
ORDER BY owner ASC, name ASC;
"""

INSERT_SECRET_REF_SQL = """
INSERT INTO secret_refs (
    id, project_id, label, description, backend, external_ref
) VALUES (
    $1, $2, $3, $4, $5, $6
)
RETURNING *;
"""

LIST_SECRET_REFS_SQL = """
SELECT *
FROM secret_refs
WHERE project_id = $1
ORDER BY created_at DESC;
"""

GET_SECRET_REF_SQL = """
SELECT *
FROM secret_refs
WHERE id = $1
LIMIT 1;
"""

INSERT_REPO_PROFILE_SQL = """
INSERT INTO repo_profiles (
    id,
    project_id,
    provider_repository_id,
    runtime_kind,
    base_image,
    install_command,
    startup_commands,
    reproduce_command,
    verify_command,
    success_criteria,
    network_allowlist,
    active
) VALUES (
    $1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11::jsonb, $12
)
RETURNING *;
"""

LIST_REPO_PROFILES_SQL = """
SELECT *
FROM repo_profiles
WHERE project_id = $1
ORDER BY created_at DESC;
"""

GET_ACTIVE_REPO_PROFILE_SQL = """
SELECT *
FROM repo_profiles
WHERE project_id = $1
  AND active = TRUE
ORDER BY created_at DESC
LIMIT 1;
"""

GET_REPO_PROFILE_SQL = """
SELECT *
FROM repo_profiles
WHERE id = $1
LIMIT 1;
"""

INSERT_REPO_PROFILE_SECRET_REF_SQL = """
INSERT INTO repo_profile_secret_refs (
    repo_profile_id, secret_ref_id, mount_as
) VALUES (
    $1, $2, $3
)
ON CONFLICT (repo_profile_id, secret_ref_id, mount_as) DO NOTHING;
"""

LIST_REPO_PROFILE_SECRET_REFS_SQL = """
SELECT secret_refs.*
FROM repo_profile_secret_refs
JOIN secret_refs ON secret_refs.id = repo_profile_secret_refs.secret_ref_id
WHERE repo_profile_secret_refs.repo_profile_id = $1
ORDER BY repo_profile_secret_refs.created_at ASC;
"""


class ControlPlaneRepository:
    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self._pool = pool

    async def create_provider_integration(
        self,
        *,
        provider: ProviderKind,
        name: str,
        credentials_secret_ref_id: str | None,
        webhook_secret_ref_id: str | None,
        aws_region: str | None,
        metadata: dict[str, object],
        status: ProviderIntegrationStatus = ProviderIntegrationStatus.ACTIVE,
    ) -> ProviderIntegrationRecord:
        row = await self._fetchrow(
            INSERT_PROVIDER_INTEGRATION_SQL,
            str(uuid4()),
            provider.value,
            name,
            status.value,
            credentials_secret_ref_id,
            webhook_secret_ref_id,
            aws_region,
            json.dumps(metadata),
        )
        return ProviderIntegrationRecord.from_db_row(row)

    async def list_provider_integrations(self) -> list[ProviderIntegrationRecord]:
        rows = await self._fetch(LIST_PROVIDER_INTEGRATIONS_SQL)
        return [ProviderIntegrationRecord.from_db_row(row) for row in rows]

    async def get_provider_integration(self, provider_integration_id: str) -> ProviderIntegrationRecord | None:
        row = await self._fetchrow(GET_PROVIDER_INTEGRATION_SQL, provider_integration_id, allow_missing=True)
        if row is None:
            return None
        return ProviderIntegrationRecord.from_db_row(row)

    async def find_provider_integration_by_metadata(
        self,
        *,
        provider: ProviderKind,
        metadata_key: str,
        metadata_value: str,
    ) -> ProviderIntegrationRecord | None:
        row = await self._fetchrow(
            FIND_PROVIDER_INTEGRATION_BY_METADATA_SQL,
            provider.value,
            metadata_key,
            metadata_value,
            allow_missing=True,
        )
        if row is None:
            return None
        return ProviderIntegrationRecord.from_db_row(row)

    async def update_provider_integration(
        self,
        provider_integration_id: str,
        *,
        status: ProviderIntegrationStatus,
        credentials_secret_ref_id: str | None,
        webhook_secret_ref_id: str | None,
        aws_region: str | None,
        metadata: dict[str, object],
    ) -> ProviderIntegrationRecord:
        row = await self._fetchrow(
            UPDATE_PROVIDER_INTEGRATION_SQL,
            provider_integration_id,
            status.value,
            credentials_secret_ref_id,
            webhook_secret_ref_id,
            aws_region,
            json.dumps(metadata),
        )
        return ProviderIntegrationRecord.from_db_row(row)

    async def create_provider_repository(
        self,
        *,
        provider_integration_id: str,
        provider: ProviderKind,
        external_repository_id: str,
        owner: str,
        name: str,
        default_branch: str,
        clone_url: str,
    ) -> ProviderRepositoryRecord:
        row = await self._fetchrow(
            INSERT_PROVIDER_REPOSITORY_SQL,
            str(uuid4()),
            provider_integration_id,
            provider.value,
            external_repository_id,
            owner,
            name,
            default_branch,
            clone_url,
        )
        return ProviderRepositoryRecord.from_db_row(row)

    async def get_provider_repository(self, provider_repository_id: str) -> ProviderRepositoryRecord | None:
        row = await self._fetchrow(GET_PROVIDER_REPOSITORY_SQL, provider_repository_id, allow_missing=True)
        if row is None:
            return None
        return ProviderRepositoryRecord.from_db_row(row)

    async def upsert_provider_repository(
        self,
        *,
        provider_integration_id: str,
        provider: ProviderKind,
        external_repository_id: str,
        owner: str,
        name: str,
        default_branch: str,
        clone_url: str,
    ) -> ProviderRepositoryRecord:
        row = await self._fetchrow(
            UPSERT_PROVIDER_REPOSITORY_SQL,
            str(uuid4()),
            provider_integration_id,
            provider.value,
            external_repository_id,
            owner,
            name,
            default_branch,
            clone_url,
        )
        return ProviderRepositoryRecord.from_db_row(row)

    async def list_provider_repositories(self, provider_integration_id: str) -> list[ProviderRepositoryRecord]:
        rows = await self._fetch(LIST_PROVIDER_REPOSITORIES_SQL, provider_integration_id)
        return [ProviderRepositoryRecord.from_db_row(row) for row in rows]

    async def create_secret_ref(
        self,
        *,
        project_id: str,
        label: str,
        description: str | None,
        backend: SecretBackend,
        external_ref: str,
    ) -> SecretRefRecord:
        row = await self._fetchrow(
            INSERT_SECRET_REF_SQL,
            str(uuid4()),
            project_id,
            label,
            description,
            backend.value,
            external_ref,
        )
        return SecretRefRecord.from_db_row(row)

    async def list_secret_refs(self, project_id: str) -> list[SecretRefRecord]:
        rows = await self._fetch(LIST_SECRET_REFS_SQL, project_id)
        return [SecretRefRecord.from_db_row(row) for row in rows]

    async def get_secret_ref(self, secret_ref_id: str) -> SecretRefRecord | None:
        row = await self._fetchrow(GET_SECRET_REF_SQL, secret_ref_id, allow_missing=True)
        if row is None:
            return None
        return SecretRefRecord.from_db_row(row)

    async def create_repo_profile(
        self,
        *,
        project_id: str,
        provider_repository_id: str,
        runtime_kind: RuntimeKind,
        base_image: str | None,
        install_command: str | None,
        startup_commands: list[str],
        reproduce_command: str,
        verify_command: str,
        success_criteria: str | None,
        network_allowlist: list[str],
        active: bool = True,
    ) -> RepoProfileRecord:
        row = await self._fetchrow(
            INSERT_REPO_PROFILE_SQL,
            str(uuid4()),
            project_id,
            provider_repository_id,
            runtime_kind.value,
            base_image,
            install_command,
            json.dumps(startup_commands),
            reproduce_command,
            verify_command,
            success_criteria,
            json.dumps(network_allowlist),
            active,
        )
        return RepoProfileRecord.from_db_row(row)

    async def list_repo_profiles(self, project_id: str) -> list[RepoProfileRecord]:
        rows = await self._fetch(LIST_REPO_PROFILES_SQL, project_id)
        return [RepoProfileRecord.from_db_row(row) for row in rows]

    async def get_repo_profile(self, repo_profile_id: str) -> RepoProfileRecord | None:
        row = await self._fetchrow(GET_REPO_PROFILE_SQL, repo_profile_id, allow_missing=True)
        if row is None:
            return None
        return RepoProfileRecord.from_db_row(row)

    async def get_active_repo_profile(self, project_id: str) -> RepoProfileRecord | None:
        row = await self._fetchrow(GET_ACTIVE_REPO_PROFILE_SQL, project_id, allow_missing=True)
        if row is None:
            return None
        return RepoProfileRecord.from_db_row(row)

    async def attach_secret_ref_to_repo_profile(
        self,
        *,
        repo_profile_id: str,
        secret_ref_id: str,
        mount_as: str,
    ) -> None:
        await self._execute(
            INSERT_REPO_PROFILE_SECRET_REF_SQL,
            repo_profile_id,
            secret_ref_id,
            mount_as,
        )

    async def list_repo_profile_secret_refs(self, repo_profile_id: str) -> list[SecretRefRecord]:
        rows = await self._fetch(LIST_REPO_PROFILE_SECRET_REFS_SQL, repo_profile_id)
        return [SecretRefRecord.from_db_row(row) for row in rows]

    async def _fetchrow(
        self,
        query: str,
        *params: object,
        allow_missing: bool = False,
    ):
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for control-plane operations.")
        try:
            async with self._pool.acquire() as connection:
                row = await connection.fetchrow(query, *params)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to execute a control-plane query.") from exc
        if row is None and not allow_missing:
            raise PersistenceError("Control-plane query returned no row.")
        return row

    async def _fetch(self, query: str, *params: object):
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for control-plane operations.")
        try:
            async with self._pool.acquire() as connection:
                return await connection.fetch(query, *params)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to execute a control-plane query.") from exc

    async def _execute(self, query: str, *params: object) -> None:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for control-plane operations.")
        try:
            async with self._pool.acquire() as connection:
                await connection.execute(query, *params)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to update a control-plane record.") from exc
