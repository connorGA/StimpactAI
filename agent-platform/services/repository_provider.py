from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from api.core.errors import APIError
from models.control_plane import ProviderKind, ProviderRepositoryRecord


@dataclass(slots=True)
class RepositorySnapshot:
    provider: ProviderKind
    clone_url: str
    owner: str
    repository_name: str
    default_branch: str
    target_commit_sha: str | None


class GitProviderAdapter(Protocol):
    provider: ProviderKind

    def build_snapshot(
        self,
        *,
        repository: ProviderRepositoryRecord,
        target_commit_sha: str | None,
    ) -> RepositorySnapshot: ...

    def build_branch_name(self, *, incident_id: str) -> str: ...

    def build_change_request_url(
        self,
        *,
        repository: ProviderRepositoryRecord,
        branch_name: str,
    ) -> str: ...


def get_provider_adapter(provider: ProviderKind) -> GitProviderAdapter:
    if provider is ProviderKind.GITHUB:
        from services.github_provider import GitHubAdapter

        return GitHubAdapter()
    if provider is ProviderKind.GITLAB:
        from services.gitlab_provider import GitLabAdapter

        return GitLabAdapter()
    raise APIError(
        f"Unsupported git provider {provider.value}.",
        status_code=400,
        code="unsupported_provider",
    )
