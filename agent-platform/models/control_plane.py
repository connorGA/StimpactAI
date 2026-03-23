from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _decode_json_array(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return []
        if normalized.startswith("[") and normalized.endswith("]"):
            try:
                import json

                parsed = json.loads(normalized)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except json.JSONDecodeError:
                return [normalized]
        return [normalized]
    return [str(value)]


class ProviderKind(StrEnum):
    GITHUB = "github"
    GITLAB = "gitlab"


class ProviderIntegrationStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class SecretBackend(StrEnum):
    AWS_SECRETS_MANAGER = "aws_secrets_manager"


class ProjectApiKeyStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class AutonomyMode(StrEnum):
    OBSERVE = "observe"
    RECOMMEND = "recommend"
    SUPERVISED_EXECUTE = "supervised_execute"
    AUTONOMOUS = "autonomous"


class RuntimeKind(StrEnum):
    GENERIC = "generic"
    PYTHON = "python"
    NODE = "node"
    CONTAINER = "container"


class ProviderIntegrationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    provider: ProviderKind
    name: str
    status: ProviderIntegrationStatus
    credentials_secret_ref_id: str | None = None
    webhook_secret_ref_id: str | None = None
    aws_region: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_db_row(cls, row: Any) -> "ProviderIntegrationRecord":
        metadata = row["metadata"]
        if not isinstance(metadata, dict):
            metadata = {}
        return cls(
            id=str(row["id"]),
            provider=ProviderKind(str(row["provider"])),
            name=str(row["name"]),
            status=ProviderIntegrationStatus(str(row["status"])),
            credentials_secret_ref_id=(
                str(row["credentials_secret_ref_id"])
                if row["credentials_secret_ref_id"] is not None
                else None
            ),
            webhook_secret_ref_id=(
                str(row["webhook_secret_ref_id"])
                if row["webhook_secret_ref_id"] is not None
                else None
            ),
            aws_region=row["aws_region"],
            metadata=metadata,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class ProviderRepositoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    provider_integration_id: str
    provider: ProviderKind
    external_repository_id: str
    owner: str
    name: str
    default_branch: str
    clone_url: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_db_row(cls, row: Any) -> "ProviderRepositoryRecord":
        return cls(
            id=str(row["id"]),
            provider_integration_id=str(row["provider_integration_id"]),
            provider=ProviderKind(str(row["provider"])),
            external_repository_id=str(row["external_repository_id"]),
            owner=str(row["owner"]),
            name=str(row["name"]),
            default_branch=str(row["default_branch"]),
            clone_url=str(row["clone_url"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class SecretRefRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    label: str
    description: str | None = None
    backend: SecretBackend
    external_ref: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_db_row(cls, row: Any) -> "SecretRefRecord":
        return cls(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            label=str(row["label"]),
            description=row["description"],
            backend=SecretBackend(str(row["backend"])),
            external_ref=str(row["external_ref"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class ProjectApiKeyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    name: str
    key_prefix: str
    key_hash: str
    status: ProjectApiKeyStatus
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_db_row(cls, row: Any) -> "ProjectApiKeyRecord":
        return cls(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            name=str(row["name"]),
            key_prefix=str(row["key_prefix"]),
            key_hash=str(row["key_hash"]),
            status=ProjectApiKeyStatus(str(row["status"])),
            last_used_at=row["last_used_at"],
            revoked_at=row["revoked_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class ProjectPolicyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    autonomy_mode: AutonomyMode
    require_human_approval: bool
    allow_production_writes: bool
    allow_low_risk_autonomy: bool
    block_during_active_deploys: bool
    restrict_to_approved_services: bool
    require_rollback_plan: bool
    require_post_action_verification: bool
    approved_services: list[str] = Field(default_factory=list)
    failure_classifier_enabled: bool
    root_cause_enabled: bool
    patch_planner_enabled: bool
    runbook_executor_enabled: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_db_row(cls, row: Any) -> "ProjectPolicyRecord":
        return cls(
            project_id=str(row["project_id"]),
            autonomy_mode=AutonomyMode(str(row["autonomy_mode"])),
            require_human_approval=bool(row["require_human_approval"]),
            allow_production_writes=bool(row["allow_production_writes"]),
            allow_low_risk_autonomy=bool(row["allow_low_risk_autonomy"]),
            block_during_active_deploys=bool(row["block_during_active_deploys"]),
            restrict_to_approved_services=bool(row["restrict_to_approved_services"]),
            require_rollback_plan=bool(row["require_rollback_plan"]),
            require_post_action_verification=bool(row["require_post_action_verification"]),
            approved_services=_decode_json_array(row["approved_services"]),
            failure_classifier_enabled=bool(row["failure_classifier_enabled"]),
            root_cause_enabled=bool(row["root_cause_enabled"]),
            patch_planner_enabled=bool(row["patch_planner_enabled"]),
            runbook_executor_enabled=bool(row["runbook_executor_enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class RepoProfileRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    provider_repository_id: str
    runtime_kind: RuntimeKind
    base_image: str | None = None
    install_command: str | None = None
    startup_commands: list[str] = Field(default_factory=list)
    reproduce_command: str
    verify_command: str
    success_criteria: str | None = None
    network_allowlist: list[str] = Field(default_factory=list)
    active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_db_row(cls, row: Any) -> "RepoProfileRecord":
        return cls(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            provider_repository_id=str(row["provider_repository_id"]),
            runtime_kind=RuntimeKind(str(row["runtime_kind"])),
            base_image=row["base_image"],
            install_command=row["install_command"],
            startup_commands=_decode_json_array(row["startup_commands"]),
            reproduce_command=str(row["reproduce_command"]),
            verify_command=str(row["verify_command"]),
            success_criteria=row["success_criteria"],
            network_allowlist=_decode_json_array(row["network_allowlist"]),
            active=bool(row["active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class RepoProfileSecretRefRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo_profile_id: str
    secret_ref_id: str
    mount_as: str
    created_at: datetime

    @classmethod
    def from_db_row(cls, row: Any) -> "RepoProfileSecretRefRecord":
        return cls(
            repo_profile_id=str(row["repo_profile_id"]),
            secret_ref_id=str(row["secret_ref_id"]),
            mount_as=str(row["mount_as"]),
            created_at=row["created_at"],
        )


class RepoProfileSecretBindingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo_profile_id: str
    mount_as: str
    secret_ref: SecretRefRecord
    created_at: datetime

    @classmethod
    def from_db_row(cls, row: Any) -> "RepoProfileSecretBindingRecord":
        binding_created_at = row["binding_created_at"] if "binding_created_at" in row else row["created_at"]
        return cls(
            repo_profile_id=str(row["repo_profile_id"]),
            mount_as=str(row["mount_as"]),
            secret_ref=SecretRefRecord.from_db_row(row),
            created_at=binding_created_at,
        )
