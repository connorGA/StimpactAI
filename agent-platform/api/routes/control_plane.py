from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status

from api.db.postgres import PostgresConnectionManager, get_postgres_manager
from api.core.errors import APIError
from api.repositories.control_plane_repository import ControlPlaneRepository
from api.schemas.control_plane import (
    CreateProviderIntegrationRequest,
    CreateProviderRepositoryRequest,
    CreateRepoProfileRequest,
    CreateSecretRefRequest,
    CreateGitHubAppIntegrationRequest,
    GitHubCallbackResponse,
    GitLabOAuthCallbackResponse,
    GitLabOAuthStartResponse,
    ProviderInstallationResponse,
    ProviderIntegrationResponse,
    ProviderRepositoryResponse,
    ProviderRepositorySyncResponse,
    ProviderWebhookResponse,
    RepoProfileResponse,
    StartGitLabOAuthRequest,
    SecretRefResponse,
)
from models.control_plane import ProviderKind, SecretBackend
from services.aws_secrets_manager import (
    AwsSecretsManagerReader,
    AwsSecretsManagerWriter,
    SecretsReader,
    SecretsWriter,
)
from services.provider_integration_service import ProviderIntegrationService

router = APIRouter(prefix="/control-plane", tags=["control-plane"])
public_router = APIRouter(tags=["provider-callbacks"])


def get_control_plane_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> ControlPlaneRepository:
    return ControlPlaneRepository(manager.pool)


def get_secrets_writer() -> SecretsWriter:
    return AwsSecretsManagerWriter()


def get_secrets_reader() -> SecretsReader:
    return AwsSecretsManagerReader()


def get_provider_integration_service(
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    writer: SecretsWriter = Depends(get_secrets_writer),
    reader: SecretsReader = Depends(get_secrets_reader),
) -> ProviderIntegrationService:
    return ProviderIntegrationService(
        repository,
        secrets_writer=writer,
        secrets_reader=reader,
    )


@router.post("/secret-refs", response_model=SecretRefResponse, status_code=status.HTTP_201_CREATED)
async def create_secret_ref(
    payload: CreateSecretRefRequest,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    writer: SecretsWriter = Depends(get_secrets_writer),
) -> SecretRefResponse:
    external_ref = writer.put_secret(
        project_id=payload.project_id,
        label=payload.label,
        value=payload.value,
    )
    record = await repository.create_secret_ref(
        project_id=payload.project_id,
        label=payload.label,
        description=payload.description,
        backend=SecretBackend.AWS_SECRETS_MANAGER,
        external_ref=external_ref,
    )
    return SecretRefResponse.from_record(record)


