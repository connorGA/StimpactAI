from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import subprocess
import tempfile
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
class ProviderBranchMetadata:
    name: str
    commit_sha: str | None = None
    last_commit_at: datetime | None = None


@dataclass(slots=True)
class ProviderSandboxAccess:
    secret_value: str
    secret_format: str = "json"


@dataclass(slots=True)
class ProviderChangeRequest:
    branch_name: str
    commit_sha: str
    change_request_url: str
    reference_id: str | None = None
    mergeable: bool | None = None


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

    async def propose_patch(
        self,
        integration: ProviderIntegrationRecord,
        repository: ProviderRepositoryRecord,
        *,
        branch_name: str,
        patch_diff: str,
        title: str,
        description: str,
        commit_message: str,
        base_commit_sha: str | None = None,
        credentials_secret_ref: SecretRefRecord | None = None,
    ) -> ProviderChangeRequest: ...

    async def list_branches(
        self,
        integration: ProviderIntegrationRecord,
        repository: ProviderRepositoryRecord,
        *,
        credentials_secret_ref: SecretRefRecord | None = None,
        limit: int = 20,
    ) -> list[ProviderBranchMetadata]: ...


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


def apply_patch_and_push_branch(
    *,
    clone_url: str,
    default_branch: str,
    branch_name: str,
    patch_diff: str,
    commit_message: str,
    base_commit_sha: str | None = None,
    author_name: str = "Stimpact AI",
    author_email: str = "bot@stimpact.ai",
) -> str:
    with tempfile.TemporaryDirectory(prefix="stimpact-provider-writeback-") as temp_dir:
        repo_dir = Path(temp_dir) / "repo"
        _git(["clone", "--quiet", "--depth", "1", "--branch", default_branch, clone_url, str(repo_dir)])
        normalized_base_commit = base_commit_sha.strip() if base_commit_sha else None
        if normalized_base_commit:
            _checkout_writeback_base(repo_dir=repo_dir, base_commit_sha=normalized_base_commit)
            _git(["checkout", "-B", branch_name, normalized_base_commit], cwd=repo_dir)
        else:
            _git(["checkout", "-b", branch_name], cwd=repo_dir)

        patch_path = repo_dir / "stimpact.patch"
        normalized_patch = patch_diff if patch_diff.endswith("\n") else f"{patch_diff}\n"
        patch_path.write_text(normalized_patch, encoding="utf-8")

        _git(["apply", "--check", patch_path.name], cwd=repo_dir)
        _git(["apply", patch_path.name], cwd=repo_dir)

        status_output = _git(["status", "--porcelain"], cwd=repo_dir)
        if not status_output.strip():
            raise APIError(
                "Patch write-back produced no file changes to commit.",
                status_code=409,
                code="provider_writeback_empty_patch",
            )

        _git(["add", "-A"], cwd=repo_dir)
        _git(
            [
                "-c",
                f"user.name={author_name}",
                "-c",
                f"user.email={author_email}",
                "commit",
                "-m",
                commit_message,
            ],
            cwd=repo_dir,
        )
        commit_sha = _git(["rev-parse", "HEAD"], cwd=repo_dir).strip()
        _git(["push", "origin", f"HEAD:refs/heads/{branch_name}"], cwd=repo_dir)
        return commit_sha


def _checkout_writeback_base(*, repo_dir: Path, base_commit_sha: str) -> None:
    normalized_sha = base_commit_sha.strip()
    if not normalized_sha:
        return

    verify = subprocess.run(
        ["git", "rev-parse", "--verify", f"{normalized_sha}^{{commit}}"],
        cwd=repo_dir,
        check=False,
        capture_output=True,
        text=True,
    )
    if verify.returncode == 0:
        return

    fetch = subprocess.run(
        ["git", "fetch", "--quiet", "--depth", "1", "origin", normalized_sha],
        cwd=repo_dir,
        check=False,
        capture_output=True,
        text=True,
    )
    if fetch.returncode != 0:
        raise APIError(
            (
                fetch.stderr
                or fetch.stdout
                or f"Provider write-back could not fetch base commit {normalized_sha}."
            ).strip(),
            status_code=409,
            code="provider_writeback_base_unavailable",
        )


def _git(args: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise APIError(
            (result.stderr or result.stdout or "Git command failed.").strip(),
            status_code=502,
            code="provider_writeback_git_failed",
        )
    return (result.stdout or result.stderr).strip()
