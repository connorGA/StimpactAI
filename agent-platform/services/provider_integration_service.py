from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from api.core.config import (
    get_aws_region,
    get_github_installation_id,
    get_github_webhook_secret,
    get_gitlab_oauth_scopes,
)
from api.core.errors import APIError
from api.repositories.control_plane_repository import ControlPlaneRepository
from models.control_plane import (
    ProviderIntegrationRecord,
    ProviderIntegrationStatus,
    ProviderKind,
    ProviderRepositoryRecord,
    SecretBackend,
    SecretRefRecord,
)
from services.aws_secrets_manager import SecretsReader, SecretsWriter
from services.github_provider import GitHubProviderClient
from services.gitlab_provider import GitLabProviderClient
from services.provider_clients import ProviderInstallation, get_provider_client
from services.repo_profile_inference import RepoProfileInferenceResult, infer_repo_profile_from_clone


@dataclass(slots=True)
class GitHubCallbackPreview:
    installation_id: str
    setup_action: str | None
    account_login: str
    account_type: str | None
    account_name: str | None


@dataclass(slots=True)
class GitLabCallbackResult:
    integration: ProviderIntegrationRecord
    credentials_secret_ref: SecretRefRecord
    connected_account: ProviderInstallation


@dataclass(slots=True)
class GitHubCallbackResult:
    integration: ProviderIntegrationRecord
    connected_account: ProviderInstallation
    installation_id: str
    setup_action: str | None
    redirect_url: str | None
    synced_repository_count: int


@dataclass(slots=True)
class ProviderWritebackResult:
    branch_name: str
    commit_sha: str
    change_request_url: str
    reference_id: str | None = None
    mergeable: bool | None = None


