from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from openai import OpenAI

from api.core.security import (
    build_project_api_key,
    build_project_browser_key,
    enforce_control_plane_rate_limit,
    hash_api_key,
    require_control_plane_access,
    require_project_control_plane_access,
)
from api.core.config import (
    get_frontend_base_url,
    get_openai_api_key,
    get_openai_patch_model,
    get_public_base_url,
)
from api.db.postgres import PostgresConnectionManager, get_postgres_manager
from api.core.errors import APIError
from api.repositories.control_plane_repository import ControlPlaneRepository
from api.schemas.control_plane import (
    CreateProjectServiceRequest,
    CreateProjectApiKeyRequest,
    CreateProjectBrowserKeyRequest,
    CreateSdkBootstrapPlanRequest,
    CreateSdkBootstrapPreviewRequest,
    CreateSdkBootstrapChangeRequestRequest,
    CreateProviderIntegrationRequest,
    CreateProviderRepositoryRequest,
    CreateRepoProfileRequest,
    CreateSecretRefRequest,
    CreateGitHubAppIntegrationRequest,
    StartGitHubAppInstallRequest,
    GitHubAppInstallStartResponse,
    GitHubCallbackResponse,
    GitLabOAuthCallbackResponse,
    GitLabOAuthStartResponse,
    ProjectApiKeyCreateResponse,
    ProjectApiKeyResponse,
    ProjectBrowserKeyCreateResponse,
    ProjectBrowserKeyResponse,
    ProjectOnboardingResponse,
    ProjectOnboardingStateResponse,
    ProjectHarnessLaunchContractResponse,
    ProjectHarnessReadinessCheckResponse,
    ProjectHarnessReadinessResponse,
    ProjectOperationalReadinessResponse,
    ProjectPolicyResponse,
    ProjectTelemetryHeartbeatResponse,
    ProjectTelemetryVerificationResponse,
    ProjectSandboxPlanPreviewResponse,
    ProjectServiceResponse,
    SandboxPlanServiceResponse,
    ProviderIntegrationOnboardingResponse,
    ProviderInstallationResponse,
    ProviderIntegrationResponse,
    ProviderRepositoryResponse,
    ProviderRepositorySyncResponse,
    ProviderWebhookResponse,
    RepoProfileInferenceResponse,
    RepoProfileResponse,
    SdkBootstrapEnvVarResponse,
    StartGitLabOAuthRequest,
    SecretRefResponse,
    SdkBootstrapManualStepResponse,
    SdkBootstrapChangeRequestResponse,
    SdkBootstrapPlanPreviewResponse,
    SdkBootstrapPatchAttemptResponse,
    SdkBootstrapPreviewResponse,
    SdkBootstrapPlannedFileResponse,
    SdkBootstrapPullRequestPreviewResponse,
    SdkBootstrapStrategyResponse,
    SdkBootstrapVerificationResponse,
    UpdateProjectPolicyRequest,
    UpdateProjectBrowserKeyRequest,
    UpdateProjectOnboardingStateRequest,
    UpdateProjectServiceRequest,
)
from models.control_plane import (
    ProjectApiKeyStatus,
    ProjectBrowserKeyStatus,
    ProjectSdkSetupStatus,
    ProviderKind,
    SecretBackend,
)
from services.aws_secrets_manager import (
    AwsSecretsManagerReader,
    AwsSecretsManagerWriter,
    SecretsReader,
    SecretsWriter,
)
from services.provider_integration_service import ProviderIntegrationService
from services.sdk_bootstrap import (
    SDK_BOOTSTRAP_API_KEY_PLACEHOLDER,
    SdkBootstrapPlan,
    SdkBootstrapPatchAttempt,
    SdkBootstrapStrategy,
    build_sdk_bootstrap_patch_from_clone,
    plan_sdk_bootstrap_from_clone,
    prepare_sdk_bootstrap_preview_from_clone,
)
from services.sdk_bootstrap_fallback import SdkBootstrapFallbackPlanner
from services.telemetry_origin_registry import TelemetryOriginRegistry

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
TELEMETRY_HEARTBEAT_STALE_AFTER_SECONDS = 900
logger = logging.getLogger(__name__)


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


def get_sdk_bootstrap_fallback_planner() -> SdkBootstrapFallbackPlanner | None:
    api_key = get_openai_api_key()
    if api_key is None:
        return None
    return SdkBootstrapFallbackPlanner(
        client=OpenAI(api_key=api_key),
        model=get_openai_patch_model(),
    )


def _assert_project_matches(path_project_id: str, payload_project_id: str) -> None:
    if path_project_id != payload_project_id:
        raise APIError(
            "The project in the request body must match the requested project path.",
            status_code=status.HTTP_400_BAD_REQUEST,
            code="project_mismatch",
        )


def _invalidate_telemetry_origin_registry(request: Request) -> None:
    registry = getattr(request.app.state, "telemetry_origin_registry", None)
    if isinstance(registry, TelemetryOriginRegistry):
        registry.invalidate_cache()


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


def _build_operational_readiness(
    *,
    integrations: list[ProviderIntegrationOnboardingResponse],
    secret_refs: list[SecretRefResponse],
    repo_profiles: list[RepoProfileResponse],
    project_services: list[ProjectServiceResponse],
    api_keys: list[ProjectApiKeyResponse],
    browser_keys: list[ProjectBrowserKeyResponse],
    policy_reviewed: bool,
    sdk_setup_status: ProjectSdkSetupStatus,
) -> ProjectOperationalReadinessResponse:
    has_provider_connection = len(integrations) > 0
    has_synced_repositories = any(item.repositories for item in integrations)
    has_secrets = len(secret_refs) > 0
    has_repo_profiles = len(repo_profiles) > 0
    has_services = len(project_services) > 0
    has_active_api_keys = any(item.status == "active" for item in api_keys)
    has_active_browser_keys = any(item.status == "active" for item in browser_keys)
    sdk_setup_ready = sdk_setup_status is not ProjectSdkSetupStatus.PENDING
    complete = (
        has_provider_connection
        and has_synced_repositories
        and has_secrets
        and has_repo_profiles
        and has_services
        and (has_active_api_keys or has_active_browser_keys)
        and policy_reviewed
        and sdk_setup_ready
    )
    return ProjectOperationalReadinessResponse(
        has_provider_connection=has_provider_connection,
        has_synced_repositories=has_synced_repositories,
        has_secrets=has_secrets,
        has_repo_profiles=has_repo_profiles,
        has_services=has_services,
        has_active_api_keys=has_active_api_keys,
        has_active_browser_keys=has_active_browser_keys,
        policy_reviewed=policy_reviewed,
        sdk_setup_ready=sdk_setup_ready,
        complete=complete,
    )


