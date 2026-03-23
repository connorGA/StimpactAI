from __future__ import annotations

import time
from urllib.parse import quote

from api.core.config import (
    get_github_api_base_url,
    get_github_app_id,
    get_github_installation_id,
    get_github_private_key,
)
from api.core.errors import APIError
from models.control_plane import ProviderKind, ProviderRepositoryRecord
from models.control_plane import ProviderIntegrationRecord, SecretRefRecord
from services.provider_clients import (
    ProviderChangeRequest,
    ProviderInstallation,
    ProviderRepositoryMetadata,
    ProviderSandboxAccess,
    apply_patch_and_push_branch,
)
from services.repository_provider import RepositorySnapshot


class GitHubAdapter:
    provider = ProviderKind.GITHUB

    def build_snapshot(
        self,
        *,
        repository: ProviderRepositoryRecord,
        target_commit_sha: str | None,
    ) -> RepositorySnapshot:
        return RepositorySnapshot(
            provider=self.provider,
            clone_url=repository.clone_url,
            owner=repository.owner,
            repository_name=repository.name,
            default_branch=repository.default_branch,
            target_commit_sha=target_commit_sha,
        )

    def build_branch_name(self, *, incident_id: str) -> str:
        return f"stimpact/fix/{incident_id}"

    def build_change_request_url(
        self,
        *,
        repository: ProviderRepositoryRecord,
        branch_name: str,
    ) -> str:
        return (
            f"https://github.com/{repository.owner}/{repository.name}"
            f"/compare/{repository.default_branch}...{branch_name}?expand=1"
        )


