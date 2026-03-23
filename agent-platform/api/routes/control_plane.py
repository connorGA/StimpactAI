from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status

from api.core.security import (
    build_project_api_key,
    enforce_control_plane_rate_limit,
    hash_api_key,
    require_control_plane_access,
    require_project_control_plane_access,
)
from api.db.postgres import PostgresConnectionManager, get_postgres_manager
from api.core.errors import APIError
from api.repositories.control_plane_repository import ControlPlaneRepository
from api.schemas.control_plane import (
    CreateProjectApiKeyRequest,
    CreateProviderIntegrationRequest,
    CreateProviderRepositoryRequest,
    CreateRepoProfileRequest,
    CreateSecretRefRequest,
    CreateGitHubAppIntegrationRequest,
    GitHubCallbackResponse,
    GitLabOAuthCallbackResponse,
    GitLabOAuthStartResponse,
    ProjectApiKeyCreateResponse,
    ProjectApiKeyResponse,
    ProjectOnboardingResponse,
    ProjectPolicyResponse,
    ProviderIntegrationOnboardingResponse,
    ProviderInstallationResponse,
    ProviderIntegrationResponse,
    ProviderRepositoryResponse,
    ProviderRepositorySyncResponse,
    ProviderWebhookResponse,
    RepoProfileResponse,
    StartGitLabOAuthRequest,
    SecretRefResponse,
    UpdateProjectPolicyRequest,
)
from models.control_plane import ProviderKind, SecretBackend
from services.aws_secrets_manager import (
    AwsSecretsManagerReader,
    AwsSecretsManagerWriter,
    SecretsReader,
    SecretsWriter,
)
from services.provider_integration_service import ProviderIntegrationService

router = APIRouter(
    prefix="/control-plane",
    tags=["control-plane"],
    dependencies=[Depends(require_control_plane_access), Depends(enforce_control_plane_rate_limit)],
)
project_router = APIRouter(
    prefix="/control-plane/projects/{project_id}",
    tags=["control-plane"],
    dependencies=[Depends(require_project_control_plane_access), Depends(enforce_control_plane_rate_limit)],
)
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


def _assert_project_matches(path_project_id: str, payload_project_id: str) -> None:
    if path_project_id != payload_project_id:
        raise APIError(
            "The project in the request body must match the requested project path.",
            status_code=status.HTTP_400_BAD_REQUEST,
            code="project_mismatch",
        )


async def _require_project_integration(
    repository: ControlPlaneRepository,
    *,
    project_id: str,
    provider_integration_id: str,
):
    integration = await repository.get_provider_integration(provider_integration_id)
    if integration is None or integration.metadata.get("project_id") != project_id:
        raise APIError(
            f"Provider integration {provider_integration_id} was not found for project {project_id}.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="provider_integration_not_found",
        )
    return integration


def _build_onboarding_next_steps(
    *,
    integrations: list[ProviderIntegrationOnboardingResponse],
    secret_refs: list[SecretRefResponse],
    repo_profiles: list[RepoProfileResponse],
) -> list[str]:
    steps: list[str] = []
    if not integrations:
        steps.append("Connect GitHub or GitLab for this project.")
    elif not any(item.repositories for item in integrations):
        steps.append("Sync repositories from your connected provider account.")
    if not secret_refs:
        steps.append("Add the runtime secrets your sandbox environment needs.")
    if not repo_profiles:
        steps.append("Create a repo profile with reproduce and verify commands.")
    if integrations and not any(item.repositories for item in integrations):
        steps.append("Choose a repository after the sync completes.")
    if integrations and secret_refs and not repo_profiles:
        steps.append("Sync provider repositories and choose one to activate for sandbox runs.")
    if not steps:
        steps.append("Project onboarding looks complete. Run a sandbox verification to validate the setup.")
    return steps


