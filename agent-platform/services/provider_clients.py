from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from api.core.errors import APIError
from models.control_plane import ProviderIntegrationRecord, ProviderKind, ProviderRepositoryRecord, SecretRefRecord


@dataclass(slots=True)
class ProviderInstallation:
    external_id: str
    account_login: str
    account_type: str | None = None
    account_name: str | None = None


@dataclass(slots=True)
class ProviderRepositoryMetadata:
    external_repository_id: str
    owner: str
    name: str
    default_branch: str
    clone_url: str


@dataclass(slots=True)
class ProviderSandboxAccess:
    secret_value: str
    secret_format: str = "json"


@dataclass(slots=True)
class GitLabAuthorization:
    authorization_url: str
    state: str


class ProviderClient(Protocol):
    provider: ProviderKind

    async def verify_integration(
        self,
        integration: ProviderIntegrationRecord,
        *,
        credentials_secret_ref: SecretRefRecord | None = None,
    ) -> ProviderInstallation: ...

    async def list_repositories(
        self,
        integration: ProviderIntegrationRecord,
        *,
        credentials_secret_ref: SecretRefRecord | None = None,
    ) -> list[ProviderRepositoryMetadata]: ...

    async def build_sandbox_access(
        self,
        integration: ProviderIntegrationRecord,
        repository: ProviderRepositoryRecord,
        *,
        credentials_secret_ref: SecretRefRecord | None = None,
    ) -> ProviderSandboxAccess: ...


def get_provider_client(provider: ProviderKind) -> ProviderClient:
    if provider is ProviderKind.GITHUB:
        from services.github_provider import GitHubProviderClient

        return GitHubProviderClient()
    if provider is ProviderKind.GITLAB:
        from services.gitlab_provider import GitLabProviderClient

        return GitLabProviderClient()
    raise APIError(
        f"Unsupported git provider {provider.value}.",
        status_code=400,
        code="unsupported_provider",
    )
