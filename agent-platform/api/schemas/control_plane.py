from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.control_plane import (
    AutonomyMode,
    ProjectServiceDependencyKind,
    ProjectServiceDependencyRecord,
    ProjectServiceRecord,
    ProjectServiceRoutingHints,
    ProjectServiceType,
    ProjectApiKeyRecord,
    ProjectApiKeyStatus,
    ProjectPolicyRecord,
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


class CreateSecretRefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)
    value: str = Field(min_length=1, max_length=10_000)

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("secret value must not be blank")
        return normalized

    @field_validator("project_id", "label")
    @classmethod
    def validate_projectish_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class SecretRefResponse(BaseModel):
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
    def from_record(cls, record: SecretRefRecord) -> "SecretRefResponse":
        return cls(**record.model_dump(mode="json"))


class CreateProjectApiKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized


class ProjectApiKeyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    name: str
    key_prefix: str
    status: ProjectApiKeyStatus
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: ProjectApiKeyRecord) -> "ProjectApiKeyResponse":
        payload = record.model_dump(mode="json")
        payload.pop("key_hash", None)
        return cls(**payload)


class ProjectApiKeyCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: ProjectApiKeyResponse
    plaintext_key: str


class ProjectPolicyResponse(BaseModel):
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
    def from_record(cls, record: ProjectPolicyRecord) -> "ProjectPolicyResponse":
        return cls(**record.model_dump(mode="json"))


class UpdateProjectPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    autonomy_mode: AutonomyMode
    require_human_approval: bool
    allow_production_writes: bool
    allow_low_risk_autonomy: bool
    block_during_active_deploys: bool
    restrict_to_approved_services: bool
    require_rollback_plan: bool
    require_post_action_verification: bool
    approved_services: list[str] = Field(default_factory=list, max_length=50)
    failure_classifier_enabled: bool
    root_cause_enabled: bool
    patch_planner_enabled: bool
    runbook_executor_enabled: bool


class CreateProviderIntegrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderKind
    name: str = Field(min_length=1, max_length=200)
    aws_region: str | None = Field(default=None, max_length=64)
    credentials_secret_ref_id: str | None = None
    webhook_secret_ref_id: str | None = None


class ProviderIntegrationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    provider: ProviderKind
    name: str
    status: ProviderIntegrationStatus
    credentials_secret_ref_id: str | None = None
    webhook_secret_ref_id: str | None = None
    aws_region: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: ProviderIntegrationRecord) -> "ProviderIntegrationResponse":
        return cls(**record.model_dump(mode="json"))


class CreateGitHubAppIntegrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    installation_id: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("project_id", "name")
    @classmethod
    def validate_nonempty_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class StartGitLabOAuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    gitlab_base_url: str | None = Field(default=None, max_length=500)

    @field_validator("project_id", "name")
    @classmethod
    def validate_nonempty_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class ProviderInstallationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_id: str
    account_login: str
    account_type: str | None = None
    account_name: str | None = None


class GitLabOAuthStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    integration: ProviderIntegrationResponse
    authorization_url: str


class GitLabOAuthCallbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    integration: ProviderIntegrationResponse
    credentials_secret_ref: SecretRefResponse
    connected_account: ProviderInstallationResponse


class GitHubCallbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderKind = ProviderKind.GITHUB
    installation_id: str
    setup_action: str | None = None
    account_login: str
    account_type: str | None = None
    account_name: str | None = None


class ProviderRepositorySyncResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    integration: ProviderIntegrationResponse
    repositories: list["ProviderRepositoryResponse"] = Field(default_factory=list)


class ProviderWebhookResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderKind
    event: str
    delivery_id: str | None = None
    status: str


class CreateProviderRepositoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_integration_id: str
    provider: ProviderKind
    external_repository_id: str = Field(min_length=1, max_length=512)
    owner: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=256)
    default_branch: str = Field(min_length=1, max_length=256)
    clone_url: str = Field(min_length=1, max_length=2_000)