async def _build_project_onboarding_response(
    *,
    project_id: str,
    repository: ControlPlaneRepository,
) -> ProjectOnboardingResponse:
    policy = await repository.get_or_create_project_policy(project_id)
    secret_refs = [SecretRefResponse.from_record(record) for record in await repository.list_secret_refs(project_id)]
    api_keys = [
        ProjectApiKeyResponse.from_record(record)
        for record in await repository.list_project_api_keys(project_id)
    ]
    integrations = await repository.list_provider_integrations(project_id=project_id)
    integration_payloads: list[ProviderIntegrationOnboardingResponse] = []
    for integration in integrations:
        repositories = await repository.list_provider_repositories(integration.id)
        integration_payloads.append(
            ProviderIntegrationOnboardingResponse(
                integration=ProviderIntegrationResponse.from_record(integration),
                repositories=[
                    ProviderRepositoryResponse.from_record(record)
                    for record in repositories
                ],
            )
        )
    repo_profiles: list[RepoProfileResponse] = []
    for record in await repository.list_repo_profiles(project_id):
        secret_mounts = await repository.list_repo_profile_secret_bindings(record.id)
        repo_profiles.append(RepoProfileResponse.from_record(record, secret_mounts=secret_mounts))
    return ProjectOnboardingResponse(
        project_id=project_id,
        policy=ProjectPolicyResponse.from_record(policy),
        secret_refs=secret_refs,
        api_keys=api_keys,
        integrations=integration_payloads,
        repo_profiles=repo_profiles,
        suggested_next_steps=_build_onboarding_next_steps(
            integrations=integration_payloads,
            secret_refs=secret_refs,
            repo_profiles=repo_profiles,
        ),
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
    "/projects/{project_id}/api-keys",
    response_model=ProjectApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_api_key(
    project_id: str,
    payload: CreateProjectApiKeyRequest,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ProjectApiKeyCreateResponse:
    plaintext_key, key_prefix = build_project_api_key()
    record = await repository.create_project_api_key(
        project_id=project_id,
        name=payload.name,
        key_prefix=key_prefix,
        key_hash=hash_api_key(plaintext_key),
    )
    return ProjectApiKeyCreateResponse(
        api_key=ProjectApiKeyResponse.from_record(record),
        plaintext_key=plaintext_key,
    )


@router.get(
    "/projects/{project_id}/api-keys",
    response_model=list[ProjectApiKeyResponse],
    status_code=status.HTTP_200_OK,
)
async def list_project_api_keys(
    project_id: str,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> list[ProjectApiKeyResponse]:
    records = await repository.list_project_api_keys(project_id)
    return [ProjectApiKeyResponse.from_record(record) for record in records]


@router.post(
    "/projects/{project_id}/api-keys/{key_id}/revoke",
    response_model=ProjectApiKeyResponse,
    status_code=status.HTTP_200_OK,
)
async def revoke_project_api_key(
    project_id: str,
    key_id: str,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ProjectApiKeyResponse:
    record = await repository.get_project_api_key(key_id)
    if record is None or record.project_id != project_id:
        raise APIError(
            f"Project API key {key_id} was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="project_api_key_not_found",
        )
    revoked = await repository.revoke_project_api_key(key_id)
    return ProjectApiKeyResponse.from_record(revoked)


@router.get(
    "/projects/{project_id}/policy",
    response_model=ProjectPolicyResponse,
    status_code=status.HTTP_200_OK,
)
async def get_project_policy(
    project_id: str,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ProjectPolicyResponse:
    record = await repository.get_or_create_project_policy(project_id)
    return ProjectPolicyResponse.from_record(record)


@router.put(
    "/projects/{project_id}/policy",
    response_model=ProjectPolicyResponse,
    status_code=status.HTTP_200_OK,
)
async def update_project_policy(
    project_id: str,
    payload: UpdateProjectPolicyRequest,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ProjectPolicyResponse:
    record = await repository.update_project_policy(
        project_id=project_id,
        autonomy_mode=payload.autonomy_mode,
        require_human_approval=payload.require_human_approval,
        allow_production_writes=payload.allow_production_writes,
        allow_low_risk_autonomy=payload.allow_low_risk_autonomy,
        block_during_active_deploys=payload.block_during_active_deploys,
        restrict_to_approved_services=payload.restrict_to_approved_services,
        require_rollback_plan=payload.require_rollback_plan,
        require_post_action_verification=payload.require_post_action_verification,
        approved_services=payload.approved_services,
        failure_classifier_enabled=payload.failure_classifier_enabled,
        root_cause_enabled=payload.root_cause_enabled,
        patch_planner_enabled=payload.patch_planner_enabled,
        runbook_executor_enabled=payload.runbook_executor_enabled,
    )
    return ProjectPolicyResponse.from_record(record)


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
    project_id: str | None = Query(default=None, min_length=1, max_length=128),
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> list[ProviderIntegrationResponse]:
    records = await repository.list_provider_integrations(project_id=project_id)
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


@project_router.post("/bootstrap", response_model=ProjectOnboardingResponse, status_code=status.HTTP_200_OK)
async def bootstrap_project_onboarding(
    project_id: str,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ProjectOnboardingResponse:
    await repository.get_or_create_project_policy(project_id)
    return await _build_project_onboarding_response(project_id=project_id, repository=repository)


@project_router.get("/onboarding", response_model=ProjectOnboardingResponse, status_code=status.HTTP_200_OK)
async def get_project_onboarding(
    project_id: str,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ProjectOnboardingResponse:
    return await _build_project_onboarding_response(project_id=project_id, repository=repository)


@project_router.post("/secret-refs", response_model=SecretRefResponse, status_code=status.HTTP_201_CREATED)
async def create_project_secret_ref(
    project_id: str,
    payload: CreateSecretRefRequest,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    writer: SecretsWriter = Depends(get_secrets_writer),
) -> SecretRefResponse:
    _assert_project_matches(project_id, payload.project_id)
    return await create_secret_ref(payload, repository=repository, writer=writer)


@project_router.get("/secret-refs", response_model=list[SecretRefResponse], status_code=status.HTTP_200_OK)
async def list_project_secret_refs(
    project_id: str,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> list[SecretRefResponse]:
    return await list_secret_refs(project_id=project_id, repository=repository)


@project_router.get(
    "/provider-integrations",
    response_model=list[ProviderIntegrationResponse],
    status_code=status.HTTP_200_OK,
)
async def list_project_provider_integrations(
    project_id: str,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> list[ProviderIntegrationResponse]:
    return await list_provider_integrations(project_id=project_id, repository=repository)


@project_router.post(
    "/provider-integrations/github-app",
    response_model=ProviderIntegrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_github_app_integration(
    project_id: str,
    payload: CreateGitHubAppIntegrationRequest,
    service: ProviderIntegrationService = Depends(get_provider_integration_service),
) -> ProviderIntegrationResponse:
    _assert_project_matches(project_id, payload.project_id)
    return await create_github_app_integration(payload, service=service)


@project_router.post(
    "/provider-integrations/gitlab/oauth/start",
    response_model=GitLabOAuthStartResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_project_gitlab_oauth(
    project_id: str,
    payload: StartGitLabOAuthRequest,
    service: ProviderIntegrationService = Depends(get_provider_integration_service),
) -> GitLabOAuthStartResponse:
    _assert_project_matches(project_id, payload.project_id)
    return await start_gitlab_oauth(payload, service=service)


@project_router.get(
    "/provider-integrations/{provider_integration_id}/repositories",
    response_model=list[ProviderRepositoryResponse],
    status_code=status.HTTP_200_OK,
)
async def list_project_provider_repositories(
    project_id: str,
    provider_integration_id: str,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: ProviderIntegrationService = Depends(get_provider_integration_service),
) -> list[ProviderRepositoryResponse]:
    await _require_project_integration(
        repository,
        project_id=project_id,
        provider_integration_id=provider_integration_id,
    )
    return await list_provider_repositories(provider_integration_id=provider_integration_id, service=service)


@project_router.post(
    "/provider-integrations/{provider_integration_id}/repositories/sync",
    response_model=ProviderRepositorySyncResponse,
    status_code=status.HTTP_200_OK,
)
async def sync_project_provider_repositories(
    project_id: str,
    provider_integration_id: str,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: ProviderIntegrationService = Depends(get_provider_integration_service),
) -> ProviderRepositorySyncResponse:
    await _require_project_integration(
        repository,
        project_id=project_id,
        provider_integration_id=provider_integration_id,
    )
    return await sync_provider_repositories(provider_integration_id=provider_integration_id, service=service)


@project_router.post("/repo-profiles", response_model=RepoProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_project_repo_profile(
    project_id: str,
    payload: CreateRepoProfileRequest,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> RepoProfileResponse:
    _assert_project_matches(project_id, payload.project_id)
    return await create_repo_profile(payload, repository=repository)


@project_router.get("/repo-profiles", response_model=list[RepoProfileResponse], status_code=status.HTTP_200_OK)
async def list_project_repo_profiles(
    project_id: str,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> list[RepoProfileResponse]:
    return await list_repo_profiles(project_id=project_id, repository=repository)


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