class ProviderIntegrationService:
    def __init__(
        self,
        repository: ControlPlaneRepository,
        *,
        secrets_writer: SecretsWriter,
        secrets_reader: SecretsReader,
        github_client: GitHubProviderClient | None = None,
        gitlab_client: GitLabProviderClient | None = None,
    ) -> None:
        self._repository = repository
        self._secrets_writer = secrets_writer
        self._secrets_reader = secrets_reader
        self._github_client = github_client or GitHubProviderClient()
        self._gitlab_client = gitlab_client or GitLabProviderClient()

    async def create_github_app_integration(
        self,
        *,
        project_id: str,
        name: str,
        installation_id: str | None = None,
    ) -> tuple[ProviderIntegrationRecord, ProviderInstallation]:
        resolved_installation_id = installation_id or get_github_installation_id()
        if resolved_installation_id is None:
            raise APIError(
                "GitHub installation id is not configured.",
                status_code=400,
                code="github_installation_missing",
            )

        now = datetime.now(UTC)
        provisional = ProviderIntegrationRecord(
            id="provisional",
            provider=ProviderKind.GITHUB,
            name=name,
            status=ProviderIntegrationStatus.ACTIVE,
            credentials_secret_ref_id=None,
            webhook_secret_ref_id=None,
            aws_region=get_aws_region(),
            metadata={
                "project_id": project_id,
                "auth_mode": "github_app",
                "installation_id": str(resolved_installation_id),
            },
            created_at=now,
            updated_at=now,
        )
        installation = await self._github_client.verify_integration(provisional)
        metadata = {
            "project_id": project_id,
            "auth_mode": "github_app",
            "installation_id": str(resolved_installation_id),
            "account_login": installation.account_login,
            "account_type": installation.account_type,
            "account_name": installation.account_name,
        }
        integration = await self._repository.create_provider_integration(
            provider=ProviderKind.GITHUB,
            name=name,
            credentials_secret_ref_id=None,
            webhook_secret_ref_id=None,
            aws_region=get_aws_region(),
            metadata=metadata,
            status=ProviderIntegrationStatus.ACTIVE,
        )
        return integration, installation

    async def start_github_app_install(
        self,
        *,
        project_id: str,
        name: str,
        redirect_url: str,
    ) -> tuple[ProviderIntegrationRecord, str]:
        state = str(uuid4())
        existing_integrations = await self._repository.list_provider_integrations(project_id=project_id)
        existing_github_integration = next(
            (item for item in reversed(existing_integrations) if item.provider is ProviderKind.GITHUB),
            None,
        )
        metadata = {
            **(existing_github_integration.metadata if existing_github_integration is not None else {}),
            "project_id": project_id,
            "redirect_project_id": project_id,
            "auth_mode": "github_app",
            "install_state": state,
            "redirect_url": redirect_url,
        }
        if existing_github_integration is not None:
            integration = await self._repository.update_provider_integration(
                existing_github_integration.id,
                status=ProviderIntegrationStatus.DISABLED,
                credentials_secret_ref_id=existing_github_integration.credentials_secret_ref_id,
                webhook_secret_ref_id=existing_github_integration.webhook_secret_ref_id,
                aws_region=existing_github_integration.aws_region,
                metadata=metadata,
            )
        else:
            integration = await self._repository.create_provider_integration(
                provider=ProviderKind.GITHUB,
                name=name,
                credentials_secret_ref_id=None,
                webhook_secret_ref_id=None,
                aws_region=get_aws_region(),
                metadata=metadata,
                status=ProviderIntegrationStatus.DISABLED,
            )
        return integration, self._github_client.build_installation_url(state=state)

    async def preview_github_callback(
        self,
        *,
        installation_id: str | None,
        setup_action: str | None,
    ) -> GitHubCallbackPreview:
        resolved_installation_id = installation_id or get_github_installation_id()
        if resolved_installation_id is None:
            raise APIError(
                "GitHub installation id is not configured.",
                status_code=400,
                code="github_installation_missing",
            )
        now = datetime.now(UTC)
        provisional = ProviderIntegrationRecord(
            id="github-callback-preview",
            provider=ProviderKind.GITHUB,
            name="GitHub callback preview",
            status=ProviderIntegrationStatus.ACTIVE,
            credentials_secret_ref_id=None,
            webhook_secret_ref_id=None,
            aws_region=get_aws_region(),
            metadata={"installation_id": str(resolved_installation_id)},
            created_at=now,
            updated_at=now,
        )
        installation = await self._github_client.verify_integration(provisional)
        return GitHubCallbackPreview(
            installation_id=str(resolved_installation_id),
            setup_action=setup_action,
            account_login=installation.account_login,
            account_type=installation.account_type,
            account_name=installation.account_name,
        )

    async def complete_github_app_callback(
        self,
        *,
        state: str,
        installation_id: str,
        setup_action: str | None,
    ) -> GitHubCallbackResult:
        integration = await self._repository.find_provider_integration_by_metadata(
            provider=ProviderKind.GITHUB,
            metadata_key="install_state",
            metadata_value=state,
        )
        if integration is None:
            raise APIError(
                "GitHub App installation state was not recognized.",
                status_code=404,
                code="github_install_state_not_found",
            )

        metadata = dict(integration.metadata)
        redirect_url = str(metadata.get("redirect_url")) if metadata.get("redirect_url") is not None else None
        project_id = self._resolve_project_id(metadata)
        provisional = integration.model_copy(
            update={
                "status": ProviderIntegrationStatus.ACTIVE,
                "metadata": {
                    **metadata,
                    "project_id": project_id,
                    "auth_mode": "github_app",
                    "installation_id": installation_id,
                },
            }
        )
        connected_account = await self._github_client.verify_integration(provisional)

        metadata.pop("install_state", None)
        metadata["project_id"] = project_id
        metadata["auth_mode"] = "github_app"
        metadata["installation_id"] = installation_id
        metadata["account_login"] = connected_account.account_login
        metadata["account_type"] = connected_account.account_type
        metadata["account_name"] = connected_account.account_name

        updated = await self._repository.update_provider_integration(
            integration.id,
            status=ProviderIntegrationStatus.ACTIVE,
            credentials_secret_ref_id=integration.credentials_secret_ref_id,
            webhook_secret_ref_id=integration.webhook_secret_ref_id,
            aws_region=integration.aws_region,
            metadata=metadata,
        )
        _synced_integration, repositories = await self.sync_repositories(updated.id)
        return GitHubCallbackResult(
            integration=updated,
            connected_account=connected_account,
            installation_id=installation_id,
            setup_action=setup_action,
            redirect_url=redirect_url,
            synced_repository_count=len(repositories),
        )

    async def start_gitlab_oauth(
        self,
        *,
        project_id: str,
        name: str,
        gitlab_base_url: str | None = None,
    ) -> tuple[ProviderIntegrationRecord, str]:
        state = str(uuid4())
        authorization = self._gitlab_client.build_authorization(state=state, base_url=gitlab_base_url)
        metadata = {
            "project_id": project_id,
            "auth_mode": "gitlab_oauth",
            "gitlab_base_url": gitlab_base_url or self._gitlab_client._base_url,  # type: ignore[attr-defined]
            "oauth_state": state,
            "scopes": get_gitlab_oauth_scopes(),
        }
        integration = await self._repository.create_provider_integration(
            provider=ProviderKind.GITLAB,
            name=name,
            credentials_secret_ref_id=None,
            webhook_secret_ref_id=None,
            aws_region=get_aws_region(),
            metadata=metadata,
            status=ProviderIntegrationStatus.DISABLED,
        )
        return integration, authorization.authorization_url

    async def complete_gitlab_oauth_callback(self, *, state: str, code: str) -> GitLabCallbackResult:
        integration = await self._repository.find_provider_integration_by_metadata(
            provider=ProviderKind.GITLAB,
            metadata_key="oauth_state",
            metadata_value=state,
        )
        if integration is None:
            raise APIError(
                "GitLab OAuth state was not recognized.",
                status_code=404,
                code="gitlab_oauth_state_not_found",
            )

        project_id = self._require_project_id(integration)
        tokens = await self._gitlab_client.exchange_code_for_token(
            code=code,
            base_url=self._get_base_url(integration),
        )
        connected_account = await self._gitlab_client.get_current_user(
            access_token=str(tokens["access_token"]),
            base_url=self._get_base_url(integration),
        )
        existing_secret_ref = await self._load_credentials_secret_ref(integration)
        label = existing_secret_ref.label if existing_secret_ref is not None else f"gitlab-oauth-{integration.id}"
        external_ref = self._secrets_writer.put_secret(project_id=project_id, label=label, value=json.dumps(tokens))
        if existing_secret_ref is not None:
            secret_ref = existing_secret_ref
        else:
            secret_ref = await self._repository.create_secret_ref(
                project_id=project_id,
                label=label,
                description=f"GitLab OAuth credentials for integration {integration.id}",
                backend=SecretBackend.AWS_SECRETS_MANAGER,
                external_ref=external_ref,
            )
        metadata = dict(integration.metadata)
        metadata.pop("oauth_state", None)
        metadata["auth_mode"] = "gitlab_oauth"
        metadata["project_id"] = project_id
        metadata["gitlab_base_url"] = self._get_base_url(integration)
        metadata["connected_account_login"] = connected_account.account_login
        metadata["connected_account_id"] = connected_account.external_id
        updated = await self._repository.update_provider_integration(
            integration.id,
            status=ProviderIntegrationStatus.ACTIVE,
            credentials_secret_ref_id=secret_ref.id,
            webhook_secret_ref_id=integration.webhook_secret_ref_id,
            aws_region=integration.aws_region,
            metadata=metadata,
        )
        return GitLabCallbackResult(
            integration=updated,
            credentials_secret_ref=secret_ref,
            connected_account=connected_account,
        )

    async def sync_repositories(
        self,
        provider_integration_id: str,
    ) -> tuple[ProviderIntegrationRecord, list[ProviderRepositoryRecord]]:
        integration = await self._require_integration(provider_integration_id)
        credentials_secret_ref = await self._load_credentials_secret_ref(integration)
        client = get_provider_client(integration.provider)
        repositories = await client.list_repositories(
            integration,
            credentials_secret_ref=credentials_secret_ref,
        )
        stored_records: list[ProviderRepositoryRecord] = []
        for repository in repositories:
            stored_records.append(
                await self._repository.upsert_provider_repository(
                    provider_integration_id=integration.id,
                    provider=integration.provider,
                    external_repository_id=repository.external_repository_id,
                    owner=repository.owner,
                    name=repository.name,
                    default_branch=repository.default_branch,
                    clone_url=repository.clone_url,
                )
            )
        return integration, stored_records

    async def list_synced_repositories(self, provider_integration_id: str) -> list[ProviderRepositoryRecord]:
        return await self._repository.list_provider_repositories(provider_integration_id)

    async def build_sandbox_access_secret(
        self,
        *,
        project_id: str,
        sandbox_run_id: str,
        integration: ProviderIntegrationRecord,
        repository: ProviderRepositoryRecord,
    ) -> str | None:
        client = get_provider_client(integration.provider)
        credentials_secret_ref = await self._load_credentials_secret_ref(integration)
        access = await client.build_sandbox_access(
            integration,
            repository,
            credentials_secret_ref=credentials_secret_ref,
        )
        label = f"sandbox-git-access-{sandbox_run_id}"
        external_ref = self._secrets_writer.put_secret(
            project_id=project_id,
            label=label,
            value=access.secret_value,
        )
        return external_ref

    async def propose_patch_writeback(
        self,
        *,
        provider_repository_id: str,
        branch_name: str,
        patch_diff: str,
        title: str,
        description: str,
        commit_message: str,
        base_commit_sha: str | None = None,
    ) -> ProviderWritebackResult:
        repository = await self._repository.get_provider_repository(provider_repository_id)
        if repository is None:
            raise APIError(
                f"Provider repository {provider_repository_id} was not found.",
                status_code=404,
                code="provider_repository_not_found",
            )
        integration = await self._require_integration(repository.provider_integration_id)
        credentials_secret_ref = await self._load_credentials_secret_ref(integration)
        client = get_provider_client(integration.provider)
        change_request = await client.propose_patch(
            integration,
            repository,
            branch_name=branch_name,
            patch_diff=patch_diff,
            title=title,
            description=description,
            commit_message=commit_message,
            base_commit_sha=base_commit_sha,
            credentials_secret_ref=credentials_secret_ref,
        )
        return ProviderWritebackResult(
            branch_name=change_request.branch_name,
            commit_sha=change_request.commit_sha,
            change_request_url=change_request.change_request_url,
            reference_id=change_request.reference_id,
            mergeable=change_request.mergeable,
        )

    async def build_authenticated_repository_clone_url(
        self,
        *,
        project_id: str,
        provider_repository_id: str,
    ) -> tuple[ProviderRepositoryRecord, str]:
        repository = await self._repository.get_provider_repository(provider_repository_id)
        if repository is None:
            raise APIError(
                f"Provider repository {provider_repository_id} was not found.",
                status_code=404,
                code="provider_repository_not_found",
            )
        integration = await self._require_integration(repository.provider_integration_id)
        if self._require_project_id(integration) != project_id:
            raise APIError(
                f"Provider repository {provider_repository_id} was not found for project {project_id}.",
                status_code=404,
                code="provider_repository_not_found",
            )
        credentials_secret_ref = await self._load_credentials_secret_ref(integration)
        client = get_provider_client(integration.provider)
        access = await client.build_sandbox_access(
            integration,
            repository,
            credentials_secret_ref=credentials_secret_ref,
        )
        return repository, access.secret_value

    async def infer_repo_profile_defaults(
        self,
        *,
        project_id: str,
        provider_repository_id: str,
    ) -> RepoProfileInferenceResult:
        repository = await self._repository.get_provider_repository(provider_repository_id)
        if repository is None:
            raise APIError(
                f"Provider repository {provider_repository_id} was not found.",
                status_code=404,
                code="provider_repository_not_found",
            )
        integration = await self._require_integration(repository.provider_integration_id)
        if self._require_project_id(integration) != project_id:
            raise APIError(
                f"Provider repository {provider_repository_id} was not found for project {project_id}.",
                status_code=404,
                code="provider_repository_not_found",
            )
        credentials_secret_ref = await self._load_credentials_secret_ref(integration)
        client = get_provider_client(integration.provider)
        access = await client.build_sandbox_access(
            integration,
            repository,
            credentials_secret_ref=credentials_secret_ref,
        )
        try:
            return infer_repo_profile_from_clone(
                clone_url=access.secret_value,
                default_branch=repository.default_branch or "main",
            )
        except APIError as exc:
            if exc.code not in {"repo_profile_inference_git_failed", "repo_profile_inference_timeout"}:
                raise
            raise APIError(
                (
                    f"Unable to inspect {repository.name} automatically. "
                    "The repo connection succeeded, but command inference could not finish. "
                    f"{exc.message}"
                ),
                status_code=exc.status_code,
                code=exc.code,
            ) from exc

    async def list_repository_branches(
        self,
        *,
        project_id: str,
        provider_repository_id: str,
        limit: int = 20,
    ):
        repository = await self._repository.get_provider_repository(provider_repository_id)
        if repository is None:
            raise APIError(
                f"Provider repository {provider_repository_id} was not found.",
                status_code=404,
                code="provider_repository_not_found",
            )
        integration = await self._require_integration(repository.provider_integration_id)
        if self._require_project_id(integration) != project_id:
            raise APIError(
                f"Provider repository {provider_repository_id} was not found for project {project_id}.",
                status_code=404,
                code="provider_repository_not_found",
            )
        credentials_secret_ref = await self._load_credentials_secret_ref(integration)
        client = get_provider_client(integration.provider)
        return await client.list_branches(
            integration,
            repository,
            credentials_secret_ref=credentials_secret_ref,
            limit=limit,
        )

    def verify_github_webhook(self, *, body: bytes, signature_header: str | None) -> None:
        secret = get_github_webhook_secret()
        if secret is None:
            raise APIError(
                "GitHub webhook secret is not configured.",
                status_code=503,
                code="github_unconfigured",
            )
        if signature_header is None or not signature_header.startswith("sha256="):
            raise APIError(
                "GitHub webhook signature was missing.",
                status_code=401,
                code="github_webhook_invalid_signature",
            )
        digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        expected = f"sha256={digest}"
        if not hmac.compare_digest(expected, signature_header):
            raise APIError(
                "GitHub webhook signature was invalid.",
                status_code=401,
                code="github_webhook_invalid_signature",
            )

    async def _require_integration(self, provider_integration_id: str) -> ProviderIntegrationRecord:
        integration = await self._repository.get_provider_integration(provider_integration_id)
        if integration is None:
            raise APIError(
                f"Provider integration {provider_integration_id} was not found.",
                status_code=404,
                code="provider_integration_not_found",
            )
        return integration

    async def _load_credentials_secret_ref(
        self,
        integration: ProviderIntegrationRecord,
    ) -> SecretRefRecord | None:
        if integration.credentials_secret_ref_id is None:
            return None
        secret_ref = await self._repository.get_secret_ref(integration.credentials_secret_ref_id)
        if secret_ref is None:
            raise APIError(
                f"Secret ref {integration.credentials_secret_ref_id} was not found.",
                status_code=404,
                code="secret_ref_not_found",
            )
        return secret_ref

    def _require_project_id(self, integration: ProviderIntegrationRecord) -> str:
        project_id = self._resolve_project_id(integration.metadata)
        if project_id is None or not str(project_id).strip():
            raise APIError(
                f"Provider integration {integration.id} is missing a project id.",
                status_code=400,
                code="provider_integration_project_missing",
            )
        return str(project_id)

    def _resolve_project_id(self, metadata: dict[str, object]) -> str | None:
        project_id = metadata.get("project_id")
        if isinstance(project_id, str) and project_id.strip():
            return project_id.strip()

        redirect_project_id = metadata.get("redirect_project_id")
        if isinstance(redirect_project_id, str) and redirect_project_id.strip():
            return redirect_project_id.strip()

        redirect_url = metadata.get("redirect_url")
        if isinstance(redirect_url, str) and redirect_url.strip():
            parsed = urlsplit(redirect_url)
            query_pairs = dict(parse_qsl(parsed.query, keep_blank_values=True))
            redirect_query_project_id = query_pairs.get("project_id")
            if isinstance(redirect_query_project_id, str) and redirect_query_project_id.strip():
                return redirect_query_project_id.strip()

        return None

    def build_callback_redirect_url(
        self,
        *,
        redirect_url: str,
        provider: ProviderKind,
        project_id: str,
        integration_id: str,
        installation_id: str | None = None,
        setup_action: str | None = None,
        synced_repository_count: int | None = None,
    ) -> str:
        parsed = urlsplit(redirect_url)
        query_pairs = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query_pairs["provider"] = provider.value
        query_pairs["provider_status"] = "connected"
        query_pairs["project_id"] = project_id
        query_pairs["integration_id"] = integration_id
        if installation_id is not None:
            query_pairs["installation_id"] = installation_id
        if setup_action is not None:
            query_pairs["setup_action"] = setup_action
        if synced_repository_count is not None:
            query_pairs["synced_repositories"] = str(synced_repository_count)
        query_pairs["step"] = "3"
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(query_pairs),
                parsed.fragment,
            )
        )

    def _get_base_url(self, integration: ProviderIntegrationRecord) -> str:
        base_url = integration.metadata.get("gitlab_base_url")
        if base_url is None or not str(base_url).strip():
            return self._gitlab_client._base_url  # type: ignore[attr-defined]
        return str(base_url).rstrip("/")