class GitHubProviderClient:
    provider = ProviderKind.GITHUB

    def __init__(self, *, api_base_url: str | None = None) -> None:
        self._api_base_url = (api_base_url or get_github_api_base_url()).rstrip("/")

    async def verify_integration(
        self,
        integration: ProviderIntegrationRecord,
        *,
        credentials_secret_ref: SecretRefRecord | None = None,
    ) -> ProviderInstallation:
        _ = credentials_secret_ref
        installation_id = self._get_installation_id(integration)
        payload = await self._request_as_app("GET", f"/app/installations/{installation_id}")
        account = payload.get("account", {})
        return ProviderInstallation(
            external_id=str(payload.get("id", installation_id)),
            account_login=str(account.get("login", "")),
            account_type=str(account.get("type")) if account.get("type") is not None else None,
            account_name=str(account.get("login", "")) or None,
        )

    async def list_repositories(
        self,
        integration: ProviderIntegrationRecord,
        *,
        credentials_secret_ref: SecretRefRecord | None = None,
    ) -> list[ProviderRepositoryMetadata]:
        _ = credentials_secret_ref
        installation_token = await self._create_installation_token(self._get_installation_id(integration))
        payload = await self._request_with_bearer(
            "GET",
            "/installation/repositories?per_page=100",
            token=installation_token,
        )
        repositories: list[ProviderRepositoryMetadata] = []
        for item in payload.get("repositories", []):
            if not isinstance(item, dict):
                continue
            owner = item.get("owner", {})
            repositories.append(
                ProviderRepositoryMetadata(
                    external_repository_id=str(item.get("id", "")),
                    owner=str(owner.get("login", "")),
                    name=str(item.get("name", "")),
                    default_branch=str(item.get("default_branch", "main")),
                    clone_url=str(item.get("clone_url", "")),
                )
            )
        return repositories

    async def build_sandbox_access(
        self,
        integration: ProviderIntegrationRecord,
        repository: ProviderRepositoryRecord,
        *,
        credentials_secret_ref: SecretRefRecord | None = None,
    ) -> ProviderSandboxAccess:
        _ = credentials_secret_ref
        installation_token = await self._create_installation_token(self._get_installation_id(integration))
        authenticated_clone_url = self._build_authenticated_clone_url(
            repository.clone_url,
            token=installation_token,
        )
        return ProviderSandboxAccess(
            secret_value=authenticated_clone_url,
            secret_format="text",
        )

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
        credentials_secret_ref: SecretRefRecord | None = None,
    ) -> ProviderChangeRequest:
        _ = credentials_secret_ref
        installation_token = await self._create_installation_token(self._get_installation_id(integration))
        authenticated_clone_url = self._build_authenticated_clone_url(repository.clone_url, token=installation_token)
        commit_sha = apply_patch_and_push_branch(
            clone_url=authenticated_clone_url,
            default_branch=repository.default_branch,
            branch_name=branch_name,
            patch_diff=patch_diff,
            commit_message=commit_message,
        )
        payload = await self._request_with_bearer(
            "POST",
            f"/repos/{repository.owner}/{repository.name}/pulls",
            token=installation_token,
            json_body={
                "title": title,
                "head": branch_name,
                "base": repository.default_branch,
                "body": description,
            },
        )
        return ProviderChangeRequest(
            branch_name=branch_name,
            commit_sha=commit_sha,
            change_request_url=str(payload.get("html_url") or self._build_compare_url(repository, branch_name)),
            reference_id=str(payload.get("number")) if payload.get("number") is not None else None,
            mergeable=payload.get("mergeable") if isinstance(payload.get("mergeable"), bool) else None,
        )

    def _get_installation_id(self, integration: ProviderIntegrationRecord) -> str:
        metadata_value = integration.metadata.get("installation_id")
        if metadata_value is not None and str(metadata_value).strip():
            return str(metadata_value).strip()
        env_value = get_github_installation_id()
        if env_value is not None:
            return env_value
        raise APIError(
            "GitHub installation id is not configured.",
            status_code=503,
            code="github_unconfigured",
        )

    def _build_app_jwt(self) -> str:
        app_id = get_github_app_id()
        private_key = get_github_private_key()
        if app_id is None or private_key is None:
            raise APIError(
                "GitHub App credentials are not configured.",
                status_code=503,
                code="github_unconfigured",
            )
        try:
            import jwt  # type: ignore
        except ImportError as exc:
            raise APIError(
                "PyJWT is not installed for GitHub App integration.",
                status_code=503,
                code="github_sdk_unavailable",
            ) from exc

        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + 540,
            "iss": app_id,
        }
        token = jwt.encode(payload, private_key, algorithm="RS256")
        return str(token)

    async def _create_installation_token(self, installation_id: str) -> str:
        payload = await self._request_as_app(
            "POST",
            f"/app/installations/{installation_id}/access_tokens",
        )
        token = payload.get("token")
        if not isinstance(token, str) or not token.strip():
            raise APIError(
                "GitHub installation token response was invalid.",
                status_code=502,
                code="github_token_exchange_failed",
            )
        return token

    async def _request_as_app(self, method: str, path: str) -> dict[str, object]:
        return await self._request(
            method,
            path,
            headers={
                "Authorization": f"Bearer {self._build_app_jwt()}",
                "Accept": "application/vnd.github+json",
            },
        )

    async def _request_with_bearer(
        self,
        method: str,
        path: str,
        *,
        token: str,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return await self._request(
            method,
            path,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            json_body=json_body,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        try:
            import httpx  # type: ignore
        except ImportError as exc:
            raise APIError(
                "httpx is not installed for provider integration.",
                status_code=503,
                code="provider_sdk_unavailable",
            ) from exc

        url = f"{self._api_base_url}{path}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.request(method, url, headers=headers, json=json_body)
        if response.status_code >= 400:
            raise APIError(
                f"GitHub API request failed with status {response.status_code}.",
                status_code=502,
                code="github_api_request_failed",
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise APIError(
                "GitHub API returned an unexpected payload.",
                status_code=502,
                code="github_api_request_failed",
            )
        return payload

    def _build_compare_url(self, repository: ProviderRepositoryRecord, branch_name: str) -> str:
        return (
            f"https://github.com/{repository.owner}/{repository.name}"
            f"/compare/{repository.default_branch}...{branch_name}?expand=1"
        )

    def _build_authenticated_clone_url(self, clone_url: str, *, token: str) -> str:
        normalized = clone_url.strip()
        if normalized.startswith("https://"):
            return normalized.replace(
                "https://",
                f"https://x-access-token:{quote(token, safe='')}@",
                1,
            )
        return normalized
