from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import quote_plus, urlencode

from api.core.config import (
    get_gitlab_application_id,
    get_gitlab_app_secret,
    get_gitlab_base_url,
    get_gitlab_callback_url,
    get_gitlab_oauth_scopes,
)
from api.core.errors import APIError
from models.control_plane import ProviderIntegrationRecord, SecretRefRecord
from services.aws_secrets_manager import AwsSecretsManagerReader, AwsSecretsManagerWriter
from services.provider_clients import (
    GitLabAuthorization,
    ProviderChangeRequest,
    ProviderInstallation,
    ProviderRepositoryMetadata,
    ProviderSandboxAccess,
    apply_patch_and_push_branch,
)

from models.control_plane import ProviderKind, ProviderRepositoryRecord
from services.repository_provider import RepositorySnapshot


class GitLabAdapter:
    provider = ProviderKind.GITLAB

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
        encoded_project = quote_plus(f"{repository.owner}/{repository.name}")
        encoded_branch = quote_plus(branch_name)
        encoded_target = quote_plus(repository.default_branch)
        return (
            f"https://gitlab.com/{repository.owner}/{repository.name}/-/merge_requests/new"
            f"?merge_request%5Bsource_branch%5D={encoded_branch}"
            f"&merge_request%5Btarget_branch%5D={encoded_target}"
            f"&project_id={encoded_project}"
        )


