from __future__ import annotations

import json
from uuid import uuid4

import asyncpg

from api.core.errors import PersistenceError
from models.control_plane import (
    AutonomyMode,
    ProjectServiceDependencyKind,
    ProjectServiceDependencyRecord,
    ProjectServiceRecord,
    ProjectServiceRoutingHints,
    ProjectTelemetryHeartbeatRecord,
    ProjectServiceType,
    ProjectApiKeyRecord,
    ProjectApiKeyStatus,
    ProjectBrowserKeyRecord,
    ProjectBrowserKeyStatus,
    ProjectOnboardingStateRecord,
    ProjectPolicyRecord,
    ProjectSdkSetupStatus,
    ProviderIntegrationRecord,
    ProviderIntegrationStatus,
    ProviderKind,
    ProviderRepositoryRecord,
    RepoProfileRecord,
    RepoProfileSecretBindingRecord,
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

LIST_PROVIDER_INTEGRATIONS_BY_PROJECT_SQL = """
SELECT *
FROM provider_integrations
WHERE jsonb_extract_path_text(metadata, 'project_id') = $1
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

DELETE_SECRET_REF_SQL = """
DELETE FROM secret_refs
WHERE id = $1
RETURNING *;
"""

INSERT_PROJECT_API_KEY_SQL = """
INSERT INTO project_api_keys (
    id, project_id, name, key_prefix, key_hash, status
) VALUES (
    $1, $2, $3, $4, $5, $6
)
RETURNING *;
"""

LIST_PROJECT_API_KEYS_SQL = """
SELECT *
FROM project_api_keys
WHERE project_id = $1
ORDER BY created_at DESC;
"""

GET_PROJECT_API_KEY_SQL = """
SELECT *
FROM project_api_keys
WHERE id = $1
LIMIT 1;
"""

FIND_ACTIVE_PROJECT_API_KEY_BY_HASH_SQL = """
SELECT *
FROM project_api_keys
WHERE project_id = $1
  AND key_hash = $2
  AND status = 'active'
LIMIT 1;
"""

COUNT_ACTIVE_PROJECT_API_KEYS_SQL = """
SELECT COUNT(*)
FROM project_api_keys
WHERE project_id = $1
  AND status = 'active';
"""

INSERT_PROJECT_BROWSER_KEY_SQL = """
INSERT INTO project_browser_keys (
    id, project_id, name, key_prefix, key_hash, allowed_origins, status
) VALUES (
    $1, $2, $3, $4, $5, $6::jsonb, $7
)
RETURNING *;
"""

LIST_PROJECT_BROWSER_KEYS_SQL = """
SELECT *
FROM project_browser_keys
WHERE project_id = $1
ORDER BY created_at DESC;
"""

LIST_ACTIVE_PROJECT_BROWSER_KEY_ORIGINS_SQL = """
SELECT DISTINCT LOWER(origin.value) AS origin
FROM project_browser_keys
CROSS JOIN LATERAL jsonb_array_elements_text(allowed_origins) AS origin(value)
WHERE status = 'active'
  AND LENGTH(TRIM(origin.value)) > 0
ORDER BY origin;
"""

GET_PROJECT_BROWSER_KEY_SQL = """
SELECT *
FROM project_browser_keys
WHERE id = $1
LIMIT 1;
"""

FIND_ACTIVE_PROJECT_BROWSER_KEY_BY_HASH_SQL = """
SELECT *
FROM project_browser_keys
WHERE project_id = $1
  AND key_hash = $2
  AND status = 'active'
LIMIT 1;
"""

COUNT_ACTIVE_PROJECT_BROWSER_KEYS_SQL = """
SELECT COUNT(*)
FROM project_browser_keys
WHERE project_id = $1
  AND status = 'active';
"""

MARK_PROJECT_API_KEY_USED_SQL = """
UPDATE project_api_keys
SET last_used_at = NOW(),
    updated_at = NOW()
WHERE id = $1
RETURNING *;
"""

MARK_PROJECT_BROWSER_KEY_USED_SQL = """
UPDATE project_browser_keys
SET last_used_at = NOW(),
    updated_at = NOW()
WHERE id = $1
RETURNING *;
"""

MARK_PROJECT_BROWSER_KEY_ISSUED_SQL = """
UPDATE project_browser_keys
SET last_issued_at = NOW(),
    updated_at = NOW()
WHERE id = $1
RETURNING *;
"""

UPSERT_PROJECT_TELEMETRY_HEARTBEAT_SQL = """
INSERT INTO project_telemetry_heartbeats (
    project_id,
    service,
    environment,
    last_seen_at,
    commit_sha
) VALUES (
    $1, $2, $3, $4, $5
)
ON CONFLICT (project_id, service, environment) DO UPDATE
SET last_seen_at = EXCLUDED.last_seen_at,
    commit_sha = EXCLUDED.commit_sha,
    updated_at = NOW()
RETURNING *;
"""

GET_PROJECT_TELEMETRY_HEARTBEAT_SQL = """
SELECT *
FROM project_telemetry_heartbeats
WHERE project_id = $1
  AND service = $2
  AND environment = $3
LIMIT 1;
"""

LIST_PROJECT_TELEMETRY_HEARTBEATS_SQL = """
SELECT *
FROM project_telemetry_heartbeats
WHERE project_id = $1
ORDER BY last_seen_at DESC;
"""

REVOKE_PROJECT_API_KEY_SQL = """
UPDATE project_api_keys
SET status = $2,
    revoked_at = NOW(),
    updated_at = NOW()
WHERE id = $1
RETURNING *;
"""

REVOKE_PROJECT_BROWSER_KEY_SQL = """
UPDATE project_browser_keys
SET status = $2,
    revoked_at = NOW(),
    updated_at = NOW()
WHERE id = $1
RETURNING *;
"""

UPDATE_PROJECT_BROWSER_KEY_SQL = """
UPDATE project_browser_keys
SET allowed_origins = $2::jsonb,
    updated_at = NOW()
WHERE id = $1
RETURNING *;
"""

ENSURE_PROJECT_ONBOARDING_STATE_SQL = """
INSERT INTO project_onboarding_states (
    project_id
) VALUES (
    $1
)
ON CONFLICT (project_id) DO NOTHING;
"""

GET_PROJECT_ONBOARDING_STATE_SQL = """
SELECT *
FROM project_onboarding_states
WHERE project_id = $1
LIMIT 1;
"""

UPSERT_PROJECT_ONBOARDING_STATE_SQL = """
INSERT INTO project_onboarding_states (
    project_id,
    policy_reviewed,
    sdk_setup_status,
    sdk_setup_provider_repository_id,
    sdk_setup_change_request_url
) VALUES (
    $1, $2, $3, $4, $5
)
ON CONFLICT (project_id) DO UPDATE
SET policy_reviewed = EXCLUDED.policy_reviewed,
    sdk_setup_status = EXCLUDED.sdk_setup_status,
    sdk_setup_provider_repository_id = EXCLUDED.sdk_setup_provider_repository_id,
    sdk_setup_change_request_url = EXCLUDED.sdk_setup_change_request_url,
    updated_at = NOW()
RETURNING *;
"""

ENSURE_PROJECT_POLICY_SQL = """
INSERT INTO project_policies (
    project_id
) VALUES (
    $1
)
ON CONFLICT (project_id) DO NOTHING;
"""

GET_PROJECT_POLICY_SQL = """
SELECT *
FROM project_policies
WHERE project_id = $1
LIMIT 1;
"""

UPSERT_PROJECT_POLICY_SQL = """
INSERT INTO project_policies (
    project_id,
    autonomy_mode,
    require_human_approval,
    allow_production_writes,
    allow_low_risk_autonomy,
    block_during_active_deploys,
    restrict_to_approved_services,
    require_rollback_plan,
    require_post_action_verification,
    approved_services,
    failure_classifier_enabled,
    root_cause_enabled,
    patch_planner_enabled,
    runbook_executor_enabled
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11, $12, $13, $14
)
ON CONFLICT (project_id) DO UPDATE
SET autonomy_mode = EXCLUDED.autonomy_mode,
    require_human_approval = EXCLUDED.require_human_approval,
    allow_production_writes = EXCLUDED.allow_production_writes,
    allow_low_risk_autonomy = EXCLUDED.allow_low_risk_autonomy,
    block_during_active_deploys = EXCLUDED.block_during_active_deploys,
    restrict_to_approved_services = EXCLUDED.restrict_to_approved_services,
    require_rollback_plan = EXCLUDED.require_rollback_plan,
    require_post_action_verification = EXCLUDED.require_post_action_verification,
    approved_services = EXCLUDED.approved_services,
    failure_classifier_enabled = EXCLUDED.failure_classifier_enabled,
    root_cause_enabled = EXCLUDED.root_cause_enabled,
    patch_planner_enabled = EXCLUDED.patch_planner_enabled,
    runbook_executor_enabled = EXCLUDED.runbook_executor_enabled,
    updated_at = NOW()
RETURNING *;
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

LIST_REPO_PROFILE_SECRET_BINDINGS_SQL = """
SELECT
    secret_refs.*,
    repo_profile_secret_refs.repo_profile_id,
    repo_profile_secret_refs.secret_ref_id,
    repo_profile_secret_refs.mount_as,
    repo_profile_secret_refs.created_at AS binding_created_at
FROM repo_profile_secret_refs
JOIN secret_refs ON secret_refs.id = repo_profile_secret_refs.secret_ref_id
WHERE repo_profile_secret_refs.repo_profile_id = $1
ORDER BY repo_profile_secret_refs.created_at ASC;
"""

INSERT_PROJECT_SERVICE_SQL = """
INSERT INTO project_services (
    id,
    project_id,
    name,
    slug,
    service_type,
    repo_profile_id,
    owner,
    deploy_target,
    tracked_branch,
    routing_hints,
    startup_priority,
    sandbox_healthcheck_command,
    sandbox_healthcheck_url,
    active
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11, $12, $13, $14
)
RETURNING *;
"""

UPDATE_PROJECT_SERVICE_SQL = """
UPDATE project_services
SET name = $2,
    slug = $3,
    service_type = $4,
    repo_profile_id = $5,
    owner = $6,
    deploy_target = $7,
    tracked_branch = $8,
    routing_hints = $9::jsonb,
    startup_priority = $10,
    sandbox_healthcheck_command = $11,
    sandbox_healthcheck_url = $12,
    active = $13,
    updated_at = NOW()
WHERE id = $1
RETURNING *;
"""

LIST_PROJECT_SERVICES_SQL = """
SELECT *
FROM project_services
WHERE project_id = $1
ORDER BY startup_priority ASC, created_at ASC;
"""

GET_PROJECT_SERVICE_SQL = """
SELECT *
FROM project_services
WHERE id = $1
LIMIT 1;
"""

GET_PROJECT_SERVICE_BY_SLUG_SQL = """
SELECT *
FROM project_services
WHERE project_id = $1
  AND slug = $2
LIMIT 1;
"""

LIST_PROJECT_SERVICE_DEPENDENCIES_SQL = """
SELECT *
FROM project_service_dependencies
WHERE service_id = $1
ORDER BY created_at ASC;
"""

LIST_PROJECT_DEPENDENCIES_FOR_SERVICES_SQL = """
SELECT *
FROM project_service_dependencies
WHERE service_id = ANY($1::uuid[])
ORDER BY created_at ASC;
"""

DELETE_PROJECT_SERVICE_DEPENDENCIES_SQL = """
DELETE FROM project_service_dependencies
WHERE service_id = $1;
"""

INSERT_PROJECT_SERVICE_DEPENDENCY_SQL = """
INSERT INTO project_service_dependencies (
    service_id,
    depends_on_service_id,
    dependency_kind
) VALUES (
    $1, $2, $3
)
ON CONFLICT (service_id, depends_on_service_id) DO UPDATE
SET dependency_kind = EXCLUDED.dependency_kind;
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

    async def list_provider_integrations(self, project_id: str | None = None) -> list[ProviderIntegrationRecord]:
        query = LIST_PROVIDER_INTEGRATIONS_BY_PROJECT_SQL if project_id is not None else LIST_PROVIDER_INTEGRATIONS_SQL
        rows = await self._fetch(query, project_id) if project_id is not None else await self._fetch(query)
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

    async def delete_secret_ref(self, secret_ref_id: str) -> SecretRefRecord | None:
        row = await self._fetchrow(DELETE_SECRET_REF_SQL, secret_ref_id, allow_missing=True)
        if row is None:
            return None
        return SecretRefRecord.from_db_row(row)

    async def create_project_api_key(
        self,
        *,
        project_id: str,
        name: str,
        key_prefix: str,
        key_hash: str,
        status: ProjectApiKeyStatus = ProjectApiKeyStatus.ACTIVE,
    ) -> ProjectApiKeyRecord:
        row = await self._fetchrow(
            INSERT_PROJECT_API_KEY_SQL,
            str(uuid4()),
            project_id,
            name,
            key_prefix,
            key_hash,
            status.value,
        )
        return ProjectApiKeyRecord.from_db_row(row)

    async def list_project_api_keys(self, project_id: str) -> list[ProjectApiKeyRecord]:
        rows = await self._fetch(LIST_PROJECT_API_KEYS_SQL, project_id)
        return [ProjectApiKeyRecord.from_db_row(row) for row in rows]

    async def get_project_api_key(self, key_id: str) -> ProjectApiKeyRecord | None:
        row = await self._fetchrow(GET_PROJECT_API_KEY_SQL, key_id, allow_missing=True)
        if row is None:
            return None
        return ProjectApiKeyRecord.from_db_row(row)

    async def find_active_project_api_key(
        self,
        *,
        project_id: str,
        key_hash: str,
    ) -> ProjectApiKeyRecord | None:
        row = await self._fetchrow(
            FIND_ACTIVE_PROJECT_API_KEY_BY_HASH_SQL,
            project_id,
            key_hash,
            allow_missing=True,
        )
        if row is None:
            return None
        return ProjectApiKeyRecord.from_db_row(row)

    async def has_active_project_api_keys(self, project_id: str) -> bool:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for control-plane operations.")
        try:
            async with self._pool.acquire() as connection:
                count = await connection.fetchval(COUNT_ACTIVE_PROJECT_API_KEYS_SQL, project_id)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to execute a control-plane query.") from exc
        return bool(count and int(count) > 0)

    async def create_project_browser_key(
        self,
        *,
        project_id: str,
        name: str,
        key_prefix: str,
        key_hash: str,
        allowed_origins: list[str],
        status: ProjectBrowserKeyStatus = ProjectBrowserKeyStatus.ACTIVE,
    ) -> ProjectBrowserKeyRecord:
        row = await self._fetchrow(
            INSERT_PROJECT_BROWSER_KEY_SQL,
            str(uuid4()),
            project_id,
            name,
            key_prefix,
            key_hash,
            json.dumps(allowed_origins),
            status.value,
        )
        return ProjectBrowserKeyRecord.from_db_row(row)

    async def list_project_browser_keys(self, project_id: str) -> list[ProjectBrowserKeyRecord]:
        rows = await self._fetch(LIST_PROJECT_BROWSER_KEYS_SQL, project_id)
        return [ProjectBrowserKeyRecord.from_db_row(row) for row in rows]

    async def list_active_project_browser_key_origins(self) -> list[str]:
        rows = await self._fetch(LIST_ACTIVE_PROJECT_BROWSER_KEY_ORIGINS_SQL)
        return [str(row["origin"]) for row in rows if row["origin"]]

    async def get_project_browser_key(self, key_id: str) -> ProjectBrowserKeyRecord | None:
        row = await self._fetchrow(GET_PROJECT_BROWSER_KEY_SQL, key_id, allow_missing=True)
        if row is None:
            return None
        return ProjectBrowserKeyRecord.from_db_row(row)

    async def find_active_project_browser_key(
        self,
        *,
        project_id: str,
        key_hash: str,
    ) -> ProjectBrowserKeyRecord | None:
        row = await self._fetchrow(
            FIND_ACTIVE_PROJECT_BROWSER_KEY_BY_HASH_SQL,
            project_id,
            key_hash,
            allow_missing=True,
        )
        if row is None:
            return None
        return ProjectBrowserKeyRecord.from_db_row(row)

    async def has_active_project_browser_keys(self, project_id: str) -> bool:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for control-plane operations.")
        try:
            async with self._pool.acquire() as connection:
                count = await connection.fetchval(COUNT_ACTIVE_PROJECT_BROWSER_KEYS_SQL, project_id)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to execute a control-plane query.") from exc
        return bool(count and int(count) > 0)

    async def mark_project_api_key_used(self, key_id: str) -> ProjectApiKeyRecord:
        row = await self._fetchrow(MARK_PROJECT_API_KEY_USED_SQL, key_id)
        return ProjectApiKeyRecord.from_db_row(row)

    async def mark_project_browser_key_used(self, key_id: str) -> ProjectBrowserKeyRecord:
        row = await self._fetchrow(MARK_PROJECT_BROWSER_KEY_USED_SQL, key_id)
        return ProjectBrowserKeyRecord.from_db_row(row)

    async def mark_project_browser_key_issued(self, key_id: str) -> ProjectBrowserKeyRecord:
        row = await self._fetchrow(MARK_PROJECT_BROWSER_KEY_ISSUED_SQL, key_id)
        return ProjectBrowserKeyRecord.from_db_row(row)

    async def revoke_project_api_key(self, key_id: str) -> ProjectApiKeyRecord:
        row = await self._fetchrow(
            REVOKE_PROJECT_API_KEY_SQL,
            key_id,
            ProjectApiKeyStatus.REVOKED.value,
        )
        return ProjectApiKeyRecord.from_db_row(row)

    async def revoke_project_browser_key(self, key_id: str) -> ProjectBrowserKeyRecord:
        row = await self._fetchrow(
            REVOKE_PROJECT_BROWSER_KEY_SQL,
            key_id,
            ProjectBrowserKeyStatus.REVOKED.value,
        )
        return ProjectBrowserKeyRecord.from_db_row(row)

    async def update_project_browser_key(
        self,
        key_id: str,
        *,
        allowed_origins: list[str],
    ) -> ProjectBrowserKeyRecord:
        row = await self._fetchrow(
            UPDATE_PROJECT_BROWSER_KEY_SQL,
            key_id,
            json.dumps(allowed_origins),
        )
        return ProjectBrowserKeyRecord.from_db_row(row)

    async def upsert_project_telemetry_heartbeat(
        self,
        *,
        project_id: str,
        service: str,
        environment: str,
        last_seen_at,
        commit_sha: str | None,
    ) -> ProjectTelemetryHeartbeatRecord:
        row = await self._fetchrow(
            UPSERT_PROJECT_TELEMETRY_HEARTBEAT_SQL,
            project_id,
            service,
            environment,
            last_seen_at,
            commit_sha,
        )
        return ProjectTelemetryHeartbeatRecord.from_db_row(row)

    async def get_project_telemetry_heartbeat(
        self,
        *,
        project_id: str,
        service: str,
        environment: str,
    ) -> ProjectTelemetryHeartbeatRecord | None:
        row = await self._fetchrow(
            GET_PROJECT_TELEMETRY_HEARTBEAT_SQL,
            project_id,
            service,
            environment,
            allow_missing=True,
        )
        if row is None:
            return None
        return ProjectTelemetryHeartbeatRecord.from_db_row(row)

    async def list_project_telemetry_heartbeats(self, project_id: str) -> list[ProjectTelemetryHeartbeatRecord]:
        rows = await self._fetch(LIST_PROJECT_TELEMETRY_HEARTBEATS_SQL, project_id)
        return [ProjectTelemetryHeartbeatRecord.from_db_row(row) for row in rows]

    async def get_or_create_project_onboarding_state(self, project_id: str) -> ProjectOnboardingStateRecord:
        await self._execute(ENSURE_PROJECT_ONBOARDING_STATE_SQL, project_id)
        row = await self._fetchrow(GET_PROJECT_ONBOARDING_STATE_SQL, project_id)
        return ProjectOnboardingStateRecord.from_db_row(row)

    async def update_project_onboarding_state(
        self,
        *,
        project_id: str,
        policy_reviewed: bool,
        sdk_setup_status: ProjectSdkSetupStatus,
        sdk_setup_provider_repository_id: str | None,
        sdk_setup_change_request_url: str | None,
    ) -> ProjectOnboardingStateRecord:
        row = await self._fetchrow(
            UPSERT_PROJECT_ONBOARDING_STATE_SQL,
            project_id,
            policy_reviewed,
            sdk_setup_status.value,
            sdk_setup_provider_repository_id,
            sdk_setup_change_request_url,
        )
        return ProjectOnboardingStateRecord.from_db_row(row)

    async def get_or_create_project_policy(self, project_id: str) -> ProjectPolicyRecord:
        await self._execute(ENSURE_PROJECT_POLICY_SQL, project_id)
        row = await self._fetchrow(GET_PROJECT_POLICY_SQL, project_id)
        return ProjectPolicyRecord.from_db_row(row)

    async def update_project_policy(
        self,
        *,
        project_id: str,
        autonomy_mode: AutonomyMode,
        require_human_approval: bool,
        allow_production_writes: bool,
        allow_low_risk_autonomy: bool,
        block_during_active_deploys: bool,
        restrict_to_approved_services: bool,
        require_rollback_plan: bool,
        require_post_action_verification: bool,
        approved_services: list[str],
        failure_classifier_enabled: bool,
        root_cause_enabled: bool,
        patch_planner_enabled: bool,
        runbook_executor_enabled: bool,
    ) -> ProjectPolicyRecord:
        row = await self._fetchrow(
            UPSERT_PROJECT_POLICY_SQL,
            project_id,
            autonomy_mode.value,
            require_human_approval,
            allow_production_writes,
            allow_low_risk_autonomy,
            block_during_active_deploys,
            restrict_to_approved_services,
            require_rollback_plan,
            require_post_action_verification,
            json.dumps(approved_services),
            failure_classifier_enabled,
            root_cause_enabled,
            patch_planner_enabled,
            runbook_executor_enabled,
        )
        return ProjectPolicyRecord.from_db_row(row)

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

    async def list_repo_profile_secret_bindings(
        self,
        repo_profile_id: str,
    ) -> list[RepoProfileSecretBindingRecord]:
        rows = await self._fetch(LIST_REPO_PROFILE_SECRET_BINDINGS_SQL, repo_profile_id)
        return [RepoProfileSecretBindingRecord.from_db_row(row) for row in rows]

    async def list_repo_profile_secret_refs(self, repo_profile_id: str) -> list[SecretRefRecord]:
        bindings = await self.list_repo_profile_secret_bindings(repo_profile_id)
        return [binding.secret_ref for binding in bindings]

    async def create_project_service(
        self,
        *,
        project_id: str,
        name: str,
        slug: str,
        service_type: ProjectServiceType,
        repo_profile_id: str | None,
        owner: str | None,
        deploy_target: str | None,
        tracked_branch: str | None,
        routing_hints: ProjectServiceRoutingHints,
        startup_priority: int,
        sandbox_healthcheck_command: str | None,
        sandbox_healthcheck_url: str | None,
        active: bool = True,
    ) -> ProjectServiceRecord:
        row = await self._fetchrow(
            INSERT_PROJECT_SERVICE_SQL,
            str(uuid4()),
            project_id,
            name,
            slug,
            service_type.value,
            repo_profile_id,
            owner,
            deploy_target,
            tracked_branch,
            json.dumps(routing_hints.model_dump(mode="json")),
            startup_priority,
            sandbox_healthcheck_command,
            sandbox_healthcheck_url,
            active,
        )
        return ProjectServiceRecord.from_db_row(row)

    async def update_project_service(
        self,
        service_id: str,
        *,
        name: str,
        slug: str,
        service_type: ProjectServiceType,
        repo_profile_id: str | None,
        owner: str | None,
        deploy_target: str | None,
        tracked_branch: str | None,
        routing_hints: ProjectServiceRoutingHints,
        startup_priority: int,
        sandbox_healthcheck_command: str | None,
        sandbox_healthcheck_url: str | None,
        active: bool,
    ) -> ProjectServiceRecord:
        row = await self._fetchrow(
            UPDATE_PROJECT_SERVICE_SQL,
            service_id,
            name,
            slug,
            service_type.value,
            repo_profile_id,
            owner,
            deploy_target,
            tracked_branch,
            json.dumps(routing_hints.model_dump(mode="json")),
            startup_priority,
            sandbox_healthcheck_command,
            sandbox_healthcheck_url,
            active,
        )
        return ProjectServiceRecord.from_db_row(row)

    async def list_project_services(self, project_id: str) -> list[ProjectServiceRecord]:
        rows = await self._fetch(LIST_PROJECT_SERVICES_SQL, project_id)
        return [ProjectServiceRecord.from_db_row(row) for row in rows]

    async def get_project_service(self, service_id: str) -> ProjectServiceRecord | None:
        row = await self._fetchrow(GET_PROJECT_SERVICE_SQL, service_id, allow_missing=True)
        if row is None:
            return None
        return ProjectServiceRecord.from_db_row(row)

    async def get_project_service_by_slug(self, project_id: str, slug: str) -> ProjectServiceRecord | None:
        row = await self._fetchrow(GET_PROJECT_SERVICE_BY_SLUG_SQL, project_id, slug, allow_missing=True)
        if row is None:
            return None
        return ProjectServiceRecord.from_db_row(row)

    async def list_project_service_dependencies(
        self,
        service_id: str,
    ) -> list[ProjectServiceDependencyRecord]:
        rows = await self._fetch(LIST_PROJECT_SERVICE_DEPENDENCIES_SQL, service_id)
        return [ProjectServiceDependencyRecord.from_db_row(row) for row in rows]

    async def list_project_dependencies_for_services(
        self,
        service_ids: list[str],
    ) -> list[ProjectServiceDependencyRecord]:
        if not service_ids:
            return []
        rows = await self._fetch(LIST_PROJECT_DEPENDENCIES_FOR_SERVICES_SQL, service_ids)
        return [ProjectServiceDependencyRecord.from_db_row(row) for row in rows]

    async def replace_project_service_dependencies(
        self,
        service_id: str,
        dependencies: list[tuple[str, ProjectServiceDependencyKind]],
    ) -> list[ProjectServiceDependencyRecord]:
        await self._execute(DELETE_PROJECT_SERVICE_DEPENDENCIES_SQL, service_id)
        for depends_on_service_id, dependency_kind in dependencies:
            await self._execute(
                INSERT_PROJECT_SERVICE_DEPENDENCY_SQL,
                service_id,
                depends_on_service_id,
                dependency_kind.value,
            )
        return await self.list_project_service_dependencies(service_id)

    async def resolve_project_service(
        self,
        *,
        project_id: str,
        service_name: str,
        stacktrace: str | None = None,
    ) -> ProjectServiceRecord | None:
        normalized_service = service_name.strip().lower()
        normalized_stacktrace = (stacktrace or "").lower()
        candidates = await self.list_project_services(project_id)
        if not candidates:
            return None
        scored: list[tuple[int, ProjectServiceRecord]] = []
        for candidate in candidates:
            if not candidate.active:
                continue
            score = 0
            if candidate.slug.lower() == normalized_service:
                score += 120
            if candidate.name.strip().lower() == normalized_service:
                score += 110
            for value in candidate.routing_hints.service_names:
                if value.strip().lower() == normalized_service:
                    score += 100
            for value in candidate.routing_hints.path_prefixes:
                normalized = value.strip().lower()
                if normalized and normalized in normalized_stacktrace:
                    score += 40
            for value in candidate.routing_hints.domains:
                normalized = value.strip().lower()
                if normalized and normalized in normalized_stacktrace:
                    score += 20
            for value in candidate.routing_hints.tags:
                normalized = value.strip().lower()
                if normalized and normalized in normalized_service:
                    score += 10
            if score > 0:
                scored.append((score, candidate))
        if scored:
            scored.sort(key=lambda item: (-item[0], item[1].startup_priority, item[1].created_at))
            return scored[0][1]
        active_candidates = [candidate for candidate in candidates if candidate.active]
        if len(active_candidates) == 1:
            return active_candidates[0]
        return None

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