def _build_onboarding_next_steps(
    *,
    integrations: list[ProviderIntegrationOnboardingResponse],
    secret_refs: list[SecretRefResponse],
    repo_profiles: list[RepoProfileResponse],
    project_services: list[ProjectServiceResponse],
    api_keys: list[ProjectApiKeyResponse],
    browser_keys: list[ProjectBrowserKeyResponse],
    policy_reviewed: bool,
    sdk_setup_status: ProjectSdkSetupStatus,
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
    if repo_profiles and not project_services:
        steps.append("Create project services and map each one to the correct repo profile.")
    if integrations and not any(item.repositories for item in integrations):
        steps.append("Choose a repository after the sync completes.")
    if integrations and secret_refs and not repo_profiles:
        steps.append("Sync provider repositories and create repo profiles for the services you need.")
    if not any(item.status == "active" for item in api_keys) and not any(
        item.status == "active" for item in browser_keys
    ):
        steps.append("Create telemetry credentials for the runtime you plan to instrument.")
    if not policy_reviewed:
        steps.append("Review and confirm the automation controls for this project.")
    if sdk_setup_status is ProjectSdkSetupStatus.PENDING:
        steps.append("Choose an SDK setup path: follow the manual guide, open a bootstrap PR, or defer it for later.")
    if not steps:
        steps.append("Project onboarding looks complete. Run a sandbox verification and validate telemetry flow.")
    return steps


def _build_sdk_bootstrap_strategy_response(strategy: SdkBootstrapStrategy) -> SdkBootstrapStrategyResponse:
    return SdkBootstrapStrategyResponse(
        id=strategy.id,
        language=strategy.language,
        framework=strategy.framework,
        summary=strategy.summary,
        confidence=strategy.confidence,
        pr_supported=strategy.pr_supported,
        target_subpath=strategy.target_subpath,
        entrypoints=list(strategy.entrypoints),
        assumptions=list(strategy.assumptions),
        blockers=list(strategy.blockers),
        planned_files=[
            SdkBootstrapPlannedFileResponse(
                path=item.path,
                action=item.action,
                reason=item.reason,
            )
            for item in strategy.planned_files
        ],
        env_vars=[
            SdkBootstrapEnvVarResponse(
                name=item.name,
                example_value=item.example_value,
                description=item.description,
            )
            for item in strategy.env_vars
        ],
        install_command=strategy.install_command,
        package_name=strategy.package_name,
        manual_steps=[
            SdkBootstrapManualStepResponse(title=item.title, content=item.content)
            for item in strategy.manual_steps
        ],
        preview_snippet=strategy.preview_snippet,
        source=strategy.source,
        evidence=list(strategy.evidence),
        confidence_reason=strategy.confidence_reason,
    )


def _build_sdk_bootstrap_plan_response(plan: SdkBootstrapPlan) -> SdkBootstrapPlanPreviewResponse:
    return SdkBootstrapPlanPreviewResponse(
        runtime=plan.runtime,
        warnings=list(plan.warnings),
        strategies=[_build_sdk_bootstrap_strategy_response(item) for item in plan.strategies],
        recommended_strategy_id=plan.recommended_strategy_id,
        requires_confirmation=plan.requires_confirmation,
    )


def _build_sdk_bootstrap_patch_attempt_response(attempt: SdkBootstrapPatchAttempt) -> SdkBootstrapPatchAttemptResponse:
    return SdkBootstrapPatchAttemptResponse(
        strategy_id=attempt.strategy_id,
        patch_source=attempt.patch_source,
        patch_generated=attempt.patch_generated,
        patch_applied=attempt.patch_applied,
        verification=SdkBootstrapVerificationResponse(
            status=attempt.verification.status,
            command=attempt.verification.command,
            summary=attempt.verification.summary,
            output=attempt.verification.output,
        ),
        preview_available=attempt.preview_available,
        change_request_allowed=attempt.change_request_allowed,
        changed_files=list(attempt.changed_files),
        warnings=list(attempt.warnings),
        failure_stage=attempt.failure_stage,
        failure_reason=attempt.failure_reason,
        rejection_reason_code=attempt.rejection_reason_code,
        attempt_number=attempt.attempt_number,
        candidate_id=attempt.candidate_id,
        generation_duration_ms=attempt.generation_duration_ms,
        apply_duration_ms=attempt.apply_duration_ms,
        verification_duration_ms=attempt.verification_duration_ms,
    )


def _resolve_sdk_bootstrap_strategy(
    *,
    plan: SdkBootstrapPlan,
    strategy_id: str | None,
) -> tuple[str, SdkBootstrapStrategy]:
    selected_strategy_id = strategy_id or plan.recommended_strategy_id
    if selected_strategy_id is None:
        raise APIError(
            "No SDK bootstrap strategy could be recommended for this repository.",
            status_code=status.HTTP_400_BAD_REQUEST,
            code="sdk_bootstrap_plan_unavailable",
        )
    if plan.requires_confirmation and strategy_id is None:
        raise APIError(
            "This repository has multiple or ambiguous SDK bootstrap surfaces. Preview the plan and submit an explicit strategy_id before generating a PR.",
            status_code=status.HTTP_409_CONFLICT,
            code="sdk_bootstrap_confirmation_required",
        )
    selected_strategy = next((item for item in plan.strategies if item.id == selected_strategy_id), None)
    if selected_strategy is None:
        raise APIError(
            f"SDK bootstrap strategy {selected_strategy_id} was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="sdk_bootstrap_strategy_not_found",
        )
    return selected_strategy_id, selected_strategy


def _log_sdk_bootstrap_plan(
    *,
    project_id: str,
    provider_repository_id: str,
    plan: SdkBootstrapPlan,
) -> None:
    recommended = next((item for item in plan.strategies if item.id == plan.recommended_strategy_id), None)
    pr_supported_count = sum(1 for item in plan.strategies if item.pr_supported)
    llm_strategy_count = sum(1 for item in plan.strategies if item.source == "llm")
    manual_only_count = sum(1 for item in plan.strategies if not item.pr_supported)
    logger.info(
        "sdk_bootstrap_plan project_id=%s provider_repository_id=%s runtime=%s strategies=%s pr_supported=%s manual_only=%s fallback_used=%s requires_confirmation=%s recommended_strategy_id=%s recommended_framework=%s recommended_blockers=%s warnings=%s",
        project_id,
        provider_repository_id,
        plan.runtime or "unknown",
        len(plan.strategies),
        pr_supported_count,
        manual_only_count,
        llm_strategy_count > 0,
        plan.requires_confirmation,
        plan.recommended_strategy_id,
        recommended.framework if recommended is not None else "none",
        len(recommended.blockers) if recommended is not None else 0,
        len(plan.warnings),
    )


def _log_sdk_bootstrap_strategy_event(
    *,
    event: str,
    project_id: str,
    provider_repository_id: str,
    strategy: SdkBootstrapStrategy,
) -> None:
    logger.info(
        "%s project_id=%s provider_repository_id=%s strategy_id=%s framework=%s source=%s confidence=%s pr_supported=%s blockers=%s planned_files=%s",
        event,
        project_id,
        provider_repository_id,
        strategy.id,
        strategy.framework,
        strategy.source,
        strategy.confidence,
        strategy.pr_supported,
        len(strategy.blockers),
        len(strategy.planned_files),
    )


def _build_sdk_bootstrap_pr_metadata(
    *,
    strategy: SdkBootstrapStrategy,
    branch_name: str,
) -> SdkBootstrapPullRequestPreviewResponse:
    target_label = _describe_sdk_bootstrap_target(strategy)
    return SdkBootstrapPullRequestPreviewResponse(
        branch_name=branch_name,
        title=f"Add Stimpact telemetry bootstrap for {strategy.framework}",
        description=(
            f"This PR applies the {strategy.framework} SDK bootstrap plan for "
            f"{target_label}, adds dependency and env scaffolding, "
            "and wires Stimpact telemetry into the detected runtime entrypoint."
        ),
        commit_message=f"Add Stimpact telemetry bootstrap for {strategy.framework}",
    )


def _describe_sdk_bootstrap_target(strategy: SdkBootstrapStrategy) -> str:
    if strategy.target_subpath != ".":
        return strategy.target_subpath
    if strategy.entrypoints:
        return f"the repository entrypoint at {strategy.entrypoints[0]}"
    return "the repository root"


def _sdk_strategy_uses_browser_credentials(strategy: SdkBootstrapStrategy) -> bool:
    return any(
        item.name.startswith("NEXT_PUBLIC_")
        or item.name.startswith("VITE_")
        or item.name.startswith("REACT_APP_")
        for item in strategy.env_vars
    )


def _build_project_telemetry_verification_response(
    *,
    service: str,
    environment: str,
    heartbeat,
) -> ProjectTelemetryVerificationResponse:
    if heartbeat is None:
        return ProjectTelemetryVerificationResponse(
            service=service,
            environment=environment,
            status="unseen",
            stale_after_seconds=TELEMETRY_HEARTBEAT_STALE_AFTER_SECONDS,
            heartbeat=None,
        )
    stale_cutoff = datetime.now(UTC) - timedelta(seconds=TELEMETRY_HEARTBEAT_STALE_AFTER_SECONDS)
    status_value = "healthy" if heartbeat.last_seen_at >= stale_cutoff else "stale"
    return ProjectTelemetryVerificationResponse(
        service=service,
        environment=environment,
        status=status_value,
        last_seen_at=heartbeat.last_seen_at,
        commit_sha=heartbeat.commit_sha,
        stale_after_seconds=TELEMETRY_HEARTBEAT_STALE_AFTER_SECONDS,
        heartbeat=ProjectTelemetryHeartbeatResponse.from_record(heartbeat),
    )


def _readiness_check(
    *,
    check_id: str,
    label: str,
    status: str,
    summary: str,
    detail: str | None = None,
) -> ProjectHarnessReadinessCheckResponse:
    return ProjectHarnessReadinessCheckResponse(
        id=check_id,
        label=label,
        status=status,
        summary=summary,
        detail=detail,
    )


async def _build_project_harness_readiness_response(
    *,
    project_id: str,
    service: str,
    environment: str,
    repository: ControlPlaneRepository,
) -> ProjectHarnessReadinessResponse:
    normalized_service = service.strip()
    normalized_environment = environment.strip()
    onboarding_state = await repository.get_or_create_project_onboarding_state(project_id)
    policy = await repository.get_or_create_project_policy(project_id)
    telemetry_verification = _build_project_telemetry_verification_response(
        service=normalized_service,
        environment=normalized_environment,
        heartbeat=await repository.get_project_telemetry_heartbeat(
            project_id=project_id,
            service=normalized_service,
            environment=normalized_environment,
        ),
    )
    api_keys = await repository.list_project_api_keys(project_id)
    browser_keys = await repository.list_project_browser_keys(project_id)
    integrations = await repository.list_provider_integrations(project_id=project_id)
    project_service = (
        await repository.resolve_project_service(project_id=project_id, service_name=normalized_service)
        if hasattr(repository, "resolve_project_service")
        else None
    )
    repo_profile = None
    dependency_service_slugs: list[str] = []
    if project_service is not None and project_service.repo_profile_id is not None and hasattr(repository, "get_repo_profile"):
        repo_profile = await repository.get_repo_profile(project_service.repo_profile_id)
        if hasattr(repository, "list_project_service_dependencies") and hasattr(repository, "get_project_service"):
            dependency_records = await repository.list_project_service_dependencies(project_service.id)
            for dependency in dependency_records:
                dependency_service = await repository.get_project_service(dependency.depends_on_service_id)
                if dependency_service is not None:
                    dependency_service_slugs.append(dependency_service.slug)
    if repo_profile is None and hasattr(repository, "get_active_repo_profile"):
        repo_profile = await repository.get_active_repo_profile(project_id)
    provider_repository = (
        await repository.get_provider_repository(repo_profile.provider_repository_id)
        if repo_profile is not None and hasattr(repository, "get_provider_repository")
        else None
    )
    ready_checks: list[ProjectHarnessReadinessCheckResponse] = []
    warning_checks: list[ProjectHarnessReadinessCheckResponse] = []
    blocked_checks: list[ProjectHarnessReadinessCheckResponse] = []

    def append_check(check: ProjectHarnessReadinessCheckResponse) -> None:
        if check.status == "ready":
            ready_checks.append(check)
        elif check.status == "warning":
            warning_checks.append(check)
        else:
            blocked_checks.append(check)

    has_active_credentials = any(item.status is ProjectApiKeyStatus.ACTIVE for item in api_keys) or any(
        item.status is ProjectBrowserKeyStatus.ACTIVE for item in browser_keys
    )
    append_check(
        _readiness_check(
            check_id="telemetry-credentials",
            label="Telemetry credentials",
            status="ready" if has_active_credentials else "blocked",
            summary=(
                "At least one active API key or browser key is available for SDK ingest."
                if has_active_credentials
                else "No active telemetry credential is available for this project."
            ),
            detail="Create an API key for servers or a browser key for browser token exchange.",
        )
    )
    append_check(
        _readiness_check(
            check_id="provider-connection",
            label="Provider connection",
            status="ready" if integrations else "blocked",
            summary=(
                "A source provider is connected, so the harness can resolve repository metadata."
                if integrations
                else "No provider integration is connected to this project yet."
            ),
            detail="Connect GitHub or GitLab and sync repositories before launching autonomous runs.",
        )
    )
    append_check(
        _readiness_check(
            check_id="service-mapping",
            label="Service mapping",
            status="ready" if project_service is not None else "blocked",
            summary=(
                f"Service '{project_service.slug}' is mapped for harness execution."
                if project_service is not None
                else f"No project service mapping matches '{normalized_service}'."
            ),
            detail="Create or update a project service so telemetry can resolve to the correct repo profile.",
        )
    )
    append_check(
        _readiness_check(
            check_id="repo-profile",
            label="Repo profile",
            status="ready" if repo_profile is not None else "blocked",
            summary=(
                "A repo profile is available with sandbox commands for this service."
                if repo_profile is not None
                else "No repo profile is available for the selected service."
            ),
            detail="Create a repo profile with install, reproduce, and verify commands.",
        )
    )
    has_command_contract = bool(repo_profile and repo_profile.reproduce_command.strip() and repo_profile.verify_command.strip())
    append_check(
        _readiness_check(
            check_id="sandbox-contract",
            label="Sandbox contract",
            status="ready" if has_command_contract else "blocked",
            summary=(
                "The harness has reproduce and verify commands for iterative repair."
                if has_command_contract
                else "The repo profile is missing reproduce or verify commands."
            ),
            detail="Autonomous runs rely on these commands to recreate failures and validate candidate fixes.",
        )
    )
    append_check(
        _readiness_check(
            check_id="policy-review",
            label="Policy review",
            status="ready" if onboarding_state.policy_reviewed else "warning",
            summary=(
                "Automation controls were reviewed for this project."
                if onboarding_state.policy_reviewed
                else "Automation controls have not been reviewed yet."
            ),
            detail="Review the project policy before enabling broader autonomous execution.",
        )
    )
    heartbeat_status = telemetry_verification.status
    append_check(
        _readiness_check(
            check_id="live-telemetry",
            label="Live telemetry",
            status="ready" if heartbeat_status == "healthy" else "warning",
            summary=(
                "A recent heartbeat confirms the deployed SDK is active."
                if heartbeat_status == "healthy"
                else "The harness can be configured without a fresh heartbeat, but live telemetry has not been confirmed recently."
            ),
            detail="Use heartbeat verification to confirm the deployed service is reaching Stimpact before a live drill.",
        )
    )
    policy_ready = all(
        [
            policy.failure_classifier_enabled,
            policy.root_cause_enabled,
            policy.patch_planner_enabled,
        ]
    )
    append_check(
        _readiness_check(
            check_id="analysis-stack",
            label="Analysis stack",
            status="ready" if policy_ready else "warning",
            summary=(
                "Failure classification, root-cause analysis, and patch planning are enabled."
                if policy_ready
                else "One or more analysis capabilities are disabled in the project policy."
            ),
            detail="These controls improve the evidence available to the agent during repair runs.",
        )
    )
    launch_status = "blocked" if blocked_checks else "warning" if warning_checks else "ready"
    missing_items = [check.label for check in blocked_checks]
    recommended_next_steps = [check.detail for check in blocked_checks + warning_checks if check.detail][:6]
    launch_contract = ProjectHarnessLaunchContractResponse(
        service=normalized_service,
        environment=normalized_environment,
        project_service_id=project_service.id if project_service is not None else None,
        repo_profile_id=repo_profile.id if repo_profile is not None else None,
        provider_repository_id=repo_profile.provider_repository_id if repo_profile is not None else None,
        provider_repository_owner=provider_repository.owner if provider_repository is not None else None,
        provider_repository_name=provider_repository.name if provider_repository is not None else None,
        runtime_kind=repo_profile.runtime_kind.value if repo_profile is not None else None,
        base_image=repo_profile.base_image if repo_profile is not None else None,
        install_command=repo_profile.install_command if repo_profile is not None else None,
        startup_commands=list(repo_profile.startup_commands) if repo_profile is not None else [],
        reproduce_command=repo_profile.reproduce_command if repo_profile is not None else None,
        verify_command=repo_profile.verify_command if repo_profile is not None else None,
        success_criteria=repo_profile.success_criteria if repo_profile is not None else None,
        network_allowlist=list(repo_profile.network_allowlist) if repo_profile is not None else [],
        dependency_service_slugs=dependency_service_slugs,
        browser_verification_urls=[],
        example_autonomous_run_request={
            "execution_mode": "repair_and_propose",
            "allow_writeback": False,
            "max_steps": 12,
            "benchmark_scenario_id": None,
            "benchmark_bug_class": None,
        },
    )
    return ProjectHarnessReadinessResponse(
        project_id=project_id,
        service=normalized_service,
        environment=normalized_environment,
        status=launch_status,
        telemetry_status=heartbeat_status,
        ready_checks=ready_checks,
        warning_checks=warning_checks,
        blocked_checks=blocked_checks,
        missing_items=missing_items,
        recommended_next_steps=recommended_next_steps,
        launch_contract=launch_contract,
    )


async def _build_project_onboarding_response(
    *,
    project_id: str,
    repository: ControlPlaneRepository,
) -> ProjectOnboardingResponse:
    policy = await repository.get_or_create_project_policy(project_id)
    onboarding_state = await repository.get_or_create_project_onboarding_state(project_id)
    secret_refs = [SecretRefResponse.from_record(record) for record in await repository.list_secret_refs(project_id)]
    api_keys = [
        ProjectApiKeyResponse.from_record(record)
        for record in await repository.list_project_api_keys(project_id)
    ]
    browser_keys = [
        ProjectBrowserKeyResponse.from_record(record)
        for record in await repository.list_project_browser_keys(project_id)
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
    project_service_records = (
        await repository.list_project_services(project_id)
        if hasattr(repository, "list_project_services")
        else []
    )
    project_service_dependencies = (
        await repository.list_project_dependencies_for_services([record.id for record in project_service_records])
        if project_service_records and hasattr(repository, "list_project_dependencies_for_services")
        else []
    )
    dependency_map: dict[str, list] = {}
    for item in project_service_dependencies:
        dependency_map.setdefault(item.service_id, []).append(item)
    project_services = [
        ProjectServiceResponse.from_record(
            record,
            dependencies=dependency_map.get(record.id, []),
        )
        for record in project_service_records
    ]
    telemetry_heartbeats = [
        ProjectTelemetryHeartbeatResponse.from_record(record)
        for record in await repository.list_project_telemetry_heartbeats(project_id)
    ]
    operational_readiness = _build_operational_readiness(
        integrations=integration_payloads,
        secret_refs=secret_refs,
        repo_profiles=repo_profiles,
        project_services=project_services,
        api_keys=api_keys,
        browser_keys=browser_keys,
        policy_reviewed=onboarding_state.policy_reviewed,
        sdk_setup_status=onboarding_state.sdk_setup_status,
    )
    return ProjectOnboardingResponse(
        project_id=project_id,
        platform_base_url=get_public_base_url(),
        policy=ProjectPolicyResponse.from_record(policy),
        onboarding_state=ProjectOnboardingStateResponse.from_record(onboarding_state),
        operational_readiness=operational_readiness,
        secret_refs=secret_refs,
        api_keys=api_keys,
        browser_keys=browser_keys,
        integrations=integration_payloads,
        repo_profiles=repo_profiles,
        project_services=project_services,
        telemetry_heartbeats=telemetry_heartbeats,
        suggested_next_steps=_build_onboarding_next_steps(
            integrations=integration_payloads,
            secret_refs=secret_refs,
            repo_profiles=repo_profiles,
            project_services=project_services,
            api_keys=api_keys,
            browser_keys=browser_keys,
            policy_reviewed=onboarding_state.policy_reviewed,
            sdk_setup_status=onboarding_state.sdk_setup_status,
        ),
    )


async def _build_project_sandbox_plan_preview(
    *,
    project_id: str,
    service_id: str,
    repository: ControlPlaneRepository,
) -> ProjectSandboxPlanPreviewResponse:
    service = await repository.get_project_service(service_id)
    if service is None or service.project_id != project_id:
        raise APIError(
            f"Project service {service_id} was not found for project {project_id}.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="project_service_not_found",
        )
    dependency_records = await repository.list_project_service_dependencies(service.id)
    warnings: list[str] = []

    async def build_service_payload(service_id_value: str) -> SandboxPlanServiceResponse:
        target_service = await repository.get_project_service(service_id_value)
        if target_service is None:
            raise APIError(
                f"Project service {service_id_value} was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
                code="project_service_not_found",
            )
        dependencies_for_target = await repository.list_project_service_dependencies(target_service.id)
        repo_profile = (
            await repository.get_repo_profile(target_service.repo_profile_id)
            if target_service.repo_profile_id is not None
            else None
        )
        if repo_profile is None:
            warnings.append(f"Service {target_service.slug} does not yet have a repo profile.")
        secret_mounts = (
            await repository.list_repo_profile_secret_bindings(repo_profile.id)
            if repo_profile is not None
            else []
        )
        return SandboxPlanServiceResponse(
            service=ProjectServiceResponse.from_record(target_service, dependencies=dependencies_for_target),
            repo_profile=RepoProfileResponse.from_record(repo_profile, secret_mounts=secret_mounts)
            if repo_profile is not None
            else None,
            startup_commands=list(repo_profile.startup_commands) if repo_profile is not None else [],
            healthcheck_command=target_service.sandbox_healthcheck_command,
            healthcheck_url=target_service.sandbox_healthcheck_url,
        )

    target_payload = await build_service_payload(service.id)
    dependency_payloads = [await build_service_payload(item.depends_on_service_id) for item in dependency_records]
    return ProjectSandboxPlanPreviewResponse(
        project_id=project_id,
        target_service=target_payload,
        dependency_services=dependency_payloads,
        warnings=warnings,
    )
    dependency_map: dict[str, list] = {}
    for item in project_service_dependencies:
        dependency_map.setdefault(item.service_id, []).append(item)
    project_services = [
        ProjectServiceResponse.from_record(
            record,
            dependencies=dependency_map.get(record.id, []),
        )
        for record in project_service_records
    ]
    return ProjectOnboardingResponse(
        project_id=project_id,
        policy=ProjectPolicyResponse.from_record(policy),
        secret_refs=secret_refs,
        api_keys=api_keys,
        integrations=integration_payloads,
        repo_profiles=repo_profiles,
        project_services=project_services,
        suggested_next_steps=_build_onboarding_next_steps(
            integrations=integration_payloads,
            secret_refs=secret_refs,
            repo_profiles=repo_profiles,
            project_services=project_services,
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


@router.delete("/secret-refs/{secret_ref_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_secret_ref(
    secret_ref_id: str,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    writer: SecretsWriter = Depends(get_secrets_writer),
) -> Response:
    record = await repository.get_secret_ref(secret_ref_id)
    if record is None:
        raise APIError(
            f"Secret ref {secret_ref_id} was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="secret_ref_not_found",
        )
    writer.delete_secret(external_ref=record.external_ref)
    await repository.delete_secret_ref(secret_ref_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@router.post(
    "/projects/{project_id}/browser-keys",
    response_model=ProjectBrowserKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_browser_key(
    request: Request,
    project_id: str,
    payload: CreateProjectBrowserKeyRequest,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ProjectBrowserKeyCreateResponse:
    plaintext_key, key_prefix = build_project_browser_key()
    record = await repository.create_project_browser_key(
        project_id=project_id,
        name=payload.name,
        key_prefix=key_prefix,
        key_hash=hash_api_key(plaintext_key),
        allowed_origins=payload.allowed_origins,
    )
    _invalidate_telemetry_origin_registry(request)
    return ProjectBrowserKeyCreateResponse(
        browser_key=ProjectBrowserKeyResponse.from_record(record),
        plaintext_key=plaintext_key,
    )


@router.get(
    "/projects/{project_id}/browser-keys",
    response_model=list[ProjectBrowserKeyResponse],
    status_code=status.HTTP_200_OK,
)
async def list_project_browser_keys(
    project_id: str,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> list[ProjectBrowserKeyResponse]:
    records = await repository.list_project_browser_keys(project_id)
    return [ProjectBrowserKeyResponse.from_record(record) for record in records]


@router.post(
    "/projects/{project_id}/browser-keys/{key_id}/revoke",
    response_model=ProjectBrowserKeyResponse,
    status_code=status.HTTP_200_OK,
)
async def revoke_project_browser_key(
    request: Request,
    project_id: str,
    key_id: str,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ProjectBrowserKeyResponse:
    record = await repository.get_project_browser_key(key_id)
    if record is None or record.project_id != project_id:
        raise APIError(
            f"Project browser key {key_id} was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="project_browser_key_not_found",
        )
    revoked = await repository.revoke_project_browser_key(key_id)
    _invalidate_telemetry_origin_registry(request)
    return ProjectBrowserKeyResponse.from_record(revoked)


@router.patch(
    "/projects/{project_id}/browser-keys/{key_id}",
    response_model=ProjectBrowserKeyResponse,
    status_code=status.HTTP_200_OK,
)
async def update_project_browser_key(
    request: Request,
    project_id: str,
    key_id: str,
    payload: UpdateProjectBrowserKeyRequest,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ProjectBrowserKeyResponse:
    record = await repository.get_project_browser_key(key_id)
    if record is None or record.project_id != project_id:
        raise APIError(
            f"Project browser key {key_id} was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="project_browser_key_not_found",
        )
    updated = await repository.update_project_browser_key(
        key_id,
        allowed_origins=payload.allowed_origins,
    )
    _invalidate_telemetry_origin_registry(request)
    return ProjectBrowserKeyResponse.from_record(updated)


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


@router.get(
    "/projects/{project_id}/onboarding-state",
    response_model=ProjectOnboardingStateResponse,
    status_code=status.HTTP_200_OK,
)
async def get_project_onboarding_state(
    project_id: str,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ProjectOnboardingStateResponse:
    record = await repository.get_or_create_project_onboarding_state(project_id)
    return ProjectOnboardingStateResponse.from_record(record)


@router.put(
    "/projects/{project_id}/onboarding-state",
    response_model=ProjectOnboardingStateResponse,
    status_code=status.HTTP_200_OK,
)
async def update_project_onboarding_state(
    project_id: str,
    payload: UpdateProjectOnboardingStateRequest,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ProjectOnboardingStateResponse:
    current = await repository.get_or_create_project_onboarding_state(project_id)
    record = await repository.update_project_onboarding_state(
        project_id=project_id,
        policy_reviewed=payload.policy_reviewed if payload.policy_reviewed is not None else current.policy_reviewed,
        sdk_setup_status=payload.sdk_setup_status or current.sdk_setup_status,
        sdk_setup_provider_repository_id=(
            payload.sdk_setup_provider_repository_id
            if payload.sdk_setup_provider_repository_id is not None
            else current.sdk_setup_provider_repository_id
        ),
        sdk_setup_change_request_url=(
            payload.sdk_setup_change_request_url
            if payload.sdk_setup_change_request_url is not None
            else current.sdk_setup_change_request_url
        ),
    )
    return ProjectOnboardingStateResponse.from_record(record)


@router.post(
    "/projects/{project_id}/sdk-bootstrap/plan",
    response_model=SdkBootstrapPlanPreviewResponse,
    status_code=status.HTTP_200_OK,
)
async def preview_project_sdk_bootstrap_plan(
    project_id: str,
    payload: CreateSdkBootstrapPlanRequest,
    service: ProviderIntegrationService = Depends(get_provider_integration_service),
    fallback_planner: SdkBootstrapFallbackPlanner | None = Depends(get_sdk_bootstrap_fallback_planner),
) -> SdkBootstrapPlanPreviewResponse:
    _assert_project_matches(project_id, payload.project_id)
    provider_repository, clone_url = await service.build_authenticated_repository_clone_url(
        project_id=project_id,
        provider_repository_id=payload.provider_repository_id,
    )
    plan = plan_sdk_bootstrap_from_clone(
        clone_url=clone_url,
        default_branch=provider_repository.default_branch,
        project_id=project_id,
        service_name=payload.service_name,
        environment=payload.environment,
        base_url=payload.base_url,
        fallback_planner=fallback_planner,
    )
    _log_sdk_bootstrap_plan(
        project_id=project_id,
        provider_repository_id=payload.provider_repository_id,
        plan=plan,
    )
    return _build_sdk_bootstrap_plan_response(plan)


@router.get(
    "/projects/{project_id}/telemetry-verification",
    response_model=ProjectTelemetryVerificationResponse,
    status_code=status.HTTP_200_OK,
)
async def get_project_telemetry_verification(
    project_id: str,
    service: str = Query(min_length=1, max_length=128),
    environment: str = Query(min_length=1, max_length=32),
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ProjectTelemetryVerificationResponse:
    heartbeat = await repository.get_project_telemetry_heartbeat(
        project_id=project_id,
        service=service.strip(),
        environment=environment.strip(),
    )
    return _build_project_telemetry_verification_response(
        service=service.strip(),
        environment=environment.strip(),
        heartbeat=heartbeat,
    )


@router.get(
    "/projects/{project_id}/harness-readiness",
    response_model=ProjectHarnessReadinessResponse,
    status_code=status.HTTP_200_OK,
)
async def get_project_harness_readiness(
    project_id: str,
    service: str = Query(min_length=1, max_length=128),
    environment: str = Query(min_length=1, max_length=32),
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ProjectHarnessReadinessResponse:
    return await _build_project_harness_readiness_response(
        project_id=project_id,
        service=service,
        environment=environment,
        repository=repository,
    )


@router.post(
    "/projects/{project_id}/sdk-bootstrap/preview",
    response_model=SdkBootstrapPreviewResponse,
    status_code=status.HTTP_200_OK,
)
async def preview_project_sdk_bootstrap_change_request(
    project_id: str,
    payload: CreateSdkBootstrapPreviewRequest,
    service: ProviderIntegrationService = Depends(get_provider_integration_service),
    fallback_planner: SdkBootstrapFallbackPlanner | None = Depends(get_sdk_bootstrap_fallback_planner),
) -> SdkBootstrapPreviewResponse:
    _assert_project_matches(project_id, payload.project_id)
    provider_repository, clone_url = await service.build_authenticated_repository_clone_url(
        project_id=project_id,
        provider_repository_id=payload.provider_repository_id,
    )
    prepared_preview = prepare_sdk_bootstrap_preview_from_clone(
        clone_url=clone_url,
        default_branch=provider_repository.default_branch,
        project_id=project_id,
        service_name=payload.service_name,
        environment=payload.environment,
        base_url=payload.base_url,
        strategy_id=payload.strategy_id,
        api_key=SDK_BOOTSTRAP_API_KEY_PLACEHOLDER,
        fallback_planner=fallback_planner,
    )
    _log_sdk_bootstrap_plan(
        project_id=project_id,
        provider_repository_id=payload.provider_repository_id,
        plan=prepared_preview.plan,
    )
    _log_sdk_bootstrap_strategy_event(
        event="sdk_bootstrap_preview_selected",
        project_id=project_id,
        provider_repository_id=payload.provider_repository_id,
        strategy=prepared_preview.strategy,
    )
    branch_name = f"stimpact/sdk-bootstrap-{uuid4().hex[:8]}"
    logger.info(
        "sdk_bootstrap_preview_ready project_id=%s provider_repository_id=%s strategy_id=%s run_id=%s branch_name=%s attempts=%s patch_lines=%s preview_available=%s change_request_allowed=%s verification_status=%s failure_stage=%s generation_ms=%s apply_ms=%s verification_ms=%s",
        project_id,
        payload.provider_repository_id,
        prepared_preview.selected_strategy_id,
        prepared_preview.run.run_id,
        branch_name,
        len(prepared_preview.run.attempts),
        len(prepared_preview.patch.patch_diff.splitlines()) if prepared_preview.patch.patch_diff else 0,
        prepared_preview.patch.attempt.preview_available,
        prepared_preview.patch.attempt.change_request_allowed,
        prepared_preview.patch.attempt.verification.status,
        prepared_preview.patch.attempt.failure_stage,
        prepared_preview.patch.attempt.generation_duration_ms,
        prepared_preview.patch.attempt.apply_duration_ms,
        prepared_preview.patch.attempt.verification_duration_ms,
    )
    attempt_responses = [
        _build_sdk_bootstrap_patch_attempt_response(item)
        for item in (
            prepared_preview.run.attempts
            if prepared_preview.run.attempts
            else ([prepared_preview.patch.attempt] if prepared_preview.patch.attempt is not None else [])
        )
    ]
    return SdkBootstrapPreviewResponse(
        run_id=prepared_preview.run.run_id,
        selected_strategy_id=prepared_preview.selected_strategy_id,
        strategy=_build_sdk_bootstrap_strategy_response(prepared_preview.strategy),
        pull_request=_build_sdk_bootstrap_pr_metadata(strategy=prepared_preview.strategy, branch_name=branch_name),
        patch_diff=prepared_preview.patch.patch_diff,
        attempt=_build_sdk_bootstrap_patch_attempt_response(prepared_preview.patch.attempt),
        attempts=attempt_responses,
    )


@router.post(
    "/projects/{project_id}/sdk-bootstrap/change-request",
    response_model=SdkBootstrapChangeRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_sdk_bootstrap_change_request(
    request: Request,
    project_id: str,
    payload: CreateSdkBootstrapChangeRequestRequest,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    service: ProviderIntegrationService = Depends(get_provider_integration_service),
    fallback_planner: SdkBootstrapFallbackPlanner | None = Depends(get_sdk_bootstrap_fallback_planner),
) -> SdkBootstrapChangeRequestResponse:
    _assert_project_matches(project_id, payload.project_id)
    provider_repository, clone_url = await service.build_authenticated_repository_clone_url(
        project_id=project_id,
        provider_repository_id=payload.provider_repository_id,
    )
    prepared_preview = prepare_sdk_bootstrap_preview_from_clone(
        clone_url=clone_url,
        default_branch=provider_repository.default_branch,
        project_id=project_id,
        service_name=payload.service_name,
        environment=payload.environment,
        base_url=payload.base_url,
        strategy_id=payload.strategy_id,
        api_key=SDK_BOOTSTRAP_API_KEY_PLACEHOLDER,
        fallback_planner=fallback_planner,
    )
    _log_sdk_bootstrap_plan(
        project_id=project_id,
        provider_repository_id=payload.provider_repository_id,
        plan=prepared_preview.plan,
    )
    _log_sdk_bootstrap_strategy_event(
        event="sdk_bootstrap_change_request_selected",
        project_id=project_id,
        provider_repository_id=payload.provider_repository_id,
        strategy=prepared_preview.strategy,
    )
    if not payload.branch_name:
        raise APIError(
            "Preview the SDK bootstrap PR draft and approve it before creating the real provider PR.",
            status_code=status.HTTP_409_CONFLICT,
            code="sdk_bootstrap_preview_required",
        )
    if not prepared_preview.patch.attempt.change_request_allowed or prepared_preview.patch.patch_diff is None:
        raise APIError(
            prepared_preview.patch.attempt.failure_reason
            or "Automatic SDK setup could not produce a verified reviewable patch for this repository.",
            status_code=status.HTTP_409_CONFLICT,
            code="sdk_bootstrap_preview_verification_failed",
        )
    uses_browser_credentials = _sdk_strategy_uses_browser_credentials(prepared_preview.strategy)
    if uses_browser_credentials and not payload.allowed_origins:
        raise APIError(
            "Browser-key SDK setup requires at least one allowed origin.",
            status_code=status.HTTP_400_BAD_REQUEST,
            code="browser_key_allowed_origins_required",
        )
    if uses_browser_credentials and payload.existing_api_key_id is not None:
        raise APIError(
            "This SDK bootstrap strategy expects a browser key, not an API key.",
            status_code=status.HTTP_400_BAD_REQUEST,
            code="sdk_bootstrap_existing_key_kind_mismatch",
        )
    if not uses_browser_credentials and payload.existing_browser_key_id is not None:
        raise APIError(
            "This SDK bootstrap strategy expects an API key, not a browser key.",
            status_code=status.HTTP_400_BAD_REQUEST,
            code="sdk_bootstrap_existing_key_kind_mismatch",
        )
    if payload.existing_plaintext_key is not None and (
        payload.existing_api_key_id is None and payload.existing_browser_key_id is None
    ):
        raise APIError(
            "A plaintext key can only be reused when paired with the matching existing key id.",
            status_code=status.HTTP_400_BAD_REQUEST,
            code="sdk_bootstrap_existing_key_id_required",
        )
    api_key_record = None
    browser_key_record = None
    if uses_browser_credentials:
        if payload.existing_browser_key_id is not None or payload.existing_plaintext_key is not None:
            if payload.existing_browser_key_id is None or payload.existing_plaintext_key is None:
                raise APIError(
                    "Reusing a browser key requires both the existing key id and plaintext key.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="sdk_bootstrap_existing_browser_key_incomplete",
                )
            browser_key_record = await repository.get_project_browser_key(payload.existing_browser_key_id)
            if (
                browser_key_record is None
                or browser_key_record.project_id != project_id
                or browser_key_record.status is not ProjectBrowserKeyStatus.ACTIVE
            ):
                raise APIError(
                    "The selected browser key is no longer active, so it cannot be reused for this PR.",
                    status_code=status.HTTP_409_CONFLICT,
                    code="sdk_bootstrap_existing_browser_key_invalid",
                )
            plaintext_key = payload.existing_plaintext_key
            if browser_key_record.key_hash != hash_api_key(plaintext_key):
                raise APIError(
                    "The saved plaintext browser key no longer matches the active key record.",
                    status_code=status.HTTP_409_CONFLICT,
                    code="sdk_bootstrap_existing_browser_key_mismatch",
                )
            if browser_key_record.allowed_origins != payload.allowed_origins:
                browser_key_record = await repository.update_project_browser_key(
                    payload.existing_browser_key_id,
                    allowed_origins=payload.allowed_origins,
                )
                _invalidate_telemetry_origin_registry(request)
        else:
            plaintext_key, key_prefix = build_project_browser_key()
            browser_key_record = await repository.create_project_browser_key(
                project_id=project_id,
                name=payload.api_key_name,
                key_prefix=key_prefix,
                key_hash=hash_api_key(plaintext_key),
                allowed_origins=payload.allowed_origins,
            )
            _invalidate_telemetry_origin_registry(request)
    else:
        if payload.existing_api_key_id is not None or payload.existing_plaintext_key is not None:
            if payload.existing_api_key_id is None or payload.existing_plaintext_key is None:
                raise APIError(
                    "Reusing an API key requires both the existing key id and plaintext key.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="sdk_bootstrap_existing_api_key_incomplete",
                )
            api_key_record = await repository.get_project_api_key(payload.existing_api_key_id)
            if (
                api_key_record is None
                or api_key_record.project_id != project_id
                or api_key_record.status is not ProjectApiKeyStatus.ACTIVE
            ):
                raise APIError(
                    "The selected API key is no longer active, so it cannot be reused for this PR.",
                    status_code=status.HTTP_409_CONFLICT,
                    code="sdk_bootstrap_existing_api_key_invalid",
                )
            plaintext_key = payload.existing_plaintext_key
            if api_key_record.key_hash != hash_api_key(plaintext_key):
                raise APIError(
                    "The saved plaintext API key no longer matches the active key record.",
                    status_code=status.HTTP_409_CONFLICT,
                    code="sdk_bootstrap_existing_api_key_mismatch",
                )
        else:
            plaintext_key, key_prefix = build_project_api_key()
            api_key_record = await repository.create_project_api_key(
                project_id=project_id,
                name=payload.api_key_name,
                key_prefix=key_prefix,
                key_hash=hash_api_key(plaintext_key),
            )
    bootstrap_patch = build_sdk_bootstrap_patch_from_clone(
        clone_url=clone_url,
        default_branch=provider_repository.default_branch,
        project_id=project_id,
        service_name=payload.service_name,
        environment=payload.environment,
        base_url=payload.base_url,
        strategy_id=prepared_preview.selected_strategy_id,
        api_key=plaintext_key,
        fallback_planner=fallback_planner,
    )
    logger.info(
        "sdk_bootstrap_change_request_ready project_id=%s provider_repository_id=%s strategy_id=%s branch_name=%s patch_lines=%s verification_status=%s generation_ms=%s apply_ms=%s verification_ms=%s",
        project_id,
        payload.provider_repository_id,
        prepared_preview.selected_strategy_id,
        payload.branch_name,
        len(bootstrap_patch.patch_diff.splitlines()) if bootstrap_patch.patch_diff else 0,
        bootstrap_patch.attempt.verification.status if bootstrap_patch.attempt is not None else "unknown",
        bootstrap_patch.attempt.generation_duration_ms if bootstrap_patch.attempt is not None else None,
        bootstrap_patch.attempt.apply_duration_ms if bootstrap_patch.attempt is not None else None,
        bootstrap_patch.attempt.verification_duration_ms if bootstrap_patch.attempt is not None else None,
    )
    pr_metadata = _build_sdk_bootstrap_pr_metadata(strategy=prepared_preview.strategy, branch_name=payload.branch_name)
    writeback = await service.propose_patch_writeback(
        provider_repository_id=payload.provider_repository_id,
        branch_name=pr_metadata.branch_name,
        patch_diff=bootstrap_patch.patch_diff or "",
        title=pr_metadata.title,
        description=pr_metadata.description,
        commit_message=pr_metadata.commit_message,
    )
    current_onboarding_state = await repository.get_or_create_project_onboarding_state(project_id)
    onboarding_state = await repository.update_project_onboarding_state(
        project_id=project_id,
        policy_reviewed=current_onboarding_state.policy_reviewed,
        sdk_setup_status=ProjectSdkSetupStatus.CHANGE_REQUEST,
        sdk_setup_provider_repository_id=payload.provider_repository_id,
        sdk_setup_change_request_url=writeback.change_request_url,
    )
    return SdkBootstrapChangeRequestResponse(
        run_id=prepared_preview.run.run_id,
        credential_kind="browser_key" if uses_browser_credentials else "server_api_key",
        api_key=ProjectApiKeyResponse.from_record(api_key_record) if api_key_record is not None else None,
        browser_key=(
            ProjectBrowserKeyResponse.from_record(browser_key_record)
            if browser_key_record is not None
            else None
        ),
        plaintext_key=plaintext_key,
        branch_name=writeback.branch_name,
        commit_sha=writeback.commit_sha,
        change_request_url=writeback.change_request_url,
        reference_id=writeback.reference_id,
        mergeable=writeback.mergeable,
        final_attempt=(
            _build_sdk_bootstrap_patch_attempt_response(bootstrap_patch.attempt)
            if bootstrap_patch.attempt is not None
            else None
        ),
        onboarding_state=ProjectOnboardingStateResponse.from_record(onboarding_state),
    )


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
    onboarding_state = await repository.get_or_create_project_onboarding_state(project_id)
    await repository.update_project_onboarding_state(
        project_id=project_id,
        policy_reviewed=True,
        sdk_setup_status=onboarding_state.sdk_setup_status,
        sdk_setup_provider_repository_id=onboarding_state.sdk_setup_provider_repository_id,
        sdk_setup_change_request_url=onboarding_state.sdk_setup_change_request_url,
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
    "/provider-integrations/github-app/start",
    response_model=GitHubAppInstallStartResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_github_app_install(
    payload: StartGitHubAppInstallRequest,
    service: ProviderIntegrationService = Depends(get_provider_integration_service),
) -> GitHubAppInstallStartResponse:
    integration, installation_url = await service.start_github_app_install(
        project_id=payload.project_id,
        name=payload.name,
        redirect_url=payload.redirect_url,
    )
    return GitHubAppInstallStartResponse(
        integration=ProviderIntegrationResponse.from_record(integration),
        installation_url=installation_url,
    )


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


@project_router.delete("/secret-refs/{secret_ref_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_secret_ref(
    project_id: str,
    secret_ref_id: str,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
    writer: SecretsWriter = Depends(get_secrets_writer),
) -> Response:
    record = await repository.get_secret_ref(secret_ref_id)
    if record is None or record.project_id != project_id:
        raise APIError(
            f"Secret ref {secret_ref_id} was not found for project {project_id}.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="secret_ref_not_found",
        )
    writer.delete_secret(external_ref=record.external_ref)
    await repository.delete_secret_ref(secret_ref_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    "/provider-integrations/github-app/start",
    response_model=GitHubAppInstallStartResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_project_github_app_install(
    project_id: str,
    payload: StartGitHubAppInstallRequest,
    service: ProviderIntegrationService = Depends(get_provider_integration_service),
) -> GitHubAppInstallStartResponse:
    _assert_project_matches(project_id, payload.project_id)
    return await start_github_app_install(payload, service=service)


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


@project_router.get(
    "/provider-repositories/{provider_repository_id}/repo-profile-defaults",
    response_model=RepoProfileInferenceResponse,
    status_code=status.HTTP_200_OK,
)
async def infer_project_repo_profile_defaults(
    project_id: str,
    provider_repository_id: str,
    service: ProviderIntegrationService = Depends(get_provider_integration_service),
) -> RepoProfileInferenceResponse:
    inference = await service.infer_repo_profile_defaults(
        project_id=project_id,
        provider_repository_id=provider_repository_id,
    )
    return RepoProfileInferenceResponse(
        runtime_kind=inference.runtime_kind,
        base_image=inference.base_image,
        install_command=inference.install_command,
        reproduce_command=inference.reproduce_command,
        verify_command=inference.verify_command,
        detected_from=inference.detected_from,
        warnings=inference.warnings,
        monorepo=inference.monorepo,
    )


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


@project_router.post("/services", response_model=ProjectServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_project_service(
    project_id: str,
    payload: CreateProjectServiceRequest,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ProjectServiceResponse:
    _assert_project_matches(project_id, payload.project_id)
    if payload.repo_profile_id is not None:
        repo_profile = await repository.get_repo_profile(payload.repo_profile_id)
        if repo_profile is None or repo_profile.project_id != project_id:
            raise APIError(
                f"Repo profile {payload.repo_profile_id} was not found for project {project_id}.",
                status_code=status.HTTP_404_NOT_FOUND,
                code="repo_profile_not_found",
            )
    record = await repository.create_project_service(
        project_id=project_id,
        name=payload.name,
        slug=payload.slug,
        service_type=payload.service_type,
        repo_profile_id=payload.repo_profile_id,
        owner=payload.owner,
        deploy_target=payload.deploy_target,
        routing_hints=payload.routing_hints.to_record(),
        startup_priority=payload.startup_priority,
        sandbox_healthcheck_command=payload.sandbox_healthcheck_command,
        sandbox_healthcheck_url=payload.sandbox_healthcheck_url,
        active=payload.active,
    )
    dependencies = await repository.replace_project_service_dependencies(
        record.id,
        [
            (item.depends_on_service_id, item.dependency_kind)
            for item in payload.dependencies
        ],
    )
    return ProjectServiceResponse.from_record(record, dependencies=dependencies)


@project_router.get("/services", response_model=list[ProjectServiceResponse], status_code=status.HTTP_200_OK)
async def list_project_services(
    project_id: str,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> list[ProjectServiceResponse]:
    records = await repository.list_project_services(project_id)
    dependencies = await repository.list_project_dependencies_for_services([record.id for record in records])
    dependency_map: dict[str, list] = {}
    for item in dependencies:
        dependency_map.setdefault(item.service_id, []).append(item)
    return [
        ProjectServiceResponse.from_record(record, dependencies=dependency_map.get(record.id, []))
        for record in records
    ]


@project_router.put("/services/{service_id}", response_model=ProjectServiceResponse, status_code=status.HTTP_200_OK)
async def update_project_service(
    project_id: str,
    service_id: str,
    payload: UpdateProjectServiceRequest,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ProjectServiceResponse:
    existing = await repository.get_project_service(service_id)
    if existing is None or existing.project_id != project_id:
        raise APIError(
            f"Project service {service_id} was not found for project {project_id}.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="project_service_not_found",
        )
    if payload.repo_profile_id is not None:
        repo_profile = await repository.get_repo_profile(payload.repo_profile_id)
        if repo_profile is None or repo_profile.project_id != project_id:
            raise APIError(
                f"Repo profile {payload.repo_profile_id} was not found for project {project_id}.",
                status_code=status.HTTP_404_NOT_FOUND,
                code="repo_profile_not_found",
            )
    record = await repository.update_project_service(
        service_id,
        name=payload.name,
        slug=payload.slug,
        service_type=payload.service_type,
        repo_profile_id=payload.repo_profile_id,
        owner=payload.owner,
        deploy_target=payload.deploy_target,
        routing_hints=payload.routing_hints.to_record(),
        startup_priority=payload.startup_priority,
        sandbox_healthcheck_command=payload.sandbox_healthcheck_command,
        sandbox_healthcheck_url=payload.sandbox_healthcheck_url,
        active=payload.active,
    )
    dependencies = await repository.replace_project_service_dependencies(
        record.id,
        [
            (item.depends_on_service_id, item.dependency_kind)
            for item in payload.dependencies
        ],
    )
    return ProjectServiceResponse.from_record(record, dependencies=dependencies)


@project_router.get(
    "/services/{service_id}/sandbox-plan",
    response_model=ProjectSandboxPlanPreviewResponse,
    status_code=status.HTTP_200_OK,
)
async def get_project_service_sandbox_plan(
    project_id: str,
    service_id: str,
    repository: ControlPlaneRepository = Depends(get_control_plane_repository),
) -> ProjectSandboxPlanPreviewResponse:
    return await _build_project_sandbox_plan_preview(
        project_id=project_id,
        service_id=service_id,
        repository=repository,
    )


@public_router.get(
    "/api/github/callback",
    response_model=None,
    status_code=status.HTTP_200_OK,
)
async def github_callback(
    installation_id: str | None = Query(default=None),
    setup_action: str | None = Query(default=None),
    state: str | None = Query(default=None),
    service: ProviderIntegrationService = Depends(get_provider_integration_service),
) -> object:
    if state is not None and installation_id is not None:
        result = await service.complete_github_app_callback(
            state=state,
            installation_id=installation_id,
            setup_action=setup_action,
        )
        project_id = str(result.integration.metadata.get("project_id", "")).strip()
        redirect_url = result.redirect_url.strip() if isinstance(result.redirect_url, str) else ""
        if not redirect_url:
            frontend_base_url = get_frontend_base_url()
            if frontend_base_url is not None:
                redirect_url = f"{frontend_base_url.rstrip('/')}/onboarding"
                if project_id:
                    redirect_url = f"{redirect_url}?project_id={project_id}"
        if redirect_url:
            return RedirectResponse(
                url=service.build_callback_redirect_url(
                    redirect_url=redirect_url,
                    provider=ProviderKind.GITHUB,
                    project_id=project_id,
                    integration_id=result.integration.id,
                    installation_id=result.installation_id,
                    setup_action=result.setup_action,
                    synced_repository_count=result.synced_repository_count,
                ),
                status_code=status.HTTP_303_SEE_OTHER,
            )
        raise APIError(
            "GitHub installation completed but no frontend redirect URL is configured.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="github_redirect_missing",
        )
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