class GitLabProviderClient:
    provider = ProviderKind.GITLAB

    def __init__(
        self,
        *,
        base_url: str | None = None,
        secrets_reader: AwsSecretsManagerReader | None = None,
        secrets_writer: AwsSecretsManagerWriter | None = None,
    ) -> None:
        self._base_url = (base_url or get_gitlab_base_url()).rstrip("/")
        self._secrets_reader = secrets_reader or AwsSecretsManagerReader()
        self._secrets_writer = secrets_writer or AwsSecretsManagerWriter()

    def build_authorization(self, *, state: str, base_url: str | None = None) -> GitLabAuthorization:
        client_id = get_gitlab_application_id()
        callback_url = get_gitlab_callback_url()
        if client_id is None or callback_url is None:
            raise APIError(
                "GitLab OAuth application is not configured.",
                status_code=503,
                code="gitlab_unconfigured",
            )
        resolved_base_url = (base_url or self._base_url).rstrip("/")
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": callback_url,
                "response_type": "code",
                "state": state,
                "scope": " ".join(get_gitlab_oauth_scopes()),
            }
        )
        return GitLabAuthorization(
            authorization_url=f"{resolved_base_url}/oauth/authorize?{query}",
            state=state,
        )

    async def exchange_code_for_token(
        self,
        *,
        code: str,
        base_url: str | None = None,
    ) -> dict[str, object]:
        client_id = get_gitlab_application_id()
        client_secret = get_gitlab_app_secret()
        callback_url = get_gitlab_callback_url()
        if client_id is None or client_secret is None or callback_url is None:
            raise APIError(
                "GitLab OAuth application is not configured.",
                status_code=503,
                code="gitlab_unconfigured",
            )
        resolved_base_url = (base_url or self._base_url).rstrip("/")
        payload = await self._request_token(
            resolved_base_url,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": callback_url,
            },
        )
        return self._normalize_token_payload(payload)

    async def get_current_user(self, *, access_token: str, base_url: str | None = None) -> ProviderInstallation:
        payload = await self._request_json(
            "GET",
            f"{(base_url or self._base_url).rstrip('/')}/api/v4/user",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return ProviderInstallation(
            external_id=str(payload.get("id", "")),
            account_login=str(payload.get("username", "")),
            account_type="user",
            account_name=str(payload.get("name", "")) or None,
        )

    async def verify_integration(
        self,
        integration: ProviderIntegrationRecord,
        *,
        credentials_secret_ref: SecretRefRecord | None = None,
    ) -> ProviderInstallation:
        secret_ref = self._require_credentials_secret_ref(
            credentials_secret_ref,
            integration=integration,
        )
        tokens = await self._ensure_valid_tokens(secret_ref, integration=integration)
        return await self.get_current_user(
            access_token=str(tokens["access_token"]),
            base_url=self._get_base_url_for_integration(integration),
        )

    async def list_repositories(
        self,
        integration: ProviderIntegrationRecord,
        *,
        credentials_secret_ref: SecretRefRecord | None = None,
    ) -> list[ProviderRepositoryMetadata]:
        secret_ref = self._require_credentials_secret_ref(
            credentials_secret_ref,
            integration=integration,
        )
        tokens = await self._ensure_valid_tokens(secret_ref, integration=integration)
        payload = await self._request_json(
            "GET",
            f"{self._get_base_url_for_integration(integration)}/api/v4/projects",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            params={"membership": "true", "simple": "true", "per_page": "100"},
        )
        if not isinstance(payload, list):
            raise APIError(
                "GitLab API returned an unexpected project payload.",
                status_code=502,
                code="gitlab_api_request_failed",
            )
        repositories: list[ProviderRepositoryMetadata] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            path_with_namespace = str(item.get("path_with_namespace", ""))
            owner = path_with_namespace.split("/", 1)[0] if "/" in path_with_namespace else path_with_namespace
            repositories.append(
                ProviderRepositoryMetadata(
                    external_repository_id=str(item.get("id", "")),
                    owner=owner,
                    name=str(item.get("path", item.get("name", ""))),
                    default_branch=str(item.get("default_branch", "main")),
                    clone_url=str(item.get("http_url_to_repo", "")),
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
        secret_ref = self._require_credentials_secret_ref(
            credentials_secret_ref,
            integration=integration,
        )
        tokens = await self._ensure_valid_tokens(secret_ref, integration=integration)
        clone_url = repository.clone_url
        if clone_url.startswith("https://"):
            clone_url = clone_url.replace(
                "https://",
                f"https://oauth2:{quote_plus(str(tokens['access_token']))}@",
                1,
            )
        return ProviderSandboxAccess(
            secret_value=clone_url,
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
        secret_ref = self._require_credentials_secret_ref(
            credentials_secret_ref,
            integration=integration,
        )
        tokens = await self._ensure_valid_tokens(secret_ref, integration=integration)
        clone_url = repository.clone_url
        if clone_url.startswith("https://"):
            clone_url = clone_url.replace(
                "https://",
                f"https://oauth2:{quote_plus(str(tokens['access_token']))}@",
                1,
            )
        commit_sha = apply_patch_and_push_branch(
            clone_url=clone_url,
            default_branch=repository.default_branch,
            branch_name=branch_name,
            patch_diff=patch_diff,
            commit_message=commit_message,
        )
        payload = await self._request_json(
            "POST",
            f"{self._get_base_url_for_integration(integration)}/api/v4/projects/{quote_plus(repository.external_repository_id)}/merge_requests",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            data={
                "source_branch": branch_name,
                "target_branch": repository.default_branch,
                "title": title,
                "description": description,
            },
        )
        if not isinstance(payload, dict):
            raise APIError(
                "GitLab merge request response was invalid.",
                status_code=502,
                code="gitlab_api_request_failed",
            )
        return ProviderChangeRequest(
            branch_name=branch_name,
            commit_sha=commit_sha,
            change_request_url=str(payload.get("web_url") or self._build_fallback_mr_url(repository, branch_name)),
            reference_id=str(payload.get("iid")) if payload.get("iid") is not None else None,
            mergeable=payload.get("merge_status") == "can_be_merged" if payload.get("merge_status") is not None else None,
        )

    def _require_credentials_secret_ref(
        self,
        secret_ref: SecretRefRecord | None,
        *,
        integration: ProviderIntegrationRecord,
    ) -> SecretRefRecord:
        if secret_ref is None:
            raise APIError(
                f"GitLab integration {integration.id} is not fully connected.",
                status_code=400,
                code="gitlab_integration_not_connected",
            )
        return secret_ref

    def _get_base_url_for_integration(self, integration: ProviderIntegrationRecord) -> str:
        metadata_base_url = integration.metadata.get("gitlab_base_url")
        if metadata_base_url is not None and str(metadata_base_url).strip():
            return str(metadata_base_url).rstrip("/")
        return self._base_url

    async def _ensure_valid_tokens(
        self,
        secret_ref: SecretRefRecord,
        *,
        integration: ProviderIntegrationRecord,
    ) -> dict[str, object]:
        raw_value = self._secrets_reader.get_secret(external_ref=secret_ref.external_ref)
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise APIError(
                "Stored GitLab OAuth token payload is invalid.",
                status_code=502,
                code="gitlab_token_payload_invalid",
            ) from exc
        if not isinstance(payload, dict):
            raise APIError(
                "Stored GitLab OAuth token payload is invalid.",
                status_code=502,
                code="gitlab_token_payload_invalid",
            )

        expires_at_raw = payload.get("expires_at")
        if isinstance(expires_at_raw, str) and expires_at_raw:
            try:
                expires_at = datetime.fromisoformat(expires_at_raw.replace("Z", "+00:00"))
            except ValueError:
                expires_at = None
        else:
            expires_at = None

        if expires_at is not None and expires_at > datetime.now(UTC) + timedelta(seconds=60):
            return payload

        refresh_token = payload.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token.strip():
            return payload

        refreshed = await self._request_token(
            self._get_base_url_for_integration(integration),
            data={
                "client_id": get_gitlab_application_id(),
                "client_secret": get_gitlab_app_secret(),
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "redirect_uri": get_gitlab_callback_url(),
            },
        )
        normalized = self._normalize_token_payload(refreshed)
        self._secrets_writer.put_secret(
            project_id=secret_ref.project_id,
            label=secret_ref.label,
            value=json.dumps(normalized),
        )
        return normalized

    def _normalize_token_payload(self, payload: dict[str, object]) -> dict[str, object]:
        normalized = dict(payload)
        expires_in = normalized.get("expires_in")
        if isinstance(expires_in, int):
            expires_at = datetime.now(UTC) + timedelta(seconds=max(0, expires_in))
            normalized["expires_at"] = expires_at.isoformat()
        return normalized

    async def _request_token(self, base_url: str, *, data: dict[str, object]) -> dict[str, object]:
        payload = await self._request_json(
            "POST",
            f"{base_url}/oauth/token",
            data={key: str(value) for key, value in data.items() if value is not None},
        )
        if not isinstance(payload, dict):
            raise APIError(
                "GitLab token endpoint returned an unexpected payload.",
                status_code=502,
                code="gitlab_token_exchange_failed",
            )
        return payload

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
    ):
        try:
            import httpx  # type: ignore
        except ImportError as exc:
            raise APIError(
                "httpx is not installed for provider integration.",
                status_code=503,
                code="provider_sdk_unavailable",
            ) from exc

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.request(
                method,
                url,
                headers=headers,
                params=params,
                data=data,
            )
        if response.status_code >= 400:
            raise APIError(
                f"GitLab API request failed with status {response.status_code}.",
                status_code=502,
                code="gitlab_api_request_failed",
            )
        return response.json()

    def _build_fallback_mr_url(self, repository: ProviderRepositoryRecord, branch_name: str) -> str:
        encoded_branch = quote_plus(branch_name)
        encoded_target = quote_plus(repository.default_branch)
        return (
            f"{self._base_url}/{repository.owner}/{repository.name}/-/merge_requests/new"
            f"?merge_request%5Bsource_branch%5D={encoded_branch}"
            f"&merge_request%5Btarget_branch%5D={encoded_target}"
        )