@router.get("/secret-refs", response_model=list[SecretRefResponse], status_code=status.HTTP_200_OK)
async def list_secret_refs(
    project_id: str = Query(min_length=1, max_length=128),
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> list[SecretRefResponse]:
    records = await repository.list_secret_refs(project_id)
    return [SecretRefResponse.from_record(record) for record in records]


@router.post(
    "/provider-integrations",
    response_model=ProviderIntegrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider_integration(
    payload: CreateProviderIntegrationRequest,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ProviderIntegrationResponse:
    record = await repository.create_provider_integration(
        provider=payload.provider,
        name=payload.name,
        credentials_secret_ref_id=payload.credentials_secret_ref_id,
        webhook_secret_ref_id=payload.webhook_secret_ref_id,
        aws_region=payload.aws_region,
        metadata={},
    )
    return ProviderIntegrationResponse.from_record(record)


@router.get(
    "/provider-integrations",
    response_model=list[ProviderIntegrationResponse],
    status_code=status.HTTP_200_OK,
)
async def list_provider_integrations(
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> list[ProviderIntegrationResponse]:
    records = await repository.list_provider_integrations()
    return [ProviderIntegrationResponse.from_record(record) for record in records]


@router.post(
    "/provider-integrations/github-app",
    response_model=ProviderIntegrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_github_app_integration(
    payload: CreateGitHubAppIntegrationRequest,
    service: ProviderIntegrationService = Depends(get_provider_integration_service),
) -> ProviderIntegrationResponse:
    integration, _installation = await service.create_github_app_integration(
        project_id=payload.project_id,
        name=payload.name,
        installation_id=payload.installation_id,
    )
    return ProviderIntegrationResponse.from_record(integration)


@router.post(
    "/provider-integrations/gitlab/oauth/start",
    response_model=GitLabOAuthStartResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_gitlab_oauth(
    payload: StartGitLabOAuthRequest,
    service: ProviderIntegrationService = Depends(get_provider_integration_service),
) -> GitLabOAuthStartResponse:
    integration, authorization_url = await service.start_gitlab_oauth(
        project_id=payload.project_id,
        name=payload.name,
        gitlab_base_url=payload.gitlab_base_url,
    )
    return GitLabOAuthStartResponse(
        integration=ProviderIntegrationResponse.from_record(integration),
        authorization_url=authorization_url,
    )


@router.post(
    "/provider-repositories",
    response_model=ProviderRepositoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider_repository(
    payload: CreateProviderRepositoryRequest,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ProviderRepositoryResponse:
    record = await repository.create_provider_repository(
        provider_integration_id=payload.provider_integration_id,
        provider=payload.provider,
        external_repository_id=payload.external_repository_id,
        owner=payload.owner,
        name=payload.name,
        default_branch=payload.default_branch,
        clone_url=payload.clone_url,
    )
    return ProviderRepositoryResponse.from_record(record)


@router.get(
    "/provider-integrations/{provider_integration_id}/repositories",
    response_model=list[ProviderRepositoryResponse],
    status_code=status.HTTP_200_OK,
)
async def list_provider_repositories(
    provider_integration_id: str,
    service: ProviderIntegrationService = Depends(get_provider_integration_service),
) -> list[ProviderRepositoryResponse]:
    records = await service.list_synced_repositories(provider_integration_id)
    return [ProviderRepositoryResponse.from_record(record) for record in records]


@router.post(
    "/provider-integrations/{provider_integration_id}/repositories/sync",
    response_model=ProviderRepositorySyncResponse,
    status_code=status.HTTP_200_OK,
)
async def sync_provider_repositories(
    provider_integration_id: str,
    service: ProviderIntegrationService = Depends(get_provider_integration_service),
) -> ProviderRepositorySyncResponse:
    integration, repositories = await service.sync_repositories(provider_integration_id)
    return ProviderRepositorySyncResponse(
        integration=ProviderIntegrationResponse.from_record(integration),
        repositories=[ProviderRepositoryResponse.from_record(record) for record in repositories],
    )


@router.post("/repo-profiles", response_model=RepoProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_repo_profile(
    payload: CreateRepoProfileRequest,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> RepoProfileResponse:
    record = await repository.create_repo_profile(
        project_id=payload.project_id,
        provider_repository_id=payload.provider_repository_id,
        runtime_kind=payload.runtime_kind,
        base_image=payload.base_image,
        install_command=payload.install_command,
        startup_commands=payload.startup_commands,
        reproduce_command=payload.reproduce_command,
        verify_command=payload.verify_command,
        success_criteria=payload.success_criteria,
        network_allowlist=payload.network_allowlist,
    )
    mounts_to_attach = [(mount.secret_ref_id, mount.mount_as) for mount in payload.secret_mounts]
    if not mounts_to_attach and payload.secret_ref_ids:
        for secret_ref_id in payload.secret_ref_ids:
            secret_ref = await repository.get_secret_ref(secret_ref_id)
            if secret_ref is None:
                raise APIError(
                    f"Secret ref {secret_ref_id} was not found.",
                    status_code=404,
                    code="secret_ref_not_found",
                )
            mounts_to_attach.append((secret_ref_id, secret_ref.label))
    for secret_ref_id, mount_as in mounts_to_attach:
        await repository.attach_secret_ref_to_repo_profile(
            repo_profile_id=record.id,
            secret_ref_id=secret_ref_id,
            mount_as=mount_as,
        )
    secret_mounts = await repository.list_repo_profile_secret_bindings(record.id)
    return RepoProfileResponse.from_record(record, secret_mounts=secret_mounts)


@router.get("/repo-profiles", response_model=list[RepoProfileResponse], status_code=status.HTTP_200_OK)
async def list_repo_profiles(
    project_id: str = Query(min_length=1, max_length=128),
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> list[RepoProfileResponse]:
    records = await repository.list_repo_profiles(project_id)
    responses: list[RepoProfileResponse] = []
    for record in records:
        secret_mounts = await repository.list_repo_profile_secret_bindings(record.id)
        responses.append(RepoProfileResponse.from_record(record, secret_mounts=secret_mounts))
    return responses


@public_router.get(
    "/api/github/callback",
    response_model=GitHubCallbackResponse,
    status_code=status.HTTP_200_OK,
)
async def github_callback(
    installation_id: str | None = Query(default=None),
    setup_action: str | None = Query(default=None),
    service: ProviderIntegrationService = Depends(get_provider_integration_service),
) -> GitHubCallbackResponse:
    preview = await service.preview_github_callback(
        installation_id=installation_id,
        setup_action=setup_action,
    )
    return GitHubCallbackResponse(
        installation_id=preview.installation_id,
        setup_action=preview.setup_action,
        account_login=preview.account_login,
        account_type=preview.account_type,
        account_name=preview.account_name,
    )


@public_router.get(
    "/auth/gitlab/callback",
    response_model=GitLabOAuthCallbackResponse,
    status_code=status.HTTP_200_OK,
)
async def gitlab_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    service: ProviderIntegrationService = Depends(get_provider_integration_service),
) -> GitLabOAuthCallbackResponse:
    if error is not None:
        raise APIError(
            error_description or f"GitLab OAuth returned error {error}.",
            status_code=400,
            code="gitlab_oauth_denied",
        )
    if code is None or state is None:
        raise APIError(
            "GitLab OAuth callback was missing code or state.",
            status_code=400,
            code="gitlab_oauth_invalid_callback",
        )
    result = await service.complete_gitlab_oauth_callback(state=state, code=code)
    return GitLabOAuthCallbackResponse(
        integration=ProviderIntegrationResponse.from_record(result.integration),
        credentials_secret_ref=SecretRefResponse.from_record(result.credentials_secret_ref),
        connected_account=ProviderInstallationResponse(
            external_id=result.connected_account.external_id,
            account_login=result.connected_account.account_login,
            account_type=result.connected_account.account_type,
            account_name=result.connected_account.account_name,
        ),
    )


@public_router.post(
    "/webhooks/github",
    response_model=ProviderWebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def github_webhook(
    request: Request,
    service: ProviderIntegrationService = Depends(get_provider_integration_service),
) -> ProviderWebhookResponse:
    body = await request.body()
    service.verify_github_webhook(
        body=body,
        signature_header=request.headers.get("X-Hub-Signature-256"),
    )
    return ProviderWebhookResponse(
        provider=ProviderKind.GITHUB,
        event=request.headers.get("X-GitHub-Event", "unknown"),
        delivery_id=request.headers.get("X-GitHub-Delivery"),
        status="accepted",
    )
