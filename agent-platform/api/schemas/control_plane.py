from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.control_plane import (
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


class StartGitLabOAuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    gitlab_base_url: str | None = Field(default=None, max_length=500)


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


class RepoProfileSecretMountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    secret_ref_id: str
    mount_as: str = Field(min_length=1, max_length=512)


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