class ProviderRepositoryResponse(BaseModel):
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
    def from_record(cls, record: ProviderRepositoryRecord) -> "ProviderRepositoryResponse":
        return cls(**record.model_dump(mode="json"))


class CreateRepoProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=128)
    provider_repository_id: str
    runtime_kind: RuntimeKind
    base_image: str | None = Field(default=None, max_length=500)
    install_command: str | None = Field(default=None, max_length=2_000)
    startup_commands: list[str] = Field(default_factory=list, max_length=20)
    reproduce_command: str = Field(min_length=1, max_length=2_000)
    verify_command: str = Field(min_length=1, max_length=2_000)
    success_criteria: str | None = Field(default=None, max_length=1_000)
    network_allowlist: list[str] = Field(default_factory=list, max_length=50)
    secret_ref_ids: list[str] = Field(default_factory=list, max_length=50)
    secret_mounts: list["RepoProfileSecretMountRequest"] = Field(default_factory=list, max_length=50)

    @field_validator(
        "project_id",
        "provider_repository_id",
        "reproduce_command",
        "verify_command",
        mode="before",
    )
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("value must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("base_image", "install_command", "success_criteria", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("startup_commands", "network_allowlist", mode="before")
    @classmethod
    def normalize_string_list(cls, value: list[str]) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("value must be a list")
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]


class RepoProfileSecretMountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    secret_ref_id: str
    mount_as: str = Field(min_length=1, max_length=512)

    @field_validator("mount_as")
    @classmethod
    def validate_mount_as(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("mount path must not be blank")
        if ".." in normalized.split("/"):
            raise ValueError("mount path must not contain parent directory traversal")
        if "/" not in normalized and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", normalized):
            raise ValueError("environment variable mounts must be valid shell variable names")
        return normalized


class ProjectBootstrapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=128)

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("project id must not be blank")
        return normalized


class ProjectServiceRoutingHintsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_names: list[str] = Field(default_factory=list, max_length=50)
    path_prefixes: list[str] = Field(default_factory=list, max_length=50)
    domains: list[str] = Field(default_factory=list, max_length=50)
    tags: list[str] = Field(default_factory=list, max_length=50)

    def to_record(self) -> ProjectServiceRoutingHints:
        return ProjectServiceRoutingHints(**self.model_dump())


class ProjectServiceDependencyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    depends_on_service_id: str = Field(min_length=1, max_length=128)
    dependency_kind: ProjectServiceDependencyKind = ProjectServiceDependencyKind.REQUIRED


class CreateProjectServiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=200)
    service_type: ProjectServiceType = ProjectServiceType.OTHER
    repo_profile_id: str | None = None
    owner: str | None = Field(default=None, max_length=200)
    deploy_target: str | None = Field(default=None, max_length=200)
    routing_hints: ProjectServiceRoutingHintsPayload = Field(default_factory=ProjectServiceRoutingHintsPayload)
    startup_priority: int = Field(default=100, ge=0, le=10_000)
    sandbox_healthcheck_command: str | None = Field(default=None, max_length=2_000)
    sandbox_healthcheck_url: str | None = Field(default=None, max_length=2_000)
    active: bool = True
    dependencies: list[ProjectServiceDependencyRequest] = Field(default_factory=list, max_length=50)

    @field_validator("project_id", "name", "slug", mode="before")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("value must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class UpdateProjectServiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=200)
    service_type: ProjectServiceType = ProjectServiceType.OTHER
    repo_profile_id: str | None = None
    owner: str | None = Field(default=None, max_length=200)
    deploy_target: str | None = Field(default=None, max_length=200)
    routing_hints: ProjectServiceRoutingHintsPayload = Field(default_factory=ProjectServiceRoutingHintsPayload)
    startup_priority: int = Field(default=100, ge=0, le=10_000)
    sandbox_healthcheck_command: str | None = Field(default=None, max_length=2_000)
    sandbox_healthcheck_url: str | None = Field(default=None, max_length=2_000)
    active: bool = True
    dependencies: list[ProjectServiceDependencyRequest] = Field(default_factory=list, max_length=50)


class ProjectServiceDependencyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    depends_on_service_id: str
    dependency_kind: ProjectServiceDependencyKind

    @classmethod
    def from_record(
        cls,
        record: ProjectServiceDependencyRecord,
    ) -> "ProjectServiceDependencyResponse":
        return cls(
            depends_on_service_id=record.depends_on_service_id,
            dependency_kind=record.dependency_kind,
        )


class ProjectServiceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    name: str
    slug: str
    service_type: ProjectServiceType
    repo_profile_id: str | None = None
    owner: str | None = None
    deploy_target: str | None = None
    routing_hints: ProjectServiceRoutingHintsPayload = Field(default_factory=ProjectServiceRoutingHintsPayload)
    startup_priority: int
    sandbox_healthcheck_command: str | None = None
    sandbox_healthcheck_url: str | None = None
    active: bool
    dependencies: list[ProjectServiceDependencyResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(
        cls,
        record: ProjectServiceRecord,
        *,
        dependencies: list[ProjectServiceDependencyRecord] | None = None,
    ) -> "ProjectServiceResponse":
        return cls(
            **record.model_dump(mode="json"),
            routing_hints=ProjectServiceRoutingHintsPayload(**record.routing_hints.model_dump(mode="json")),
            dependencies=[
                ProjectServiceDependencyResponse.from_record(item).model_dump(mode="json")
                for item in (dependencies or [])
            ],
        )


class SandboxPlanServiceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: ProjectServiceResponse
    repo_profile: RepoProfileResponse | None = None
    startup_commands: list[str] = Field(default_factory=list)
    healthcheck_command: str | None = None
    healthcheck_url: str | None = None


class ProjectSandboxPlanPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    target_service: SandboxPlanServiceResponse
    dependency_services: list[SandboxPlanServiceResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RepoProfileSecretMountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mount_as: str
    secret_ref: SecretRefResponse

    @classmethod
    def from_record(
        cls,
        record: RepoProfileSecretBindingRecord,
    ) -> "RepoProfileSecretMountResponse":
        return cls(
            mount_as=record.mount_as,
            secret_ref=SecretRefResponse.from_record(record.secret_ref),
        )


class RepoProfileResponse(BaseModel):
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
    secret_refs: list[SecretRefResponse] = Field(default_factory=list)
    secret_mounts: list[RepoProfileSecretMountResponse] = Field(default_factory=list)
    active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(
        cls,
        record: RepoProfileRecord,
        *,
        secret_mounts: list[RepoProfileSecretBindingRecord] | None = None,
    ) -> "RepoProfileResponse":
        payload = record.model_dump(mode="json")
        mounts = secret_mounts or []
        payload["secret_refs"] = [
            SecretRefResponse.from_record(binding.secret_ref).model_dump(mode="json")
            for binding in mounts
        ]
        payload["secret_mounts"] = [
            RepoProfileSecretMountResponse.from_record(binding).model_dump(mode="json")
            for binding in mounts
        ]
        return cls(**payload)


class ProviderIntegrationOnboardingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    integration: ProviderIntegrationResponse
    repositories: list[ProviderRepositoryResponse] = Field(default_factory=list)


class ProjectOnboardingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    policy: ProjectPolicyResponse
    secret_refs: list[SecretRefResponse] = Field(default_factory=list)
    api_keys: list[ProjectApiKeyResponse] = Field(default_factory=list)
    integrations: list[ProviderIntegrationOnboardingResponse] = Field(default_factory=list)
    repo_profiles: list[RepoProfileResponse] = Field(default_factory=list)
    project_services: list[ProjectServiceResponse] = Field(default_factory=list)
    suggested_next_steps: list[str] = Field(default_factory=list)
