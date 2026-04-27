from __future__ import annotations

import importlib
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.core.errors import APIError, register_exception_handlers
from api.middleware.telemetry_cors import install_telemetry_cors_middleware
from api.core.security import (
    build_browser_ingest_token,
    get_security_control_plane_repository,
    hash_api_key,
)
from api.events.publisher import IncidentEventPublisher
from api.routes.control_plane import (
    get_control_plane_repository,
    get_provider_integration_service,
    project_router as project_control_plane_router,
    get_secrets_writer,
    public_router as provider_callback_router,
    router as control_plane_router,
)
from api.routes.health import router as health_router
from api.routes.incident_chat import (
    get_control_plane_repository as get_incident_chat_control_plane_repository,
    get_incident_chat_service,
    get_incident_repository as get_incident_chat_repository,
    router as incident_chat_router,
)
from api.routes.incidents import (
    get_autonomous_run_service,
    get_artifact_repository,
    get_control_plane_repository as get_incident_control_plane_repository,
    get_failure_classifier,
    get_incident_repository,
    get_patch_generation_service,
    get_root_cause_analysis_service,
    get_sandbox_repository,
    get_sandbox_verification_service,
    router as incidents_router,
)
from api.routes.telemetry import (
    get_control_plane_repository as get_telemetry_control_plane_repository,
    get_incident_event_publisher,
    get_outbox_signaler,
    get_telemetry_repository,
    router as telemetry_router,
)
from api.schemas.autonomous import AutonomousRunCreateRequest, AutonomousRunDetailResponse
from harness.schemas.autonomous import (
    AutonomousArtifactPaths,
    AutonomousPromotionStatus,
    AutonomousRepairRunRecord,
    AutonomousRunEvent,
    AutonomousRunOutcome,
    AutonomousRunPhase,
    AutonomousRunStatus,
)
from harness.schemas.autonomous import AutonomousEventType
from harness.schemas.initializer import FeatureSeed
from models.async_job import AsyncJobStatus
from models.control_plane import (
    AutonomyMode,
    ProjectApiKeyRecord,
    ProjectApiKeyStatus,
    ProjectBrowserKeyRecord,
    ProjectBrowserKeyStatus,
    ProjectOnboardingStateRecord,
    ProjectPolicyRecord,
    ProjectServiceDependencyKind,
    ProjectServiceDependencyRecord,
    ProjectServiceRecord,
    ProjectServiceRoutingHints,
    ProjectServiceType,
    ProjectSdkSetupStatus,
    ProjectTelemetryHeartbeatRecord,
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
from models.failure_classification import FailureCategory, FailureClassification
from models.incident import (
    IncidentEventRecord,
    IncidentProcessingResult,
    IncidentRecord,
    IncidentSeverity,
    IncidentStatus,
)
from models.live_operations_metrics import LiveOperationsMetricsRecord
from models.patch import PatchRunRecord, PatchRunStatus, PatchTargetFile
from models.root_cause import RootCauseAnalysis, RootCauseEvidence, RootCauseReasoning
from models.sandbox import (
    SandboxRunAttemptRecord,
    SandboxRunRecord,
    SandboxRunStatus,
    SandboxRunStepRecord,
)
from shared.events.incident_events import IncidentEvent, IncidentEventType
from shared.types.telemetry import Environment
from services.provider_clients import ProviderInstallation
from services.provider_integration_service import (
    GitHubCallbackPreview,
    GitHubCallbackResult,
    GitLabCallbackResult,
    ProviderWritebackResult,
)
from services.repo_profile_inference import RepoProfileInferenceResult
from services.telemetry_origin_registry import TelemetryOriginRegistry


def build_test_app() -> FastAPI:
    class StubPostgresManager:
        is_configured = True
        pool = None

        async def ping(self) -> bool:
            return True

    app = FastAPI()
    app.state.postgres = StubPostgresManager()
    register_exception_handlers(app)
    install_telemetry_cors_middleware(app)
    app.include_router(health_router)
    app.include_router(telemetry_router)
    app.include_router(incident_chat_router)
    app.include_router(incidents_router)
    app.include_router(control_plane_router)
    app.include_router(project_control_plane_router)
    app.include_router(provider_callback_router)
    return app


class RecordingTelemetryRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    async def insert_event_with_outbox(self, telemetry: object, incident_event: object) -> str:
        self.calls.append((telemetry, incident_event))
        return "outbox-1"


class RecordingOutboxSignaler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def signal(self, *, event_id: str, event_type: str) -> None:
        self.calls.append((event_id, event_type))


class StubIncidentRepository:
    def __init__(self) -> None:
        now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
        self.incident = IncidentRecord(
            id="incident-1",
            project_id="project-1",
            fingerprint="fingerprint-1",
            service="billing-api",
            environment=Environment.PRODUCTION,
            title="billing-api: Database timeout",
            status=IncidentStatus.OPEN,
            severity=IncidentSeverity.CRITICAL,
            first_seen_at=now,
            last_seen_at=now,
            event_count=2,
            latest_telemetry_id="telemetry-2",
            created_at=now,
            updated_at=now,
        )
        self.events = [
            IncidentEventRecord(
                id="event-1",
                incident_id="incident-1",
                telemetry_id="telemetry-2",
                event_type="telemetry.received",
                error_message="Database timeout",
                stacktrace="Traceback:\nline 1",
                request_payload={"method": "POST"},
                response_payload={"status_code": 503},
                payload={"environment": "production"},
                occurred_at=now,
                created_at=now,
            )
        ]
        self.last_list_kwargs: dict[str, object] | None = None
        self.status_updates: list[IncidentStatus] = []

    async def list_incidents(
        self,
        *,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[IncidentRecord], int]:
        self.last_list_kwargs = {
            "project_id": project_id,
            "status": status,
            "limit": limit,
            "offset": offset,
        }
        return [self.incident], 1

    async def get_incident(self, incident_id: str) -> IncidentRecord | None:
        return self.incident if incident_id == self.incident.id else None

    async def list_incident_events(self, incident_id: str, *, limit: int = 100) -> list[IncidentEventRecord]:
        assert incident_id == self.incident.id
        assert limit >= 1
        return self.events[:limit]

    async def fetch_live_operations_metrics(self, project_id: str) -> LiveOperationsMetricsRecord:
        assert project_id == "project-1"
        return LiveOperationsMetricsRecord(
            uptime_percent_last_30d=90.0,
            uptime_percent_prior_30d=85.0,
            avg_agent_response_seconds_last_30d=300.0,
            avg_agent_response_seconds_prior_30d=400.0,
            open_incidents=1,
            agent_resolution_percent_last_30d=50.0,
            agent_resolution_percent_prior_30d=40.0,
        )

    async def update_incident_status(
        self,
        incident_id: str,
        new_status: IncidentStatus,
        *,
        resolution_source: str | None = None,
    ) -> IncidentRecord:
        _ = resolution_source
        assert incident_id == self.incident.id
        self.status_updates.append(new_status)
        self.incident = self.incident.model_copy(update={"status": new_status})
        return self.incident


class StubFailureClassifier:
    def classify(
        self,
        incident: IncidentRecord,
        events: list[IncidentEventRecord],
    ) -> FailureClassification:
        return self._result(incident, events)

    async def classify_async(
        self,
        incident: IncidentRecord,
        events: list[IncidentEventRecord],
    ) -> FailureClassification:
        return self._result(incident, events)

    def _result(
        self,
        incident: IncidentRecord,
        events: list[IncidentEventRecord],
    ) -> FailureClassification:
        assert incident.id == "incident-1"
        assert len(events) == 1
        return FailureClassification(
            category=FailureCategory.DATABASE_FAILURE,
            confidence=0.91,
            summary="The billing-api incident is most likely a database failure based on database, postgres.",
            matched_signals=["database", "postgres"],
            inspected_event_count=len(events),
        )


class StubIncidentChatService:
    async def chat_about_incidents(self, payload) -> object:
        project_id = getattr(payload, "project_id", None) or "all-projects"
        return {
            "answer": f"Summarized incidents for {project_id}.",
            "referenced_incident_ids": ["incident-1"],
        }

    async def chat_about_incident(self, incident_id: str, payload) -> object:
        _ = payload
        return {
            "answer": f"Summarized incident {incident_id}.",
            "referenced_incident_ids": [incident_id],
        }


class StubControlPlaneRepository:
    def __init__(self) -> None:
        now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
        self.attached_mounts: list[str] = []
        self.project_api_keys: list[ProjectApiKeyRecord] = []
        self.project_browser_keys: list[ProjectBrowserKeyRecord] = []
        self.project_telemetry_heartbeats: list[ProjectTelemetryHeartbeatRecord] = []
        self.secret_ref = SecretRefRecord(
            id="secret-1",
            project_id="project-1",
            label="OPENAI_API_KEY",
            description="Runtime secret",
            backend=SecretBackend.AWS_SECRETS_MANAGER,
            external_ref="arn:aws:secretsmanager:us-east-1:123456789012:secret:stimpact/project-1/OPENAI_API_KEY",
            created_at=now,
            updated_at=now,
        )
        self.provider_integration = ProviderIntegrationRecord(
            id="integration-1",
            provider=ProviderKind.GITHUB,
            name="Acme GitHub",
            status=ProviderIntegrationStatus.ACTIVE,
            credentials_secret_ref_id=self.secret_ref.id,
            webhook_secret_ref_id=None,
            aws_region="us-east-1",
            metadata={"project_id": "project-1", "installation_id": "117170229"},
            created_at=now,
            updated_at=now,
        )
        self.provider_repository = ProviderRepositoryRecord(
            id="provider-repo-1",
            provider_integration_id="integration-1",
            provider=ProviderKind.GITHUB,
            external_repository_id="123",
            owner="acme",
            name="billing-api",
            default_branch="main",
            clone_url="https://github.com/acme/billing-api.git",
            created_at=now,
            updated_at=now,
        )
        self.repo_profile = RepoProfileRecord(
            id="profile-1",
            project_id="project-1",
            provider_repository_id="provider-repo-1",
            runtime_kind=RuntimeKind.PYTHON,
            base_image="public.ecr.aws/docker/library/python:3.12",
            install_command="pip install -r requirements.txt",
            startup_commands=["python app.py"],
            reproduce_command="python reproduce.py",
            verify_command="pytest",
            success_criteria="Exit 0 after patch verification.",
            network_allowlist=["pypi.org"],
            active=True,
            created_at=now,
            updated_at=now,
        )
        self.project_policy = ProjectPolicyRecord(
            project_id="project-1",
            autonomy_mode=AutonomyMode.RECOMMEND,
            require_human_approval=True,
            allow_production_writes=False,
            allow_low_risk_autonomy=True,
            block_during_active_deploys=True,
            restrict_to_approved_services=False,
            require_rollback_plan=True,
            require_post_action_verification=True,
            approved_services=["billing-api"],
            failure_classifier_enabled=True,
            root_cause_enabled=True,
            patch_planner_enabled=True,
            runbook_executor_enabled=False,
            created_at=now,
            updated_at=now,
        )
        self.project_onboarding_state = ProjectOnboardingStateRecord(
            project_id="project-1",
            policy_reviewed=False,
            sdk_setup_status=ProjectSdkSetupStatus.PENDING,
            sdk_setup_provider_repository_id=None,
            sdk_setup_change_request_url=None,
            created_at=now,
            updated_at=now,
        )
        self.project_service = ProjectServiceRecord(
            id="service-1",
            project_id="project-1",
            name="Billing API",
            slug="billing-api",
            service_type=ProjectServiceType.API,
            repo_profile_id=self.repo_profile.id,
            owner="platform",
            deploy_target="staging",
            routing_hints=ProjectServiceRoutingHints(
                service_names=["billing-api"],
                path_prefixes=["/retry-policy"],
                domains=["billing.example.com"],
                tags=["payments"],
            ),
            startup_priority=10,
            sandbox_healthcheck_command="python healthcheck.py",
            sandbox_healthcheck_url=None,
            active=True,
            created_at=now,
            updated_at=now,
        )
        self.dependency_service = ProjectServiceRecord(
            id="service-2",
            project_id="project-1",
            name="Redis Cache",
            slug="redis-cache",
            service_type=ProjectServiceType.CACHE,
            repo_profile_id=None,
            owner="platform",
            deploy_target="staging",
            routing_hints=ProjectServiceRoutingHints(tags=["cache"]),
            startup_priority=20,
            sandbox_healthcheck_command=None,
            sandbox_healthcheck_url=None,
            active=True,
            created_at=now,
            updated_at=now,
        )

    async def create_secret_ref(self, **kwargs) -> SecretRefRecord:
        assert kwargs["project_id"] == "project-1"
        return self.secret_ref

    async def list_secret_refs(self, project_id: str) -> list[SecretRefRecord]:
        assert project_id == "project-1"
        return [self.secret_ref]

    async def get_secret_ref(self, secret_ref_id: str) -> SecretRefRecord | None:
        return self.secret_ref if secret_ref_id == self.secret_ref.id else None

    async def delete_secret_ref(self, secret_ref_id: str) -> SecretRefRecord | None:
        if secret_ref_id != self.secret_ref.id:
            return None
        deleted = self.secret_ref
        self.secret_ref = self.secret_ref.model_copy(update={"id": "deleted-secret"})
        return deleted

    async def create_project_api_key(
        self,
        *,
        project_id: str,
        name: str,
        key_prefix: str,
        key_hash: str,
        status: ProjectApiKeyStatus = ProjectApiKeyStatus.ACTIVE,
    ) -> ProjectApiKeyRecord:
        record = ProjectApiKeyRecord(
            id=f"api-key-{len(self.project_api_keys) + 1}",
            project_id=project_id,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            status=status,
            last_used_at=None,
            revoked_at=None,
            created_at=self.secret_ref.created_at,
            updated_at=self.secret_ref.updated_at,
        )
        self.project_api_keys.append(record)
        return record

    async def list_project_api_keys(self, project_id: str) -> list[ProjectApiKeyRecord]:
        return [record for record in self.project_api_keys if record.project_id == project_id]

    async def get_project_api_key(self, key_id: str) -> ProjectApiKeyRecord | None:
        for record in self.project_api_keys:
            if record.id == key_id:
                return record
        return None

    async def find_active_project_api_key(
        self,
        *,
        project_id: str,
        key_hash: str,
    ) -> ProjectApiKeyRecord | None:
        for record in self.project_api_keys:
            if (
                record.project_id == project_id
                and record.key_hash == key_hash
                and record.status is ProjectApiKeyStatus.ACTIVE
            ):
                return record
        return None

    async def has_active_project_api_keys(self, project_id: str) -> bool:
        return any(
            record.project_id == project_id and record.status is ProjectApiKeyStatus.ACTIVE
            for record in self.project_api_keys
        )

    async def create_project_browser_key(
        self,
        *,
        project_id: str,
        name: str,
        key_prefix: str,
        key_hash: str,
        allowed_origins: list[str],
        status: ProjectBrowserKeyStatus = ProjectBrowserKeyStatus.ACTIVE,
    ) -> ProjectBrowserKeyRecord:
        record = ProjectBrowserKeyRecord(
            id=f"browser-key-{len(self.project_browser_keys) + 1}",
            project_id=project_id,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            allowed_origins=list(allowed_origins),
            status=status,
            last_used_at=None,
            last_issued_at=None,
            revoked_at=None,
            created_at=self.secret_ref.created_at,
            updated_at=self.secret_ref.updated_at,
        )
        self.project_browser_keys.append(record)
        return record

    async def list_project_browser_keys(self, project_id: str) -> list[ProjectBrowserKeyRecord]:
        return [record for record in self.project_browser_keys if record.project_id == project_id]

    async def get_project_browser_key(self, key_id: str) -> ProjectBrowserKeyRecord | None:
        for record in self.project_browser_keys:
            if record.id == key_id:
                return record
        return None

    async def find_active_project_browser_key(
        self,
        *,
        project_id: str,
        key_hash: str,
    ) -> ProjectBrowserKeyRecord | None:
        for record in self.project_browser_keys:
            if (
                record.project_id == project_id
                and record.key_hash == key_hash
                and record.status is ProjectBrowserKeyStatus.ACTIVE
            ):
                return record
        return None

    async def has_active_project_browser_keys(self, project_id: str) -> bool:
        return any(
            record.project_id == project_id and record.status is ProjectBrowserKeyStatus.ACTIVE
            for record in self.project_browser_keys
        )

    async def list_active_project_browser_key_origins(self) -> list[str]:
        origins: list[str] = []
        seen: set[str] = set()
        for record in self.project_browser_keys:
            if record.status is not ProjectBrowserKeyStatus.ACTIVE:
                continue
            for origin in record.allowed_origins:
                normalized = origin.lower()
                if normalized in seen:
                    continue
                seen.add(normalized)
                origins.append(normalized)
        return origins

    async def mark_project_api_key_used(self, key_id: str) -> ProjectApiKeyRecord:
        for index, record in enumerate(self.project_api_keys):
            if record.id == key_id:
                updated = record.model_copy(update={"last_used_at": datetime.now(tz=UTC)})
                self.project_api_keys[index] = updated
                return updated
        raise AssertionError(f"unknown project api key {key_id}")

    async def mark_project_browser_key_used(self, key_id: str) -> ProjectBrowserKeyRecord:
        for index, record in enumerate(self.project_browser_keys):
            if record.id == key_id:
                updated = record.model_copy(update={"last_used_at": datetime.now(tz=UTC)})
                self.project_browser_keys[index] = updated
                return updated
        raise AssertionError(f"unknown project browser key {key_id}")

    async def mark_project_browser_key_issued(self, key_id: str) -> ProjectBrowserKeyRecord:
        for index, record in enumerate(self.project_browser_keys):
            if record.id == key_id:
                updated = record.model_copy(update={"last_issued_at": datetime.now(tz=UTC)})
                self.project_browser_keys[index] = updated
                return updated
        raise AssertionError(f"unknown project browser key {key_id}")

    async def revoke_project_api_key(self, key_id: str) -> ProjectApiKeyRecord:
        for index, record in enumerate(self.project_api_keys):
            if record.id == key_id:
                updated = record.model_copy(
                    update={
                        "status": ProjectApiKeyStatus.REVOKED,
                        "revoked_at": datetime.now(tz=UTC),
                    }
                )
                self.project_api_keys[index] = updated
                return updated
        raise AssertionError(f"unknown project api key {key_id}")

    async def revoke_project_browser_key(self, key_id: str) -> ProjectBrowserKeyRecord:
        for index, record in enumerate(self.project_browser_keys):
            if record.id == key_id:
                updated = record.model_copy(
                    update={
                        "status": ProjectBrowserKeyStatus.REVOKED,
                        "revoked_at": datetime.now(tz=UTC),
                    }
                )
                self.project_browser_keys[index] = updated
                return updated
        raise AssertionError(f"unknown project browser key {key_id}")

    async def update_project_browser_key(
        self,
        key_id: str,
        *,
        allowed_origins: list[str],
    ) -> ProjectBrowserKeyRecord:
        for index, record in enumerate(self.project_browser_keys):
            if record.id == key_id:
                updated = record.model_copy(
                    update={
                        "allowed_origins": list(allowed_origins),
                        "updated_at": datetime.now(tz=UTC),
                    }
                )
                self.project_browser_keys[index] = updated
                return updated
        raise AssertionError(f"unknown project browser key {key_id}")

    async def upsert_project_telemetry_heartbeat(
        self,
        *,
        project_id: str,
        service: str,
        environment: str,
        last_seen_at,
        commit_sha: str | None,
    ) -> ProjectTelemetryHeartbeatRecord:
        record = ProjectTelemetryHeartbeatRecord(
            project_id=project_id,
            service=service,
            environment=Environment(environment),
            last_seen_at=last_seen_at,
            commit_sha=commit_sha,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        self.project_telemetry_heartbeats = [
            item
            for item in self.project_telemetry_heartbeats
            if not (
                item.project_id == project_id
                and item.service == service
                and item.environment.value == environment
            )
        ]
        self.project_telemetry_heartbeats.append(record)
        return record

    async def get_project_telemetry_heartbeat(
        self,
        *,
        project_id: str,
        service: str,
        environment: str,
    ) -> ProjectTelemetryHeartbeatRecord | None:
        for item in self.project_telemetry_heartbeats:
            if item.project_id == project_id and item.service == service and item.environment.value == environment:
                return item
        return None

    async def list_project_telemetry_heartbeats(self, project_id: str) -> list[ProjectTelemetryHeartbeatRecord]:
        return [item for item in self.project_telemetry_heartbeats if item.project_id == project_id]

    async def get_or_create_project_policy(self, project_id: str) -> ProjectPolicyRecord:
        assert project_id == self.project_policy.project_id
        return self.project_policy

    async def get_or_create_project_onboarding_state(self, project_id: str) -> ProjectOnboardingStateRecord:
        assert project_id == self.project_onboarding_state.project_id
        return self.project_onboarding_state

    async def update_project_onboarding_state(self, *, project_id: str, **kwargs) -> ProjectOnboardingStateRecord:
        assert project_id == self.project_onboarding_state.project_id
        self.project_onboarding_state = self.project_onboarding_state.model_copy(update=kwargs)
        return self.project_onboarding_state

    async def update_project_policy(self, *, project_id: str, **kwargs) -> ProjectPolicyRecord:
        assert project_id == self.project_policy.project_id
        self.project_policy = self.project_policy.model_copy(update=kwargs)
        return self.project_policy

    async def create_provider_integration(self, **kwargs) -> ProviderIntegrationRecord:
        assert kwargs["provider"] is ProviderKind.GITHUB
        return self.provider_integration

    async def list_provider_integrations(
        self,
        project_id: str | None = None,
    ) -> list[ProviderIntegrationRecord]:
        if project_id is None or self.provider_integration.metadata.get("project_id") == project_id:
            return [self.provider_integration]
        return []

    async def get_provider_integration(self, provider_integration_id: str) -> ProviderIntegrationRecord | None:
        return self.provider_integration if provider_integration_id == self.provider_integration.id else None

    async def list_provider_repositories(self, provider_integration_id: str) -> list[ProviderRepositoryRecord]:
        if provider_integration_id == self.provider_integration.id:
            return [self.provider_repository]
        return []

    async def create_provider_repository(self, **kwargs):
        now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
        return ProviderRepositoryRecord(
            id="provider-repo-1",
            provider_integration_id="integration-1",
            provider=ProviderKind.GITHUB,
            external_repository_id="123",
            owner="acme",
            name="billing-api",
            default_branch="main",
            clone_url="https://github.com/acme/billing-api.git",
            created_at=now,
            updated_at=now,
        )

    async def create_repo_profile(self, **kwargs) -> RepoProfileRecord:
        assert kwargs["project_id"] == "project-1"
        return self.repo_profile

    async def attach_secret_ref_to_repo_profile(self, **kwargs) -> None:
        assert kwargs["repo_profile_id"] == self.repo_profile.id
        self.attached_mounts.append(kwargs["mount_as"])

    async def list_repo_profile_secret_refs(self, repo_profile_id: str) -> list[SecretRefRecord]:
        assert repo_profile_id == self.repo_profile.id
        return [self.secret_ref]

    async def list_repo_profile_secret_bindings(
        self,
        repo_profile_id: str,
    ) -> list[RepoProfileSecretBindingRecord]:
        assert repo_profile_id == self.repo_profile.id
        return [
            RepoProfileSecretBindingRecord(
                repo_profile_id=self.repo_profile.id,
                mount_as=self.attached_mounts[-1] if self.attached_mounts else self.secret_ref.label,
                secret_ref=self.secret_ref,
                created_at=self.secret_ref.created_at,
            )
        ]

    async def list_repo_profiles(self, project_id: str) -> list[RepoProfileRecord]:
        assert project_id == "project-1"
        return [self.repo_profile]

    async def get_repo_profile(self, repo_profile_id: str) -> RepoProfileRecord | None:
        if repo_profile_id == self.repo_profile.id:
            return self.repo_profile
        return None

    async def get_active_repo_profile(self, project_id: str) -> RepoProfileRecord | None:
        if project_id == self.repo_profile.project_id:
            return self.repo_profile
        return None

    async def get_provider_repository(self, provider_repository_id: str) -> ProviderRepositoryRecord | None:
        if provider_repository_id == self.provider_repository.id:
            return self.provider_repository
        return None

    async def list_project_services(self, project_id: str) -> list[ProjectServiceRecord]:
        assert project_id == "project-1"
        return [self.project_service, self.dependency_service]

    async def get_project_service(self, service_id: str) -> ProjectServiceRecord | None:
        if service_id == self.project_service.id:
            return self.project_service
        if service_id == self.dependency_service.id:
            return self.dependency_service
        return None

    async def list_project_service_dependencies(
        self,
        service_id: str,
    ) -> list[ProjectServiceDependencyRecord]:
        if service_id != self.project_service.id:
            return []
        return [
            ProjectServiceDependencyRecord(
                service_id=self.project_service.id,
                depends_on_service_id=self.dependency_service.id,
                dependency_kind=ProjectServiceDependencyKind.REQUIRED,
                created_at=self.project_service.created_at,
            )
        ]

    async def list_project_dependencies_for_services(
        self,
        service_ids: list[str],
    ) -> list[ProjectServiceDependencyRecord]:
        if self.project_service.id in service_ids:
            return await self.list_project_service_dependencies(self.project_service.id)
        return []

    async def resolve_project_service(
        self,
        *,
        project_id: str,
        service_name: str,
        stacktrace: str | None = None,
    ) -> ProjectServiceRecord | None:
        assert project_id == "project-1"
        _ = stacktrace
        if service_name.strip().lower() in {"billing-api", "billing api"}:
            return self.project_service
        return None


class StubSecretsWriter:
    def put_secret(self, *, project_id: str, label: str, value: str) -> str:
        assert project_id == "project-1"
        assert label == "OPENAI_API_KEY"
        assert value == "super-secret-value"
        return "arn:aws:secretsmanager:us-east-1:123456789012:secret:stimpact/project-1/OPENAI_API_KEY"

    def delete_secret(self, *, external_ref: str) -> None:
        assert external_ref.startswith("arn:aws:secretsmanager:")


class StubProviderIntegrationService:
    def __init__(self) -> None:
        now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
        self.integration = ProviderIntegrationRecord(
            id="integration-1",
            provider=ProviderKind.GITHUB,
            name="Acme GitHub",
            status=ProviderIntegrationStatus.ACTIVE,
            credentials_secret_ref_id="secret-1",
            webhook_secret_ref_id=None,
            aws_region="us-west-2",
            metadata={
                "project_id": "project-1",
                "installation_id": "117170229",
            },
            created_at=now,
            updated_at=now,
        )
        self.secret_ref = SecretRefRecord(
            id="secret-1",
            project_id="project-1",
            label="gitlab-oauth-integration-1",
            description="GitLab OAuth credentials",
            backend=SecretBackend.AWS_SECRETS_MANAGER,
            external_ref="arn:aws:secretsmanager:us-west-2:123456789012:secret:stimpactai/projects/project-1/env/dev/gitlab-oauth-integration-1",
            created_at=now,
            updated_at=now,
        )
        self.repositories = [
            ProviderRepositoryRecord(
                id="provider-repo-1",
                provider_integration_id="integration-1",
                provider=ProviderKind.GITHUB,
                external_repository_id="123",
                owner="acme",
                name="billing-api",
                default_branch="main",
                clone_url="https://github.com/acme/billing-api.git",
                created_at=now,
                updated_at=now,
            )
        ]

    async def create_github_app_integration(
        self,
        *,
        project_id: str,
        name: str,
        installation_id: str | None = None,
    ) -> tuple[ProviderIntegrationRecord, ProviderInstallation]:
        assert project_id == "project-1"
        assert name == "Acme GitHub"
        assert installation_id == "117170229"
        return self.integration, ProviderInstallation(
            external_id="117170229",
            account_login="acme",
            account_type="Organization",
            account_name="Acme",
        )

    async def start_github_app_install(
        self,
        *,
        project_id: str,
        name: str,
        redirect_url: str,
    ) -> tuple[ProviderIntegrationRecord, str]:
        assert project_id == "project-1"
        assert name == "ScaleProject GitHub"
        assert redirect_url == "http://localhost:3000/onboarding?provider=github&step=3"
        integration = self.integration.model_copy(update={"status": ProviderIntegrationStatus.DISABLED})
        return (
            integration,
            "https://github.com/apps/stimpact/installations/new?state=github-install-state-1",
        )

    async def start_gitlab_oauth(
        self,
        *,
        project_id: str,
        name: str,
        gitlab_base_url: str | None = None,
    ) -> tuple[ProviderIntegrationRecord, str]:
        assert project_id == "project-1"
        assert name == "Acme GitLab"
        assert gitlab_base_url is None
        integration = self.integration.model_copy(
            update={
                "provider": ProviderKind.GITLAB,
                "name": "Acme GitLab",
                "status": ProviderIntegrationStatus.DISABLED,
            }
        )
        return integration, "https://gitlab.com/oauth/authorize?client_id=abc"

    async def complete_gitlab_oauth_callback(self, *, state: str, code: str) -> GitLabCallbackResult:
        assert state == "oauth-state-1"
        assert code == "gitlab-code"
        integration = self.integration.model_copy(update={"provider": ProviderKind.GITLAB})
        return GitLabCallbackResult(
            integration=integration,
            credentials_secret_ref=self.secret_ref,
            connected_account=ProviderInstallation(
                external_id="42",
                account_login="connor",
                account_type="user",
                account_name="Connor",
            ),
        )

    async def sync_repositories(
        self,
        provider_integration_id: str,
    ) -> tuple[ProviderIntegrationRecord, list[ProviderRepositoryRecord]]:
        assert provider_integration_id == "integration-1"
        return self.integration, self.repositories

    async def list_synced_repositories(self, provider_integration_id: str) -> list[ProviderRepositoryRecord]:
        assert provider_integration_id == "integration-1"
        return self.repositories

    async def build_authenticated_repository_clone_url(
        self,
        *,
        project_id: str,
        provider_repository_id: str,
    ) -> tuple[ProviderRepositoryRecord, str]:
        assert project_id == "project-1"
        assert provider_repository_id == "provider-repo-1"
        return self.repositories[0], "https://token@example.com/acme/billing-api.git"

    async def propose_patch_writeback(
        self,
        *,
        provider_repository_id: str,
        branch_name: str,
        patch_diff: str,
        title: str,
        description: str,
        commit_message: str,
    ) -> ProviderWritebackResult:
        assert provider_repository_id == "provider-repo-1"
        assert branch_name.startswith("stimpact/sdk-bootstrap-")
        assert patch_diff
        assert title.startswith("Add Stimpact telemetry bootstrap")
        assert commit_message.startswith("Add Stimpact telemetry bootstrap")
        return ProviderWritebackResult(
            branch_name=branch_name,
            commit_sha="commit-123",
            change_request_url="https://github.com/acme/billing-api/pull/42",
            reference_id="42",
            mergeable=True,
        )

    async def infer_repo_profile_defaults(
        self,
        *,
        project_id: str,
        provider_repository_id: str,
    ) -> RepoProfileInferenceResult:
        assert project_id == "project-1"
        assert provider_repository_id == "provider-repo-1"
        return RepoProfileInferenceResult(
            runtime_kind=RuntimeKind.NODE,
            base_image="public.ecr.aws/docker/library/node:20",
            install_command="npm ci",
            reproduce_command="npm test",
            verify_command="npm test",
            detected_from=["package.json scripts", "package.json and lockfile"],
            warnings=[
                "This repository looks like a monorepo. If frontend and backend deploy separately, map them as separate services.",
            ],
            monorepo=True,
        )

    async def preview_github_callback(
        self,
        *,
        installation_id: str | None,
        setup_action: str | None,
    ) -> GitHubCallbackPreview:
        assert installation_id == "117170229"
        assert setup_action == "install"
        return GitHubCallbackPreview(
            installation_id="117170229",
            setup_action="install",
            account_login="acme",
            account_type="Organization",
            account_name="Acme",
        )

    async def complete_github_app_callback(
        self,
        *,
        state: str,
        installation_id: str,
        setup_action: str | None,
    ) -> GitHubCallbackResult:
        assert state == "github-install-state-1"
        assert installation_id == "117170229"
        assert setup_action == "install"
        integration = self.integration.model_copy(
            update={
                "metadata": {
                    **self.integration.metadata,
                    "project_id": "project-1",
                }
            }
        )
        return GitHubCallbackResult(
            integration=integration,
            connected_account=ProviderInstallation(
                external_id="117170229",
                account_login="acme",
                account_type="Organization",
                account_name="Acme",
            ),
            installation_id="117170229",
            setup_action="install",
            redirect_url="http://localhost:3000/onboarding?provider=github&step=3",
            synced_repository_count=4,
        )

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
        assert redirect_url == "http://localhost:3000/onboarding?provider=github&step=3"
        assert provider is ProviderKind.GITHUB
        assert project_id == "project-1"
        assert integration_id == "integration-1"
        assert installation_id == "117170229"
        assert setup_action == "install"
        assert synced_repository_count == 4
        return (
            "http://localhost:3000/onboarding"
            "?provider=github&provider_status=connected&project_id=project-1"
            "&integration_id=integration-1&installation_id=117170229"
            "&setup_action=install&synced_repositories=4&step=3"
        )

    def verify_github_webhook(self, *, body: bytes, signature_header: str | None) -> None:
        assert body == b'{"zen":"keep it logically awesome"}'
        assert signature_header == "sha256=test-signature"


class StubRootCauseAnalysisService:
    async def analyze_incident(
        self,
        incident_id: str,
        *,
        event_limit: int = 50,
    ) -> RootCauseAnalysis:
        assert incident_id == "incident-1"
        assert event_limit == 20
        return RootCauseAnalysis(
            incident_id=incident_id,
            category=FailureCategory.DATABASE_FAILURE,
            category_summary="The billing-api incident is most likely a database failure based on database, postgres.",
            category_confidence=0.91,
            evidence=RootCauseEvidence(
                suspected_component="agent-platform/api/repositories/incident_repository.py",
                evidence_summary="Stack signals and code search both point toward the incident repository path.",
                stack_trace_signals=["incident_repository.py", "fetchrow"],
                search_terms=["database", "postgres", "fetchrow"],
                code_candidates=[],
                git_signals=[],
                evidence_confidence=0.72,
                latest_commit_sha="abc123",
                inspected_event_count=1,
            ),
            reasoning=RootCauseReasoning(
                root_cause_hypothesis="A database query path is timing out inside the incident repository layer.",
                reasoning_summary="The grounded evidence points to the repository layer handling database reads.",
                alternative_hypotheses=["An upstream connection-pool issue is also possible."],
                confidence=0.78,
            ),
        )


class StubPatchGenerationService:
    async def get_or_generate_patch(
        self,
        incident_id: str,
        *,
        refresh: bool = False,
        event_limit: int = 50,
    ) -> PatchRunRecord:
        assert incident_id == "incident-1"
        assert refresh is False
        assert event_limit == 20
        now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
        return PatchRunRecord(
            id="patch-1",
            incident_id=incident_id,
            status=PatchRunStatus.GENERATED,
            patch_summary="Add a guard around the timeout-prone billing repository path.",
            rationale="The RCA evidence points to a narrow timeout path in the billing repository layer.",
            target_files=[
                PatchTargetFile(
                    path="agent-platform/api/repositories/incident_repository.py",
                    reason="Primary candidate file from RCA evidence.",
                )
            ],
            unified_diff="diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new",
            verification_steps=["Replay the failing request.", "Run targeted repository tests."],
            confidence=0.74,
            model_name="patch-model",
            based_on_commit_sha="abc123",
            diff_line_count=2,
            file_count=1,
            created_at=now,
            updated_at=now,
        )


class StubSandboxVerificationService:
    async def get_latest_run(self, incident_id: str) -> SandboxRunRecord | None:
        assert incident_id == "incident-1"
        now = datetime(2026, 3, 16, 12, 5, tzinfo=UTC)
        return SandboxRunRecord(
            id="sandbox-1",
            incident_id=incident_id,
            patch_run_id="patch-1",
            repo_profile_id="profile-1",
            async_job_id="job-1",
            status=SandboxRunStatus.SUCCEEDED,
            executor_backend="kubernetes",
            external_job_id="stimpact-sandbox-abcd1234",
            install_command="npm install",
            reproduce_command="python reproduce.py",
            verify_command="pytest",
            reproduction_succeeded=True,
            patch_applied=True,
            verification_succeeded=True,
            summary="Sandbox reproduced the incident, applied the patch, and verified the candidate fix.",
            execution_log="[reproduce]\nexit_code: 0",
            created_at=now,
            updated_at=now,
        )

    async def list_runs(self, incident_id: str, *, limit: int = 20) -> list[SandboxRunRecord]:
        assert incident_id == "incident-1"
        assert limit == 20
        run = await self.get_latest_run(incident_id)
        return [run] if run is not None else []

    async def get_run(self, incident_id: str, sandbox_run_id: str) -> SandboxRunRecord:
        assert sandbox_run_id == "sandbox-1"
        run = await self.get_latest_run(incident_id)
        assert run is not None
        return run

    async def queue_sandbox_run(
        self,
        incident_id: str,
        *,
        event_limit: int = 50,
        refresh_patch: bool = False,
    ) -> tuple[SandboxRunRecord, object]:
        assert incident_id == "incident-1"
        assert event_limit == 20
        assert refresh_patch is False
        run = await self.get_latest_run(incident_id)
        assert run is not None
        job = type(
            "StubJob",
            (),
            {"id": "job-1", "status": AsyncJobStatus.QUEUED},
        )()
        return run, job


class StubSandboxRepository:
    async def list_sandbox_run_steps(self, sandbox_run_id: str) -> list[SandboxRunStepRecord]:
        assert sandbox_run_id == "sandbox-1"
        now = datetime(2026, 3, 16, 12, 5, tzinfo=UTC)
        return [
            SandboxRunStepRecord(
                id="step-1",
                sandbox_run_id=sandbox_run_id,
                step_name="submit-kubernetes-job",
                status=SandboxRunStatus.RUNNING,
                command="kubernetes job submission",
                summary="Submitted Kubernetes job.",
                artifact_id="artifact-1",
                exit_code=0,
                started_at=now,
                finished_at=now,
                created_at=now,
            )
        ]

    async def list_sandbox_run_attempts(self, sandbox_run_id: str) -> list[SandboxRunAttemptRecord]:
        assert sandbox_run_id == "sandbox-1"
        now = datetime(2026, 3, 16, 12, 5, tzinfo=UTC)
        return [
            SandboxRunAttemptRecord(
                id="attempt-1",
                sandbox_run_id=sandbox_run_id,
                async_job_id="job-1",
                attempt_number=1,
                status=SandboxRunStatus.RUNNING,
                error_message=None,
                started_at=now,
                finished_at=None,
            )
        ]


class StubArtifactRepository:
    async def list_sandbox_run_artifacts(self, sandbox_run_id: str):
        assert sandbox_run_id == "sandbox-1"
        now = datetime(2026, 3, 16, 12, 5, tzinfo=UTC)
        from models.artifact import ArtifactRecord, ArtifactStorageBackend, ArtifactType

        return [
            ArtifactRecord(
                id="artifact-1",
                incident_id="incident-1",
                patch_run_id="patch-1",
                sandbox_run_id=sandbox_run_id,
                artifact_type=ArtifactType.SANDBOX_MANIFEST,
                storage_backend=ArtifactStorageBackend.S3,
                bucket_name="artifact-bucket",
                object_key="sandbox-runs/sandbox-1/job-manifest.json",
                uri="s3://artifact-bucket/sandbox-runs/sandbox-1/job-manifest.json",
                content_type="application/json",
                size_bytes=128,
                checksum_sha256=None,
                created_at=now,
                updated_at=now,
            )
        ]


class StubAutonomousRunService:
    async def start_run(
        self,
        incident_id: str,
        request: AutonomousRunCreateRequest,
    ) -> AutonomousRunDetailResponse:
        assert incident_id == "incident-1"
        assert request.feature_seeds
        return self.get_run_detail_sync(incident_id, "auto-run-1")

    async def list_runs(self, incident_id: str) -> list[AutonomousRepairRunRecord]:
        assert incident_id == "incident-1"
        return [self._detail().run]

    async def get_latest_run_detail(self, incident_id: str) -> AutonomousRunDetailResponse:
        assert incident_id == "incident-1"
        return self._detail()

    async def get_run_detail(self, incident_id: str, run_id: str) -> AutonomousRunDetailResponse:
        assert incident_id == "incident-1"
        assert run_id == "auto-run-1"
        return self._detail()

    async def approve_run(self, incident_id: str, run_id: str, request) -> AutonomousRunDetailResponse:
        assert incident_id == "incident-1"
        assert run_id == "auto-run-1"
        detail = self._detail()
        return detail.model_copy(
            update={
                "run": detail.run.model_copy(update={"approval_status": request.approval_status}),
            }
        )

    async def promote_run(self, incident_id: str, run_id: str) -> AutonomousRunDetailResponse:
        assert incident_id == "incident-1"
        assert run_id == "auto-run-1"
        detail = self._detail()
        return detail.model_copy(
            update={
                "run": detail.run.model_copy(
                    update={
                        "promotion_status": AutonomousPromotionStatus.PROPOSED,
                        "promotion_branch_name": "stimpact/fix/incident-1",
                        "promotion_url": "https://github.com/acme/billing-api/compare/main...stimpact/fix/incident-1?expand=1",
                    }
                ),
            }
        )

    def get_run_detail_sync(self, incident_id: str, run_id: str) -> AutonomousRunDetailResponse:
        assert incident_id == "incident-1"
        assert run_id == "auto-run-1"
        return self._detail()

    def subscribe(self, run_id: str, subscriber) -> None:
        assert run_id == "auto-run-1"

    def unsubscribe(self, run_id: str, subscriber) -> None:
        assert run_id == "auto-run-1"

    def is_terminal(self, run: AutonomousRepairRunRecord) -> bool:
        return True

    def _detail(self) -> AutonomousRunDetailResponse:
        now = datetime(2026, 3, 16, 12, 10, tzinfo=UTC)
        run = AutonomousRepairRunRecord(
            id="auto-run-1",
            incident_id="incident-1",
            repository_root="/tmp/demo",
            objective="Repair the billing timeout incident.",
            status=AutonomousRunStatus.SUCCEEDED,
            phase=AutonomousRunPhase.COMPLETED,
            initializer_session_id="init-1",
            coding_session_id="code-1",
            last_error=None,
            loop_state={
                "step_index": 4,
                "max_steps": 8,
                "checkpoint_ref": "stimpact-checkpoint/autonomous-baseline",
                "recovery_attempts": 1,
                "consecutive_failures": 0,
                "last_tool_name": "browser_assert_text",
                "recent_tool_names": ["checkpoint", "edit_file", "browser_open", "browser_assert_text"],
                "last_tool_ok": True,
                "last_tool_result": {"ok": True},
            },
            created_at=now,
            updated_at=now,
        )
        events = [
            AutonomousRunEvent(
                id="event-1",
                run_id=run.id,
                event_type=AutonomousEventType.RUN_COMPLETED,
                phase=AutonomousRunPhase.COMPLETED,
                summary="Autonomous repair run completed successfully.",
                payload={"status": "succeeded"},
                created_at=now,
            )
        ]
        outcome = AutonomousRunOutcome(
            run_id=run.id,
            incident_id="incident-1",
            status=AutonomousRunStatus.SUCCEEDED,
            phase=AutonomousRunPhase.COMPLETED,
            objective=run.objective,
            repository_root=run.repository_root,
            checkpoint_ref="stimpact-checkpoint/autonomous-baseline",
            recovery_attempts=1,
            total_steps=4,
            total_decisions=4,
            total_tool_calls=4,
            total_events=6,
            last_error=None,
            created_at=now,
            completed_at=now,
        )
        return AutonomousRunDetailResponse(
            run=run,
            events=events,
            outcome=outcome,
            artifact_paths=AutonomousArtifactPaths(
                snapshot_path="/tmp/demo/.stimpactai/autonomous-runs/incident-1/auto-run-1/snapshot.json",
                events_path="/tmp/demo/.stimpactai/autonomous-runs/incident-1/auto-run-1/events.jsonl",
                outcome_path="/tmp/demo/.stimpactai/autonomous-runs/incident-1/auto-run-1/outcome.json",
            ),
        )


def test_ingest_error_returns_accepted_response_and_signals_outbox(caplog) -> None:
    caplog.set_level("INFO")
    app = build_test_app()
    telemetry_repository = RecordingTelemetryRepository()
    outbox_signaler = RecordingOutboxSignaler()

    app.dependency_overrides[get_telemetry_repository] = lambda: telemetry_repository
    app.dependency_overrides[get_incident_event_publisher] = IncidentEventPublisher
    app.dependency_overrides[get_outbox_signaler] = lambda: outbox_signaler

    client = TestClient(app)
    response = client.post(
        "/telemetry/error",
        json={
            "project_id": "project-1",
            "environment": "production",
            "service": "billing-api",
            "error_message": "  Database timeout  ",
            "stacktrace": "Traceback:\nline 1\n",
            "request": {"method": "POST"},
            "response": {"status_code": 503},
            "commit_sha": "ABC123",
            "timestamp": "2026-03-16T12:00:00Z",
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert len(body["telemetry_id"]) > 10
    assert len(body["fingerprint"]) == 64
    assert len(telemetry_repository.calls) == 1
    assert outbox_signaler.calls == [("outbox-1", IncidentEventType.TELEMETRY_RECEIVED.value)]
    assert any("telemetry_error_accepted" in message for message in caplog.messages)


@pytest.mark.asyncio
async def test_process_telemetry_outbox_inline_triggers_for_existing_incident_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    telemetry_module = importlib.import_module("api.routes.telemetry")
    trigger_module = importlib.import_module("services.autonomous_trigger")
    incident_repo_module = importlib.import_module("api.repositories.incident_repository")
    control_repo_module = importlib.import_module("api.repositories.control_plane_repository")
    async_job_module = importlib.import_module("api.repositories.async_job_repository")
    autonomous_repo_module = importlib.import_module("api.repositories.autonomous_repository")
    patch_repo_module = importlib.import_module("api.repositories.patch_repository")
    telemetry_repo_module = importlib.import_module("api.repositories.telemetry_repository")
    outbox_repo_module = importlib.import_module("api.repositories.outbox_repository")
    provider_module = importlib.import_module("services.provider_integration_service")
    asm_module = importlib.import_module("services.aws_secrets_manager")
    autonomous_runs_module = importlib.import_module("services.autonomous_runs")
    incident_creation_module = importlib.import_module("services.incident_creation")

    trigger_calls: list[dict[str, object]] = []
    marked_processed: list[str] = []

    class StubIncidentRepository:
        def __init__(self, pool) -> None:
            self.pool = pool

    class StubControlPlaneRepository:
        def __init__(self, pool) -> None:
            self.pool = pool

    class StubTelemetryRepository:
        def __init__(self, pool) -> None:
            self.pool = pool

    class StubAsyncJobRepository:
        def __init__(self, pool) -> None:
            self.pool = pool

    class StubAutonomousRepository:
        def __init__(self, pool) -> None:
            self.pool = pool

    class StubPatchRepository:
        def __init__(self, pool) -> None:
            self.pool = pool

    class StubOutboxRepository:
        def __init__(self, pool) -> None:
            self.pool = pool

        async def mark_processed(self, event_id: str) -> None:
            marked_processed.append(event_id)

    class StubProviderIntegrationService:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

    class StubSecretsWriter:
        pass

    class StubSecretsReader:
        pass

    class StubAutonomousRunServiceInline:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

    class StubIncidentCreationService:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        async def process_telemetry_received(self, payload):
            assert payload == {"telemetry_id": "telemetry-1"}
            return IncidentProcessingResult(
                incident_id="incident-1",
                created_new_incident=False,
                attached_telemetry=True,
                severity=IncidentSeverity.HIGH,
                event_count=2,
            )

    async def _fake_trigger(**kwargs):
        trigger_calls.append(kwargs)

    monkeypatch.setattr(telemetry_module, "get_telemetry_classifier_enabled", lambda: False, raising=False)
    monkeypatch.setattr(incident_repo_module, "IncidentRepository", StubIncidentRepository)
    monkeypatch.setattr(control_repo_module, "ControlPlaneRepository", StubControlPlaneRepository)
    monkeypatch.setattr(telemetry_repo_module, "PostgresTelemetryRepository", StubTelemetryRepository)
    monkeypatch.setattr(async_job_module, "AsyncJobRepository", StubAsyncJobRepository)
    monkeypatch.setattr(autonomous_repo_module, "AutonomousRunRepository", StubAutonomousRepository)
    monkeypatch.setattr(patch_repo_module, "PatchRepository", StubPatchRepository)
    monkeypatch.setattr(outbox_repo_module, "OutboxRepository", StubOutboxRepository)
    monkeypatch.setattr(provider_module, "ProviderIntegrationService", StubProviderIntegrationService)
    monkeypatch.setattr(asm_module, "AwsSecretsManagerWriter", StubSecretsWriter)
    monkeypatch.setattr(asm_module, "AwsSecretsManagerReader", StubSecretsReader)
    monkeypatch.setattr(autonomous_runs_module, "AutonomousRunService", StubAutonomousRunServiceInline)
    monkeypatch.setattr(incident_creation_module, "IncidentCreationService", StubIncidentCreationService)
    monkeypatch.setattr(trigger_module, "trigger_autonomous_run_for_new_incident", _fake_trigger)

    await telemetry_module._process_telemetry_outbox_inline(
        pool=object(),
        outbox_event_id="outbox-1",
        incident_payload={"telemetry_id": "telemetry-1"},
    )

    assert marked_processed == ["outbox-1"]
    assert trigger_calls == [
        {
            "incident_id": "incident-1",
            "autonomous_run_service": trigger_calls[0]["autonomous_run_service"],
            "processing_result": IncidentProcessingResult(
                incident_id="incident-1",
                created_new_incident=False,
                attached_telemetry=True,
                severity=IncidentSeverity.HIGH,
                event_count=2,
            ),
        }
    ]


def test_ingest_heartbeat_updates_project_telemetry_verification(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ADMIN_TOKEN", "super-admin-token")
    app = build_test_app()
    repository = StubControlPlaneRepository()
    api_key = ProjectApiKeyRecord(
        id="api-key-1",
        project_id="project-1",
        name="Telemetry key",
        key_prefix="stimp_live_1234",
        key_hash=hash_api_key("stimp_live_123"),
        status=ProjectApiKeyStatus.ACTIVE,
        last_used_at=None,
        revoked_at=None,
        created_at=datetime(2026, 3, 16, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 3, 16, 12, 0, tzinfo=UTC),
    )
    repository.project_api_keys.append(api_key)
    app.dependency_overrides[get_telemetry_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_security_control_plane_repository] = lambda: repository

    client = TestClient(app)
    heartbeat_response = client.post(
        "/telemetry/heartbeat",
        headers={"X-Stimpact-Project-Key": "stimp_live_123"},
        json={
            "project_id": "project-1",
            "environment": "production",
            "service": "billing-api",
            "commit_sha": "abc123",
            "timestamp": datetime.now(tz=UTC).isoformat(),
        },
    )

    assert heartbeat_response.status_code == 202
    verification_response = client.get(
        "/control-plane/projects/project-1/telemetry-verification",
        params={"service": "billing-api", "environment": "production"},
        headers={"Authorization": "Bearer super-admin-token"},
    )

    assert verification_response.status_code == 200
    body = verification_response.json()
    assert body["status"] == "healthy"
    assert body["commit_sha"] == "abc123"
    assert body["heartbeat"]["service"] == "billing-api"


def test_project_harness_readiness_reports_launch_contract(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ADMIN_TOKEN", "super-admin-token")
    app = build_test_app()
    repository = StubControlPlaneRepository()
    repository.project_onboarding_state = repository.project_onboarding_state.model_copy(
        update={"policy_reviewed": True, "sdk_setup_status": ProjectSdkSetupStatus.MANUAL}
    )
    repository.project_api_keys.append(
        ProjectApiKeyRecord(
            id="api-key-1",
            project_id="project-1",
            name="Telemetry key",
            key_prefix="stimp_live_1234",
            key_hash=hash_api_key("stimp_live_123"),
            status=ProjectApiKeyStatus.ACTIVE,
            last_used_at=None,
            revoked_at=None,
            created_at=datetime(2026, 3, 16, 12, 0, tzinfo=UTC),
            updated_at=datetime(2026, 3, 16, 12, 0, tzinfo=UTC),
        )
    )
    repository.project_telemetry_heartbeats.append(
        ProjectTelemetryHeartbeatRecord(
            project_id="project-1",
            service="billing-api",
            environment=Environment.PRODUCTION,
            last_seen_at=datetime.now(tz=UTC),
            commit_sha="abc123",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
    )
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_security_control_plane_repository] = lambda: repository

    client = TestClient(app)
    response = client.get(
        "/control-plane/projects/project-1/harness-readiness",
        params={"service": "billing-api", "environment": "production"},
        headers={"Authorization": "Bearer super-admin-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["telemetry_status"] == "healthy"
    assert body["launch_contract"]["repo_profile_id"] == "profile-1"
    assert body["launch_contract"]["provider_repository_name"] == "billing-api"
    assert body["launch_contract"]["dependency_service_slugs"] == ["redis-cache"]
    assert body["launch_contract"]["reproduce_command"] == "python reproduce.py"
    assert body["blocked_checks"] == []
    ready_ids = {item["id"] for item in body["ready_checks"]}
    assert "telemetry-credentials" in ready_ids
    assert "sandbox-contract" in ready_ids


def test_browser_telemetry_token_can_be_issued_and_used() -> None:
    app = build_test_app()
    repository = StubControlPlaneRepository()
    repository.project_browser_keys.append(
        ProjectBrowserKeyRecord(
            id="browser-key-1",
            project_id="project-1",
            name="Browser telemetry",
            key_prefix="stimp_browser_demo",
            key_hash=hash_api_key("stimp_browser_secret"),
            allowed_origins=["https://app.example.com"],
            status=ProjectBrowserKeyStatus.ACTIVE,
            last_used_at=None,
            last_issued_at=None,
            revoked_at=None,
            created_at=repository.secret_ref.created_at,
            updated_at=repository.secret_ref.updated_at,
        )
    )
    telemetry_repository = RecordingTelemetryRepository()
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_telemetry_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_security_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_telemetry_repository] = lambda: telemetry_repository
    app.dependency_overrides[get_incident_event_publisher] = IncidentEventPublisher
    app.dependency_overrides[get_outbox_signaler] = RecordingOutboxSignaler

    client = TestClient(app)
    token_response = client.post(
        "/telemetry/browser-token",
        headers={"Origin": "https://app.example.com"},
        json={
            "project_id": "project-1",
            "browser_key": "stimp_browser_secret",
            "service": "billing-web",
            "environment": "production",
        },
    )

    assert token_response.status_code == 200
    token = token_response.json()["token"]

    ingest_response = client.post(
        "/telemetry/error",
        headers={
            "Authorization": f"Bearer {token}",
            "Origin": "https://app.example.com",
        },
        json={
            "project_id": "project-1",
            "environment": "production",
            "service": "billing-web",
            "error_message": "Browser crash",
            "stacktrace": "Error: boom",
            "timestamp": "2026-03-16T12:00:00Z",
        },
    )

    assert ingest_response.status_code == 202
    assert len(telemetry_repository.calls) == 1
    assert repository.project_browser_keys[0].last_issued_at is not None


def test_browser_telemetry_token_rejects_wrong_origin() -> None:
    app = build_test_app()
    repository = StubControlPlaneRepository()
    repository.project_browser_keys.append(
        ProjectBrowserKeyRecord(
            id="browser-key-1",
            project_id="project-1",
            name="Browser telemetry",
            key_prefix="stimp_browser_demo",
            key_hash=hash_api_key("stimp_browser_secret"),
            allowed_origins=["https://app.example.com"],
            status=ProjectBrowserKeyStatus.ACTIVE,
            last_used_at=None,
            last_issued_at=None,
            revoked_at=None,
            created_at=repository.secret_ref.created_at,
            updated_at=repository.secret_ref.updated_at,
        )
    )
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_telemetry_control_plane_repository] = lambda: repository

    client = TestClient(app)
    response = client.post(
        "/telemetry/browser-token",
        headers={"Origin": "https://evil.example.com"},
        json={
            "project_id": "project-1",
            "browser_key": "stimp_browser_secret",
            "service": "billing-web",
            "environment": "production",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "browser_origin_not_allowed"


def test_browser_telemetry_token_rejects_unconfigured_browser_key() -> None:
    app = build_test_app()
    repository = StubControlPlaneRepository()
    repository.project_browser_keys.append(
        ProjectBrowserKeyRecord(
            id="browser-key-1",
            project_id="project-1",
            name="Browser telemetry",
            key_prefix="stimp_browser_demo",
            key_hash=hash_api_key("stimp_browser_secret"),
            allowed_origins=[],
            status=ProjectBrowserKeyStatus.ACTIVE,
            last_used_at=None,
            last_issued_at=None,
            revoked_at=None,
            created_at=repository.secret_ref.created_at,
            updated_at=repository.secret_ref.updated_at,
        )
    )
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_telemetry_control_plane_repository] = lambda: repository

    client = TestClient(app)
    response = client.post(
        "/telemetry/browser-token",
        headers={"Origin": "https://app.example.com"},
        json={
            "project_id": "project-1",
            "browser_key": "stimp_browser_secret",
            "service": "billing-web",
            "environment": "production",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "browser_origin_not_configured"


def test_browser_telemetry_ingest_rechecks_live_browser_key_origin() -> None:
    app = build_test_app()
    repository = StubControlPlaneRepository()
    repository.project_browser_keys.append(
        ProjectBrowserKeyRecord(
            id="browser-key-1",
            project_id="project-1",
            name="Browser telemetry",
            key_prefix="stimp_browser_demo",
            key_hash=hash_api_key("stimp_browser_secret"),
            allowed_origins=["https://app.example.com"],
            status=ProjectBrowserKeyStatus.ACTIVE,
            last_used_at=None,
            last_issued_at=None,
            revoked_at=None,
            created_at=repository.secret_ref.created_at,
            updated_at=repository.secret_ref.updated_at,
        )
    )
    telemetry_repository = RecordingTelemetryRepository()
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_telemetry_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_security_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_telemetry_repository] = lambda: telemetry_repository
    app.dependency_overrides[get_incident_event_publisher] = IncidentEventPublisher
    app.dependency_overrides[get_outbox_signaler] = RecordingOutboxSignaler

    client = TestClient(app)
    token_response = client.post(
        "/telemetry/browser-token",
        headers={"Origin": "https://app.example.com"},
        json={
            "project_id": "project-1",
            "browser_key": "stimp_browser_secret",
            "service": "billing-web",
            "environment": "production",
        },
    )

    assert token_response.status_code == 200
    token = token_response.json()["token"]
    repository.project_browser_keys[0] = repository.project_browser_keys[0].model_copy(
        update={"allowed_origins": ["https://admin.example.com"]}
    )

    ingest_response = client.post(
        "/telemetry/error",
        headers={
            "Authorization": f"Bearer {token}",
            "Origin": "https://app.example.com",
        },
        json={
            "project_id": "project-1",
            "environment": "production",
            "service": "billing-web",
            "error_message": "Browser crash",
            "stacktrace": "Error: boom",
            "timestamp": "2026-03-16T12:00:00Z",
        },
    )

    assert ingest_response.status_code == 401
    assert ingest_response.json()["error"]["code"] == "browser_ingest_token_origin_mismatch"
    assert len(telemetry_repository.calls) == 0


def test_browser_telemetry_token_preflight_returns_cors_headers(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ALLOW_LEGACY_BROWSER_TOKEN_EXCHANGE", "true")
    monkeypatch.setenv("CLIENT_UI_BASE_URL", "https://app.example.com")

    app = build_test_app()
    client = TestClient(app)
    response = client.options(
        "/telemetry/browser-token",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == "https://app.example.com"
    assert response.headers["Access-Control-Allow-Methods"] == "OPTIONS, POST"
    assert response.headers["Access-Control-Allow-Headers"] == "authorization, content-type, x-stimpact-project-key"
    assert response.headers["Access-Control-Max-Age"] == "600"
    assert response.headers["Vary"] == "Origin"


def test_browser_telemetry_token_preflight_uses_active_browser_key_origins(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ALLOW_LEGACY_BROWSER_TOKEN_EXCHANGE", "true")

    app = build_test_app()
    repository = StubControlPlaneRepository()
    repository.project_browser_keys.append(
        ProjectBrowserKeyRecord(
            id="browser-key-1",
            project_id="project-1",
            name="Browser telemetry",
            key_prefix="stimp_browser_demo",
            key_hash=hash_api_key("stimp_browser_secret"),
            allowed_origins=["https://syntheticsoulsongs.com"],
            status=ProjectBrowserKeyStatus.ACTIVE,
            last_used_at=None,
            last_issued_at=None,
            revoked_at=None,
            created_at=repository.secret_ref.created_at,
            updated_at=repository.secret_ref.updated_at,
        )
    )
    app.state.telemetry_origin_registry = TelemetryOriginRegistry(
        pool_getter=lambda: None,
        fallback_origins=[],
        lookup_override=repository.list_active_project_browser_key_origins,
    )

    client = TestClient(app)
    response = client.options(
        "/telemetry/browser-token",
        headers={
            "Origin": "https://syntheticsoulsongs.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == "https://syntheticsoulsongs.com"


def test_browser_telemetry_token_cannot_access_project_routes() -> None:
    app = build_test_app()
    repository = StubControlPlaneRepository()
    repository.project_api_keys.append(
        ProjectApiKeyRecord(
            id="api-key-1",
            project_id="project-1",
            name="SDK key",
            key_prefix="stimp_live_demo",
            key_hash=hash_api_key("secret-project-key"),
            status=ProjectApiKeyStatus.ACTIVE,
            last_used_at=None,
            revoked_at=None,
            created_at=repository.secret_ref.created_at,
            updated_at=repository.secret_ref.updated_at,
        )
    )
    token = build_browser_ingest_token(
        project_id="project-1",
        service="billing-web",
        environment="production",
        origin="https://app.example.com",
        browser_key_id="browser-key-1",
    ).token
    app.dependency_overrides[get_incident_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_security_control_plane_repository] = lambda: repository

    client = TestClient(app)
    response = client.get(
        "/incidents",
        params={"project_id": "project-1"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "project_api_key_missing"


def test_telemetry_verification_returns_unseen_when_no_heartbeat_exists(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ADMIN_TOKEN", "super-admin-token")
    app = build_test_app()
    repository = StubControlPlaneRepository()
    app.dependency_overrides[get_control_plane_repository] = lambda: repository

    client = TestClient(app)
    response = client.get(
        "/control-plane/projects/project-1/telemetry-verification",
        params={"service": "billing-api", "environment": "production"},
        headers={"Authorization": "Bearer super-admin-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unseen"
    assert body["heartbeat"] is None


def test_list_incidents_passes_filters_and_serializes_response() -> None:
    app = build_test_app()
    repository = StubIncidentRepository()
    app.dependency_overrides[get_incident_repository] = lambda: repository

    client = TestClient(app)
    response = client.get(
        "/incidents",
        params={"project_id": "project-1", "status": "open", "limit": 25, "offset": 5},
    )

    assert response.status_code == 200
    assert repository.last_list_kwargs == {
        "project_id": "project-1",
        "status": "open",
        "limit": 25,
        "offset": 5,
    }
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == "incident-1"
    assert body["items"][0]["severity"] == "critical"


def test_incident_reporting_overview_returns_real_aggregates() -> None:
    app = build_test_app()
    repository = StubIncidentRepository()
    app.dependency_overrides[get_incident_repository] = lambda: repository

    client = TestClient(app)
    response = client.get("/incidents/reporting/overview", params={"project_id": "project-1"})

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "project-1"
    assert body["total_visible_incidents"] == 1
    assert body["open_incidents"] == 1
    assert body["critical_incidents"] == 1
    assert body["total_event_volume"] == 2
    assert body["service_counts"][0]["label"] == "billing-api"
    assert body["uptime_percent_last_30d"] == 90.0
    assert body["uptime_delta_pp"] == 5.0
    assert body["avg_agent_response_seconds_last_30d"] == 300.0
    assert body["avg_agent_response_delta_seconds"] == -100.0
    assert body["agent_resolution_percent_last_30d"] == 50.0
    assert body["agent_resolution_delta_pp"] == 10.0


def test_get_incident_returns_detail_payload() -> None:
    app = build_test_app()
    repository = StubIncidentRepository()
    app.dependency_overrides[get_incident_repository] = lambda: repository

    client = TestClient(app)
    response = client.get("/incidents/incident-1", params={"event_limit": 20})

    assert response.status_code == 200
    body = response.json()
    assert body["incident"]["id"] == "incident-1"
    assert body["events"][0]["telemetry_id"] == "telemetry-2"


def test_acknowledge_incident_updates_status() -> None:
    app = build_test_app()
    repository = StubIncidentRepository()
    app.dependency_overrides[get_incident_repository] = lambda: repository

    client = TestClient(app)
    response = client.patch("/incidents/incident-1/acknowledge")

    assert response.status_code == 200
    assert repository.status_updates == [IncidentStatus.ACKNOWLEDGED]
    assert response.json()["status"] == "acknowledged"


def test_reopen_incident_updates_status() -> None:
    app = build_test_app()
    repository = StubIncidentRepository()
    repository.incident = repository.incident.model_copy(update={"status": IncidentStatus.ACKNOWLEDGED})
    app.dependency_overrides[get_incident_repository] = lambda: repository

    client = TestClient(app)
    response = client.patch("/incidents/incident-1/reopen")

    assert response.status_code == 200
    assert repository.status_updates == [IncidentStatus.OPEN]
    assert response.json()["status"] == "open"


def test_get_missing_incident_returns_not_found() -> None:
    app = build_test_app()
    repository = StubIncidentRepository()
    app.dependency_overrides[get_incident_repository] = lambda: repository

    client = TestClient(app)
    response = client.get("/incidents/missing-incident")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "incident_not_found"


def test_incident_list_requires_project_key_when_project_has_active_key() -> None:
    app = build_test_app()
    incident_repository = StubIncidentRepository()
    security_repository = StubControlPlaneRepository()
    security_repository.project_api_keys.append(
        ProjectApiKeyRecord(
            id="api-key-1",
            project_id="project-1",
            name="Incident read key",
            key_prefix="stimp_live_demo",
            key_hash=hash_api_key("incident-project-key"),
            status=ProjectApiKeyStatus.ACTIVE,
            last_used_at=None,
            revoked_at=None,
            created_at=security_repository.secret_ref.created_at,
            updated_at=security_repository.secret_ref.updated_at,
        )
    )
    app.dependency_overrides[get_incident_repository] = lambda: incident_repository
    app.dependency_overrides[get_incident_control_plane_repository] = lambda: security_repository

    client = TestClient(app)
    unauthorized = client.get("/incidents", params={"project_id": "project-1"})
    authorized = client.get(
        "/incidents",
        params={"project_id": "project-1"},
        headers={"X-Stimpact-Project-Key": "incident-project-key"},
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200


def test_incident_list_requires_project_id_when_scoped_credentials_are_used(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_REQUIRE_PROJECT_API_KEYS", "1")
    app = build_test_app()
    app.dependency_overrides[get_incident_control_plane_repository] = StubControlPlaneRepository

    client = TestClient(app)
    response = client.get("/incidents")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "project_id_required"


def test_incident_detail_requires_matching_project_key_when_auth_is_enforced(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_REQUIRE_PROJECT_API_KEYS", "1")
    app = build_test_app()
    incident_repository = StubIncidentRepository()
    incident_repository.incident = incident_repository.incident.model_copy(update={"project_id": "project-2"})
    security_repository = StubControlPlaneRepository()
    security_repository.project_api_keys.append(
        ProjectApiKeyRecord(
            id="api-key-1",
            project_id="project-1",
            name="Project one key",
            key_prefix="stimp_live_demo",
            key_hash=hash_api_key("project-one-key"),
            status=ProjectApiKeyStatus.ACTIVE,
            last_used_at=None,
            revoked_at=None,
            created_at=security_repository.secret_ref.created_at,
            updated_at=security_repository.secret_ref.updated_at,
        )
    )
    app.dependency_overrides[get_incident_repository] = lambda: incident_repository
    app.dependency_overrides[get_incident_control_plane_repository] = lambda: security_repository

    client = TestClient(app)
    response = client.get(
        "/incidents/incident-1",
        headers={"X-Stimpact-Project-Key": "project-one-key"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] in {"project_api_key_invalid", "project_api_key_required"}


def test_global_incident_chat_requires_matching_project_key() -> None:
    app = build_test_app()
    security_repository = StubControlPlaneRepository()
    security_repository.project_api_keys.append(
        ProjectApiKeyRecord(
            id="api-key-1",
            project_id="project-1",
            name="Chat key",
            key_prefix="stimp_live_demo",
            key_hash=hash_api_key("chat-project-key"),
            status=ProjectApiKeyStatus.ACTIVE,
            last_used_at=None,
            revoked_at=None,
            created_at=security_repository.secret_ref.created_at,
            updated_at=security_repository.secret_ref.updated_at,
        )
    )
    app.dependency_overrides[get_incident_chat_service] = StubIncidentChatService
    app.dependency_overrides[get_incident_chat_control_plane_repository] = lambda: security_repository

    client = TestClient(app)
    unauthorized = client.post(
        "/incidents/chat",
        json={"messages": [{"role": "user", "content": "Summarize incidents"}], "project_id": "project-1"},
    )
    authorized = client.post(
        "/incidents/chat",
        json={"messages": [{"role": "user", "content": "Summarize incidents"}], "project_id": "project-1"},
        headers={"X-Stimpact-Project-Key": "chat-project-key"},
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["referenced_incident_ids"] == ["incident-1"]


def test_incident_detail_chat_uses_incident_project_scope() -> None:
    app = build_test_app()
    incident_repository = StubIncidentRepository()
    security_repository = StubControlPlaneRepository()
    security_repository.project_api_keys.append(
        ProjectApiKeyRecord(
            id="api-key-1",
            project_id="project-1",
            name="Detail chat key",
            key_prefix="stimp_live_demo",
            key_hash=hash_api_key("detail-chat-key"),
            status=ProjectApiKeyStatus.ACTIVE,
            last_used_at=None,
            revoked_at=None,
            created_at=security_repository.secret_ref.created_at,
            updated_at=security_repository.secret_ref.updated_at,
        )
    )
    app.dependency_overrides[get_incident_chat_repository] = lambda: incident_repository
    app.dependency_overrides[get_incident_chat_service] = StubIncidentChatService
    app.dependency_overrides[get_incident_chat_control_plane_repository] = lambda: security_repository

    client = TestClient(app)
    response = client.post(
        "/incidents/incident-1/chat",
        json={"messages": [{"role": "user", "content": "What happened?"}]},
        headers={"X-Stimpact-Project-Key": "detail-chat-key"},
    )

    assert response.status_code == 200
    assert response.json()["referenced_incident_ids"] == ["incident-1"]


def test_get_incident_classification_returns_category_payload() -> None:
    app = build_test_app()
    repository = StubIncidentRepository()
    app.dependency_overrides[get_incident_repository] = lambda: repository
    app.dependency_overrides[get_failure_classifier] = StubFailureClassifier

    client = TestClient(app)
    response = client.get("/incidents/incident-1/classification", params={"event_limit": 20})

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == "incident-1"
    assert body["category"] == "database_failure"
    assert body["matched_signals"] == ["database", "postgres"]


def test_get_incident_root_cause_returns_analysis_payload() -> None:
    app = build_test_app()
    app.dependency_overrides[get_incident_repository] = StubIncidentRepository
    app.dependency_overrides[get_root_cause_analysis_service] = StubRootCauseAnalysisService

    client = TestClient(app)
    response = client.get("/incidents/incident-1/root-cause", params={"event_limit": 20})

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == "incident-1"
    assert body["category"] == "database_failure"
    assert body["reasoning"]["confidence"] == 0.78
    assert body["evidence"]["suspected_component"] == "agent-platform/api/repositories/incident_repository.py"


def test_get_incident_patch_returns_patch_payload() -> None:
    app = build_test_app()
    app.dependency_overrides[get_incident_repository] = StubIncidentRepository
    app.dependency_overrides[get_patch_generation_service] = StubPatchGenerationService

    client = TestClient(app)
    response = client.get("/incidents/incident-1/patch", params={"event_limit": 20})

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == "incident-1"
    assert body["status"] == "generated"
    assert body["file_count"] == 1
    assert body["target_files"][0]["path"] == "agent-platform/api/repositories/incident_repository.py"


def test_get_incident_sandbox_run_returns_payload() -> None:
    app = build_test_app()
    app.dependency_overrides[get_incident_repository] = StubIncidentRepository
    app.dependency_overrides[get_sandbox_verification_service] = StubSandboxVerificationService

    client = TestClient(app)
    response = client.get("/incidents/incident-1/sandbox-run")

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == "incident-1"
    assert body["status"] == "succeeded"
    assert body["verification_succeeded"] is True


def test_post_incident_sandbox_run_executes_verification() -> None:
    app = build_test_app()
    app.dependency_overrides[get_incident_repository] = StubIncidentRepository
    app.dependency_overrides[get_sandbox_verification_service] = StubSandboxVerificationService

    client = TestClient(app)
    response = client.post("/incidents/incident-1/sandbox-run", params={"event_limit": 20})

    assert response.status_code == 202
    body = response.json()
    assert body["sandbox_run"]["incident_id"] == "incident-1"
    assert body["async_job_id"] == "job-1"


def test_list_incident_sandbox_runs_returns_history() -> None:
    app = build_test_app()
    app.dependency_overrides[get_incident_repository] = StubIncidentRepository
    app.dependency_overrides[get_sandbox_verification_service] = StubSandboxVerificationService

    client = TestClient(app)
    response = client.get("/incidents/incident-1/sandbox-runs", params={"limit": 20})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "succeeded"


def test_get_incident_sandbox_run_detail_returns_steps_and_artifacts() -> None:
    app = build_test_app()
    app.dependency_overrides[get_incident_repository] = StubIncidentRepository
    app.dependency_overrides[get_sandbox_verification_service] = StubSandboxVerificationService
    app.dependency_overrides[get_sandbox_repository] = StubSandboxRepository
    app.dependency_overrides[get_artifact_repository] = StubArtifactRepository

    client = TestClient(app)
    response = client.get("/incidents/incident-1/sandbox-runs/sandbox-1")

    assert response.status_code == 200
    body = response.json()
    assert body["run"]["incident_id"] == "incident-1"
    assert body["steps"][0]["step_name"] == "submit-kubernetes-job"
    assert body["artifacts"][0]["storage_backend"] == "s3"


def test_create_autonomous_run_returns_queued_run() -> None:
    app = build_test_app()
    app.dependency_overrides[get_incident_repository] = StubIncidentRepository
    app.dependency_overrides[get_autonomous_run_service] = StubAutonomousRunService

    client = TestClient(app)
    response = client.post(
        "/incidents/incident-1/autonomous-runs",
        json={
            "feature_seeds": [
                {
                    "feature_name": "billing timeout resolved",
                    "description": "The billing timeout should no longer reproduce after the repair.",
                    "verification_method": "browser assertion",
                    "required_verification": ["browser"],
                    "browser_required": True,
                    "notes": [],
                }
            ],
            "max_steps": 8,
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["run"]["id"] == "auto-run-1"
    assert body["run"]["status"] == "succeeded"


def test_list_autonomous_runs_returns_history() -> None:
    app = build_test_app()
    app.dependency_overrides[get_incident_repository] = StubIncidentRepository
    app.dependency_overrides[get_autonomous_run_service] = StubAutonomousRunService

    client = TestClient(app)
    response = client.get("/incidents/incident-1/autonomous-runs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == "auto-run-1"


def test_get_latest_autonomous_run_returns_detail() -> None:
    app = build_test_app()
    app.dependency_overrides[get_incident_repository] = StubIncidentRepository
    app.dependency_overrides[get_autonomous_run_service] = StubAutonomousRunService

    client = TestClient(app)
    response = client.get("/incidents/incident-1/autonomous-runs/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["run"]["id"] == "auto-run-1"
    assert body["outcome"]["total_tool_calls"] == 4


def test_stream_autonomous_run_events_returns_sse_snapshot() -> None:
    app = build_test_app()
    app.dependency_overrides[get_incident_repository] = StubIncidentRepository
    app.dependency_overrides[get_autonomous_run_service] = StubAutonomousRunService

    client = TestClient(app)
    with client.stream("GET", "/incidents/incident-1/autonomous-runs/auto-run-1/events") as response:
        assert response.status_code == 200
        payload = "".join(response.iter_text())

    assert '"id": "auto-run-1"' in payload
    assert '"event_type": "run_completed"' in payload


def test_approve_autonomous_run_returns_updated_detail() -> None:
    app = build_test_app()
    app.dependency_overrides[get_incident_repository] = StubIncidentRepository
    app.dependency_overrides[get_autonomous_run_service] = StubAutonomousRunService

    client = TestClient(app)
    response = client.post(
        "/incidents/incident-1/autonomous-runs/auto-run-1/approval",
        json={"approval_status": "approved"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run"]["approval_status"] == "approved"


def test_promote_autonomous_run_returns_promotion_metadata() -> None:
    app = build_test_app()
    app.dependency_overrides[get_incident_repository] = StubIncidentRepository
    app.dependency_overrides[get_autonomous_run_service] = StubAutonomousRunService

    client = TestClient(app)
    response = client.post("/incidents/incident-1/autonomous-runs/auto-run-1/promote")

    assert response.status_code == 200
    body = response.json()
    assert body["run"]["promotion_status"] == "proposed"
    assert body["run"]["promotion_branch_name"] == "stimpact/fix/incident-1"


def test_create_secret_ref_writes_to_secret_manager_and_returns_metadata() -> None:
    app = build_test_app()
    app.dependency_overrides[get_control_plane_repository] = StubControlPlaneRepository
    app.dependency_overrides[get_secrets_writer] = StubSecretsWriter

    client = TestClient(app)
    response = client.post(
        "/control-plane/secret-refs",
        json={
            "project_id": "project-1",
            "label": "OPENAI_API_KEY",
            "description": "Runtime secret",
            "value": "super-secret-value",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["project_id"] == "project-1"
    assert body["backend"] == "aws_secrets_manager"
    assert "external_ref" not in body


def test_create_repo_profile_returns_profile_with_secret_refs() -> None:
    app = build_test_app()
    repository = StubControlPlaneRepository()
    app.dependency_overrides[get_control_plane_repository] = lambda: repository

    client = TestClient(app)
    response = client.post(
        "/control-plane/repo-profiles",
        json={
            "project_id": "project-1",
            "provider_repository_id": "provider-repo-1",
            "runtime_kind": "python",
            "base_image": "public.ecr.aws/docker/library/python:3.12",
            "install_command": "pip install -r requirements.txt",
            "startup_commands": ["python app.py"],
            "reproduce_command": "python reproduce.py",
            "verify_command": "pytest",
            "success_criteria": "Exit 0 after patch verification.",
            "network_allowlist": ["pypi.org"],
            "secret_ref_ids": ["secret-1"],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["project_id"] == "project-1"
    assert body["runtime_kind"] == "python"
    assert body["secret_refs"][0]["id"] == "secret-1"
    assert body["secret_mounts"][0]["mount_as"] == "OPENAI_API_KEY"


def test_create_repo_profile_accepts_explicit_secret_mounts() -> None:
    app = build_test_app()
    repository = StubControlPlaneRepository()
    app.dependency_overrides[get_control_plane_repository] = lambda: repository

    client = TestClient(app)
    response = client.post(
        "/control-plane/repo-profiles",
        json={
            "project_id": "project-1",
            "provider_repository_id": "provider-repo-1",
            "runtime_kind": "python",
            "reproduce_command": "python reproduce.py",
            "verify_command": "pytest",
            "secret_mounts": [
                {
                    "secret_ref_id": "secret-1",
                    "mount_as": "/var/run/stimpact/openai.key",
                }
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["secret_mounts"][0]["mount_as"] == "/var/run/stimpact/openai.key"


def test_create_github_app_integration_returns_verified_record() -> None:
    app = build_test_app()
    app.dependency_overrides[get_provider_integration_service] = StubProviderIntegrationService

    client = TestClient(app)
    response = client.post(
        "/control-plane/provider-integrations/github-app",
        json={
            "project_id": "project-1",
            "name": "Acme GitHub",
            "installation_id": "117170229",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["provider"] == "github"
    assert body["metadata"]["installation_id"] == "117170229"


def test_start_github_app_install_returns_installation_url() -> None:
    app = build_test_app()
    app.dependency_overrides[get_provider_integration_service] = StubProviderIntegrationService

    client = TestClient(app)
    response = client.post(
        "/control-plane/projects/project-1/provider-integrations/github-app/start",
        json={
            "project_id": "project-1",
            "name": "ScaleProject GitHub",
            "redirect_url": "http://localhost:3000/onboarding?provider=github&step=3",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["integration"]["provider"] == "github"
    assert body["installation_url"].startswith("https://github.com/apps/stimpact/installations/new")


def test_start_gitlab_oauth_returns_authorization_url() -> None:
    app = build_test_app()
    app.dependency_overrides[get_provider_integration_service] = StubProviderIntegrationService

    client = TestClient(app)
    response = client.post(
        "/control-plane/provider-integrations/gitlab/oauth/start",
        json={
            "project_id": "project-1",
            "name": "Acme GitLab",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["integration"]["provider"] == "gitlab"
    assert body["authorization_url"].startswith("https://gitlab.com/oauth/authorize")


def test_sync_provider_repositories_returns_synced_records() -> None:
    app = build_test_app()
    app.dependency_overrides[get_provider_integration_service] = StubProviderIntegrationService

    client = TestClient(app)
    response = client.post("/control-plane/provider-integrations/integration-1/repositories/sync")

    assert response.status_code == 200
    body = response.json()
    assert body["integration"]["id"] == "integration-1"
    assert body["repositories"][0]["name"] == "billing-api"


def test_list_provider_repositories_returns_synced_records() -> None:
    app = build_test_app()
    app.dependency_overrides[get_provider_integration_service] = StubProviderIntegrationService

    client = TestClient(app)
    response = client.get("/control-plane/provider-integrations/integration-1/repositories")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["provider_integration_id"] == "integration-1"


def test_infer_project_repo_profile_defaults_returns_suggestions() -> None:
    app = build_test_app()
    app.dependency_overrides[get_provider_integration_service] = StubProviderIntegrationService

    client = TestClient(app)
    response = client.get(
        "/control-plane/projects/project-1/provider-repositories/provider-repo-1/repo-profile-defaults",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["runtime_kind"] == "node"
    assert body["install_command"] == "npm ci"
    assert body["verify_command"] == "npm test"
    assert body["monorepo"] is True


def test_infer_project_repo_profile_defaults_returns_actionable_error() -> None:
    class FailingProviderIntegrationService(StubProviderIntegrationService):
        async def infer_repo_profile_defaults(
            self,
            *,
            project_id: str,
            provider_repository_id: str,
        ) -> RepoProfileInferenceResult:
            raise APIError(
                "Unable to inspect billing-api automatically. The repo connection succeeded, but command inference could not finish.",
                status_code=502,
                code="repo_profile_inference_git_failed",
            )

    app = build_test_app()
    app.dependency_overrides[get_provider_integration_service] = FailingProviderIntegrationService

    client = TestClient(app)
    response = client.get(
        "/control-plane/projects/project-1/provider-repositories/provider-repo-1/repo-profile-defaults",
    )

    assert response.status_code == 502
    body = response.json()
    assert body["error"]["code"] == "repo_profile_inference_git_failed"
    assert "repo connection succeeded" in body["error"]["message"]


def test_project_onboarding_returns_aggregated_project_state() -> None:
    app = build_test_app()
    repository = StubControlPlaneRepository()
    app.dependency_overrides[get_control_plane_repository] = lambda: repository

    client = TestClient(app)
    response = client.get("/control-plane/projects/project-1/onboarding")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "project-1"
    assert body["policy"]["project_id"] == "project-1"
    assert body["onboarding_state"]["sdk_setup_status"] == "pending"
    assert body["operational_readiness"]["has_active_api_keys"] is False
    assert body["operational_readiness"]["complete"] is False
    assert body["secret_refs"][0]["id"] == "secret-1"
    assert body["integrations"][0]["integration"]["id"] == "integration-1"
    assert body["integrations"][0]["repositories"][0]["id"] == "provider-repo-1"
    assert body["repo_profiles"][0]["id"] == "profile-1"


def test_project_secret_ref_route_rejects_mismatched_project_id() -> None:
    app = build_test_app()
    app.dependency_overrides[get_control_plane_repository] = StubControlPlaneRepository
    app.dependency_overrides[get_secrets_writer] = StubSecretsWriter

    client = TestClient(app)
    response = client.post(
        "/control-plane/projects/project-1/secret-refs",
        json={
            "project_id": "project-2",
            "label": "OPENAI_API_KEY",
            "description": "Runtime secret",
            "value": "super-secret-value",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "project_mismatch"


def test_delete_project_secret_ref_returns_no_content() -> None:
    app = build_test_app()
    app.dependency_overrides[get_control_plane_repository] = StubControlPlaneRepository
    app.dependency_overrides[get_secrets_writer] = StubSecretsWriter

    client = TestClient(app)
    response = client.delete("/control-plane/projects/project-1/secret-refs/secret-1")

    assert response.status_code == 204


def test_project_onboarding_route_accepts_project_api_key_when_admin_auth_enabled(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ADMIN_TOKEN", "admin-token")
    repository = StubControlPlaneRepository()
    repository.project_api_keys.append(
        ProjectApiKeyRecord(
            id="api-key-1",
            project_id="project-1",
            name="onboarding",
            key_prefix="stimp_live_demo",
            key_hash=hash_api_key("project-secret-key"),
            status=ProjectApiKeyStatus.ACTIVE,
            last_used_at=None,
            revoked_at=None,
            created_at=repository.secret_ref.created_at,
            updated_at=repository.secret_ref.updated_at,
        )
    )
    app = build_test_app()
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_security_control_plane_repository] = lambda: repository

    client = TestClient(app)
    response = client.get(
        "/control-plane/projects/project-1/onboarding",
        headers={"X-Stimpact-Project-Key": "project-secret-key"},
    )

    assert response.status_code == 200
    assert response.json()["project_id"] == "project-1"


def test_gitlab_callback_exchanges_code_and_returns_connected_integration() -> None:
    app = build_test_app()
    app.dependency_overrides[get_provider_integration_service] = StubProviderIntegrationService

    client = TestClient(app)
    response = client.get(
        "/auth/gitlab/callback",
        params={"state": "oauth-state-1", "code": "gitlab-code"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["integration"]["provider"] == "gitlab"
    assert body["credentials_secret_ref"]["id"] == "secret-1"
    assert body["connected_account"]["account_login"] == "connor"


def test_github_callback_returns_installation_preview() -> None:
    app = build_test_app()
    app.dependency_overrides[get_provider_integration_service] = StubProviderIntegrationService

    client = TestClient(app)
    response = client.get(
        "/api/github/callback",
        params={"installation_id": "117170229", "setup_action": "install"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "github"
    assert body["account_login"] == "acme"


def test_github_callback_redirects_back_to_onboarding_when_state_is_present() -> None:
    app = build_test_app()
    app.dependency_overrides[get_provider_integration_service] = StubProviderIntegrationService

    client = TestClient(app)
    response = client.get(
        "/api/github/callback",
        params={
            "installation_id": "117170229",
            "setup_action": "install",
            "state": "github-install-state-1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("http://localhost:3000/onboarding")
    assert "provider_status=connected" in response.headers["location"]
    assert "synced_repositories=4" in response.headers["location"]


def test_github_webhook_accepts_verified_payload() -> None:
    app = build_test_app()
    app.dependency_overrides[get_provider_integration_service] = StubProviderIntegrationService

    client = TestClient(app)
    response = client.post(
        "/webhooks/github",
        content=b'{"zen":"keep it logically awesome"}',
        headers={
            "X-Hub-Signature-256": "sha256=test-signature",
            "X-GitHub-Event": "ping",
            "X-GitHub-Delivery": "delivery-1",
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["provider"] == "github"
    assert body["event"] == "ping"


def test_health_routes_report_liveness_and_readiness() -> None:
    app = build_test_app()
    client = TestClient(app)

    live = client.get("/health/live")
    ready = client.get("/health/ready")
    metrics = client.get("/health/metrics")

    assert live.status_code == 200
    assert live.json()["status"] == "ok"
    assert ready.status_code == 200
    assert ready.json()["checks"]["database"]["ready"] is True
    assert metrics.status_code == 200
    assert "stimpact_build_info" in metrics.text


def test_health_readiness_returns_503_when_strict_and_database_is_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_STRICT_READINESS", "true")

    class UnreadyPostgresManager:
        is_configured = True

        async def ping(self) -> bool:
            return False

    app = build_test_app()
    app.state.postgres = UnreadyPostgresManager()
    client = TestClient(app)

    ready = client.get("/health/ready")

    assert ready.status_code == 503
    assert ready.json()["status"] == "degraded"


def test_control_plane_routes_require_admin_token_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ADMIN_TOKEN", "super-admin-token")
    app = build_test_app()
    app.dependency_overrides[get_control_plane_repository] = StubControlPlaneRepository
    client = TestClient(app)

    unauthorized = client.get("/control-plane/provider-integrations")
    authorized = client.get(
        "/control-plane/provider-integrations",
        headers={"Authorization": "Bearer super-admin-token"},
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200


def test_telemetry_ingest_requires_project_api_key_when_project_has_active_key() -> None:
    app = build_test_app()
    repository = StubControlPlaneRepository()
    repository.project_api_keys.append(
        ProjectApiKeyRecord(
            id="api-key-1",
            project_id="project-1",
            name="SDK key",
            key_prefix="stimp_live_demo",
            key_hash=hash_api_key("secret-project-key"),
            status=ProjectApiKeyStatus.ACTIVE,
            last_used_at=None,
            revoked_at=None,
            created_at=repository.secret_ref.created_at,
            updated_at=repository.secret_ref.updated_at,
        )
    )
    app.dependency_overrides[get_security_control_plane_repository] = lambda: repository
    app.state.outbox_signaler = RecordingOutboxSignaler()
    app.dependency_overrides[get_telemetry_repository] = RecordingTelemetryRepository
    app.dependency_overrides[get_incident_event_publisher] = IncidentEventPublisher
    client = TestClient(app)
    payload = {
        "project_id": "project-1",
        "environment": "production",
        "service": "billing-api",
        "error_message": "Database timeout",
        "stacktrace": "Traceback",
        "timestamp": "2026-03-16T12:00:00Z",
    }

    unauthorized = client.post("/telemetry/error", json=payload)
    authorized = client.post(
        "/telemetry/error",
        json=payload,
        headers={"X-Stimpact-Project-Key": "secret-project-key"},
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 202


def test_project_api_keys_can_be_created_listed_and_revoked(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ADMIN_TOKEN", "super-admin-token")
    app = build_test_app()
    repository = StubControlPlaneRepository()
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    client = TestClient(app)
    headers = {"Authorization": "Bearer super-admin-token"}

    created = client.post(
        "/control-plane/projects/project-1/api-keys",
        json={"name": "SDK ingest"},
        headers=headers,
    )
    assert created.status_code == 201
    created_body = created.json()
    assert created_body["api_key"]["project_id"] == "project-1"
    assert created_body["plaintext_key"].startswith("stimp_live_")

    listed = client.get("/control-plane/projects/project-1/api-keys", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    revoked = client.post(
        f"/control-plane/projects/project-1/api-keys/{created_body['api_key']['id']}/revoke",
        headers=headers,
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"


def test_project_browser_keys_can_be_created_updated_listed_and_revoked(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ADMIN_TOKEN", "super-admin-token")
    app = build_test_app()
    repository = StubControlPlaneRepository()
    app.state.telemetry_origin_registry = TelemetryOriginRegistry(
        pool_getter=lambda: None,
        fallback_origins=[],
        lookup_override=repository.list_active_project_browser_key_origins,
    )
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    client = TestClient(app)
    headers = {"Authorization": "Bearer super-admin-token"}

    created = client.post(
        "/control-plane/projects/project-1/browser-keys",
        json={"name": "Browser telemetry", "allowed_origins": ["https://app.example.com"]},
        headers=headers,
    )
    assert created.status_code == 201
    created_body = created.json()
    assert created_body["browser_key"]["project_id"] == "project-1"
    assert created_body["plaintext_key"].startswith("stimp_browser_")
    assert created_body["browser_key"]["allowed_origins"] == ["https://app.example.com"]

    updated = client.patch(
        f"/control-plane/projects/project-1/browser-keys/{created_body['browser_key']['id']}",
        json={"allowed_origins": ["https://syntheticsoulsongs.com"]},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["allowed_origins"] == ["https://syntheticsoulsongs.com"]

    listed = client.get("/control-plane/projects/project-1/browser-keys", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["allowed_origins"] == ["https://syntheticsoulsongs.com"]

    revoked = client.post(
        f"/control-plane/projects/project-1/browser-keys/{created_body['browser_key']['id']}/revoke",
        headers=headers,
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"


def test_project_browser_keys_require_allowed_origins(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ADMIN_TOKEN", "super-admin-token")
    app = build_test_app()
    repository = StubControlPlaneRepository()
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    client = TestClient(app)
    headers = {"Authorization": "Bearer super-admin-token"}

    created = client.post(
        "/control-plane/projects/project-1/browser-keys",
        json={"name": "Browser telemetry", "allowed_origins": []},
        headers=headers,
    )
    assert created.status_code == 422

    seeded = ProjectBrowserKeyRecord(
        id="browser-key-1",
        project_id="project-1",
        name="Browser telemetry",
        key_prefix="stimp_browser_demo",
        key_hash=hash_api_key("stimp_browser_secret"),
        allowed_origins=["https://app.example.com"],
        status=ProjectBrowserKeyStatus.ACTIVE,
        last_used_at=None,
        last_issued_at=None,
        revoked_at=None,
        created_at=repository.secret_ref.created_at,
        updated_at=repository.secret_ref.updated_at,
    )
    repository.project_browser_keys.append(seeded)

    updated = client.patch(
        "/control-plane/projects/project-1/browser-keys/browser-key-1",
        json={"allowed_origins": []},
        headers=headers,
    )
    assert updated.status_code == 422


def test_updating_project_policy_marks_onboarding_policy_reviewed(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ADMIN_TOKEN", "super-admin-token")
    app = build_test_app()
    repository = StubControlPlaneRepository()
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    client = TestClient(app)
    headers = {"Authorization": "Bearer super-admin-token"}

    response = client.put(
        "/control-plane/projects/project-1/policy",
        json={
            "autonomy_mode": "recommend",
            "require_human_approval": True,
            "allow_production_writes": False,
            "allow_low_risk_autonomy": True,
            "block_during_active_deploys": True,
            "restrict_to_approved_services": False,
            "require_rollback_plan": True,
            "require_post_action_verification": True,
            "approved_services": ["billing-api"],
            "failure_classifier_enabled": True,
            "root_cause_enabled": True,
            "patch_planner_enabled": True,
            "runbook_executor_enabled": False,
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert repository.project_onboarding_state.policy_reviewed is True


def test_project_onboarding_state_can_be_updated(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ADMIN_TOKEN", "super-admin-token")
    app = build_test_app()
    repository = StubControlPlaneRepository()
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    client = TestClient(app)
    headers = {"Authorization": "Bearer super-admin-token"}

    response = client.put(
        "/control-plane/projects/project-1/onboarding-state",
        json={
            "sdk_setup_status": "manual",
            "sdk_setup_provider_repository_id": "provider-repo-1",
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sdk_setup_status"] == "manual"
    assert body["sdk_setup_provider_repository_id"] == "provider-repo-1"


def test_sdk_bootstrap_change_request_creates_key_and_updates_onboarding_state(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ADMIN_TOKEN", "super-admin-token")
    from services.sdk_bootstrap import (
        SdkBootstrapManualStep,
        SdkBootstrapPatch,
        SdkBootstrapPatchAttempt,
        SdkBootstrapPlan,
        SdkBootstrapPlannedFile,
        SdkBootstrapPreparedPreview,
        SdkBootstrapStrategy,
        SdkBootstrapVerification,
    )
    import api.routes.control_plane as control_plane_module

    app = build_test_app()
    repository = StubControlPlaneRepository()
    provider_service = StubProviderIntegrationService()
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_provider_integration_service] = lambda: provider_service
    client = TestClient(app)
    headers = {"Authorization": "Bearer super-admin-token"}

    monkeypatch.setattr(
        control_plane_module,
        "plan_sdk_bootstrap_from_clone",
        lambda **_: SdkBootstrapPlan(
            runtime="javascript",
            warnings=[],
            recommended_strategy_id="javascript-next:.:src/app/layout.tsx",
            requires_confirmation=False,
            strategies=[
                SdkBootstrapStrategy(
                    id="javascript-next:.:src/app/layout.tsx",
                    language="javascript",
                    framework="Next.js",
                    summary="Inject browser auto-capture.",
                    confidence="high",
                    pr_supported=True,
                    target_subpath=".",
                    entrypoints=["src/app/layout.tsx"],
                    planned_files=[
                        SdkBootstrapPlannedFile(
                            path="package.json",
                            action="update",
                            reason="Add dependency.",
                        )
                    ],
                    manual_steps=[SdkBootstrapManualStep(title="Install", content="Run npm install @stimpact/sdk")],
                )
            ],
        ),
    )
    monkeypatch.setattr(
        control_plane_module,
        "prepare_sdk_bootstrap_preview_from_clone",
        lambda **_: SdkBootstrapPreparedPreview(
            plan=SdkBootstrapPlan(
                runtime="javascript",
                warnings=[],
                recommended_strategy_id="javascript-next:.:src/app/layout.tsx",
                requires_confirmation=False,
                strategies=[
                    SdkBootstrapStrategy(
                        id="javascript-next:.:src/app/layout.tsx",
                        language="javascript",
                        framework="Next.js",
                        summary="Inject browser auto-capture into the app shell.",
                        confidence="high",
                        pr_supported=True,
                        target_subpath=".",
                        entrypoints=["src/app/layout.tsx"],
                        assumptions=["src/app/layout.tsx is the main browser shell."],
                        blockers=[],
                        planned_files=[
                            SdkBootstrapPlannedFile(
                                path="package.json",
                                action="update",
                                reason="Add dependency.",
                            )
                        ],
                        manual_steps=[SdkBootstrapManualStep(title="Install", content="Run npm install @stimpact/sdk")],
                    )
                ],
            ),
            selected_strategy_id="javascript-next:.:src/app/layout.tsx",
            strategy=SdkBootstrapStrategy(
                id="javascript-next:.:src/app/layout.tsx",
                language="javascript",
                framework="Next.js",
                summary="Inject browser auto-capture into the app shell.",
                confidence="high",
                pr_supported=True,
                target_subpath=".",
                entrypoints=["src/app/layout.tsx"],
                assumptions=["src/app/layout.tsx is the main browser shell."],
                blockers=[],
                planned_files=[
                    SdkBootstrapPlannedFile(
                        path="package.json",
                        action="update",
                        reason="Add dependency.",
                    )
                ],
                manual_steps=[SdkBootstrapManualStep(title="Install", content="Run npm install @stimpact/sdk")],
            ),
            patch=SdkBootstrapPatch(
                patch_diff="diff --git a/package.json b/package.json\n",
                attempt=SdkBootstrapPatchAttempt(
                    strategy_id="javascript-next:.:src/app/layout.tsx",
                    patch_source="deterministic",
                    patch_generated=True,
                    patch_applied=True,
                    verification=SdkBootstrapVerification(status="passed", summary="ok"),
                    preview_available=True,
                    change_request_allowed=True,
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        control_plane_module,
        "build_sdk_bootstrap_patch_from_clone",
        lambda **_: SdkBootstrapPatch(
            patch_diff="diff --git a/package.json b/package.json\n",
            attempt=SdkBootstrapPatchAttempt(
                strategy_id="javascript-next:.:src/app/layout.tsx",
                patch_source="deterministic",
                patch_generated=True,
                patch_applied=True,
                verification=SdkBootstrapVerification(status="passed", summary="ok"),
                preview_available=True,
                change_request_allowed=True,
            ),
        ),
    )

    response = client.post(
        "/control-plane/projects/project-1/sdk-bootstrap/change-request",
        json={
            "project_id": "project-1",
            "provider_repository_id": "provider-repo-1",
            "api_key_name": "Telemetry bootstrap",
            "service_name": "billing-api",
            "environment": "production",
            "base_url": "https://stimpact.example.com",
            "branch_name": "stimpact/sdk-bootstrap-preview-1234",
        },
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["run_id"] is not None
    assert body["plaintext_key"].startswith("stimp_live_")
    assert body["branch_name"] == "stimpact/sdk-bootstrap-preview-1234"
    assert body["change_request_url"] == "https://github.com/acme/billing-api/pull/42"
    assert body["final_attempt"]["verification"]["status"] == "passed"
    assert repository.project_onboarding_state.sdk_setup_status is ProjectSdkSetupStatus.CHANGE_REQUEST


def test_sdk_bootstrap_change_request_reuses_existing_api_key(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ADMIN_TOKEN", "super-admin-token")
    from services.sdk_bootstrap import (
        SdkBootstrapManualStep,
        SdkBootstrapPatch,
        SdkBootstrapPatchAttempt,
        SdkBootstrapPlan,
        SdkBootstrapPlannedFile,
        SdkBootstrapPreparedPreview,
        SdkBootstrapStrategy,
        SdkBootstrapVerification,
    )
    import api.routes.control_plane as control_plane_module

    app = build_test_app()
    repository = StubControlPlaneRepository()
    provider_service = StubProviderIntegrationService()
    existing_plaintext_key = "stimp_live_existing_secret"
    repository.project_api_keys.append(
        ProjectApiKeyRecord(
            id="api-key-1",
            project_id="project-1",
            name="Telemetry bootstrap",
            key_prefix="stimp_live_existing",
            key_hash=hash_api_key(existing_plaintext_key),
            status=ProjectApiKeyStatus.ACTIVE,
            last_used_at=None,
            revoked_at=None,
            created_at=repository.secret_ref.created_at,
            updated_at=repository.secret_ref.updated_at,
        )
    )
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_provider_integration_service] = lambda: provider_service
    client = TestClient(app)
    headers = {"Authorization": "Bearer super-admin-token"}

    monkeypatch.setattr(
        control_plane_module,
        "prepare_sdk_bootstrap_preview_from_clone",
        lambda **_: SdkBootstrapPreparedPreview(
            plan=SdkBootstrapPlan(
                runtime="python",
                warnings=[],
                recommended_strategy_id="python-fastapi:.:main.py",
                requires_confirmation=False,
                strategies=[
                    SdkBootstrapStrategy(
                        id="python-fastapi:.:main.py",
                        language="python",
                        framework="FastAPI",
                        summary="Install telemetry middleware.",
                        confidence="high",
                        pr_supported=True,
                        target_subpath=".",
                        entrypoints=["main.py"],
                        assumptions=["main.py is the ASGI entrypoint."],
                        blockers=[],
                        planned_files=[
                            SdkBootstrapPlannedFile(
                                path="main.py",
                                action="update",
                                reason="Install middleware hook.",
                            )
                        ],
                        manual_steps=[SdkBootstrapManualStep(title="Install", content="Run pip install stimpact-sdk")],
                    )
                ],
            ),
            selected_strategy_id="python-fastapi:.:main.py",
            strategy=SdkBootstrapStrategy(
                id="python-fastapi:.:main.py",
                language="python",
                framework="FastAPI",
                summary="Install telemetry middleware.",
                confidence="high",
                pr_supported=True,
                target_subpath=".",
                entrypoints=["main.py"],
                assumptions=["main.py is the ASGI entrypoint."],
                blockers=[],
                planned_files=[
                    SdkBootstrapPlannedFile(
                        path="main.py",
                        action="update",
                        reason="Install middleware hook.",
                    )
                ],
                manual_steps=[SdkBootstrapManualStep(title="Install", content="Run pip install stimpact-sdk")],
            ),
            patch=SdkBootstrapPatch(
                patch_diff="diff --git a/main.py b/main.py\n",
                attempt=SdkBootstrapPatchAttempt(
                    strategy_id="python-fastapi:.:main.py",
                    patch_source="deterministic",
                    patch_generated=True,
                    patch_applied=True,
                    verification=SdkBootstrapVerification(status="passed", summary="ok"),
                    preview_available=True,
                    change_request_allowed=True,
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        control_plane_module,
        "build_sdk_bootstrap_patch_from_clone",
        lambda **_: SdkBootstrapPatch(
            patch_diff="diff --git a/main.py b/main.py\n",
            attempt=SdkBootstrapPatchAttempt(
                strategy_id="python-fastapi:.:main.py",
                patch_source="deterministic",
                patch_generated=True,
                patch_applied=True,
                verification=SdkBootstrapVerification(status="passed", summary="ok"),
                preview_available=True,
                change_request_allowed=True,
            ),
        ),
    )

    response = client.post(
        "/control-plane/projects/project-1/sdk-bootstrap/change-request",
        json={
            "project_id": "project-1",
            "provider_repository_id": "provider-repo-1",
            "api_key_name": "Telemetry bootstrap",
            "existing_api_key_id": "api-key-1",
            "existing_plaintext_key": existing_plaintext_key,
            "service_name": "billing-api",
            "environment": "production",
            "base_url": "https://stimpact.example.com",
            "branch_name": "stimpact/sdk-bootstrap-preview-existing-api",
        },
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["api_key"]["id"] == "api-key-1"
    assert body["plaintext_key"] == existing_plaintext_key
    assert len(repository.project_api_keys) == 1


def test_sdk_bootstrap_change_request_reuses_existing_browser_key(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ADMIN_TOKEN", "super-admin-token")
    from services.sdk_bootstrap import (
        SdkBootstrapManualStep,
        SdkBootstrapPatch,
        SdkBootstrapPatchAttempt,
        SdkBootstrapPlan,
        SdkBootstrapPlannedFile,
        SdkBootstrapPreparedPreview,
        SdkBootstrapStrategy,
        SdkBootstrapVerification,
    )
    from services.sdk_catalog import SdkEnvVarSpec
    import api.routes.control_plane as control_plane_module

    app = build_test_app()
    repository = StubControlPlaneRepository()
    provider_service = StubProviderIntegrationService()
    existing_plaintext_key = "stimp_browser_existing_secret"
    repository.project_browser_keys.append(
        ProjectBrowserKeyRecord(
            id="browser-key-1",
            project_id="project-1",
            name="Telemetry bootstrap",
            key_prefix="stimp_browser_existing",
            key_hash=hash_api_key(existing_plaintext_key),
            allowed_origins=["https://old.example.com"],
            status=ProjectBrowserKeyStatus.ACTIVE,
            last_used_at=None,
            last_issued_at=None,
            revoked_at=None,
            created_at=repository.secret_ref.created_at,
            updated_at=repository.secret_ref.updated_at,
        )
    )
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_provider_integration_service] = lambda: provider_service
    client = TestClient(app)
    headers = {"Authorization": "Bearer super-admin-token"}
    browser_env_vars = [
        SdkEnvVarSpec(
            name="NEXT_PUBLIC_STIMPACT_PROJECT_ID",
            example_value="project-1",
            description="Browser SDK project id.",
        )
    ]

    monkeypatch.setattr(
        control_plane_module,
        "prepare_sdk_bootstrap_preview_from_clone",
        lambda **_: SdkBootstrapPreparedPreview(
            plan=SdkBootstrapPlan(
                runtime="javascript",
                warnings=[],
                recommended_strategy_id="javascript-next:.:src/app/layout.tsx",
                requires_confirmation=False,
                strategies=[
                    SdkBootstrapStrategy(
                        id="javascript-next:.:src/app/layout.tsx",
                        language="javascript",
                        framework="Next.js",
                        summary="Inject browser auto-capture.",
                        confidence="high",
                        pr_supported=True,
                        target_subpath=".",
                        entrypoints=["src/app/layout.tsx"],
                        assumptions=["src/app/layout.tsx is the main browser shell."],
                        blockers=[],
                        planned_files=[
                            SdkBootstrapPlannedFile(
                                path="package.json",
                                action="update",
                                reason="Add dependency.",
                            )
                        ],
                        env_vars=browser_env_vars,
                        manual_steps=[SdkBootstrapManualStep(title="Install", content="Run npm install @stimpact/sdk")],
                    )
                ],
            ),
            selected_strategy_id="javascript-next:.:src/app/layout.tsx",
            strategy=SdkBootstrapStrategy(
                id="javascript-next:.:src/app/layout.tsx",
                language="javascript",
                framework="Next.js",
                summary="Inject browser auto-capture into the app shell.",
                confidence="high",
                pr_supported=True,
                target_subpath=".",
                entrypoints=["src/app/layout.tsx"],
                assumptions=["src/app/layout.tsx is the main browser shell."],
                blockers=[],
                planned_files=[
                    SdkBootstrapPlannedFile(
                        path="package.json",
                        action="update",
                        reason="Add dependency.",
                    )
                ],
                env_vars=browser_env_vars,
                manual_steps=[SdkBootstrapManualStep(title="Install", content="Run npm install @stimpact/sdk")],
            ),
            patch=SdkBootstrapPatch(
                patch_diff="diff --git a/package.json b/package.json\n",
                attempt=SdkBootstrapPatchAttempt(
                    strategy_id="javascript-next:.:src/app/layout.tsx",
                    patch_source="deterministic",
                    patch_generated=True,
                    patch_applied=True,
                    verification=SdkBootstrapVerification(status="passed", summary="ok"),
                    preview_available=True,
                    change_request_allowed=True,
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        control_plane_module,
        "build_sdk_bootstrap_patch_from_clone",
        lambda **_: SdkBootstrapPatch(
            patch_diff="diff --git a/package.json b/package.json\n",
            attempt=SdkBootstrapPatchAttempt(
                strategy_id="javascript-next:.:src/app/layout.tsx",
                patch_source="deterministic",
                patch_generated=True,
                patch_applied=True,
                verification=SdkBootstrapVerification(status="passed", summary="ok"),
                preview_available=True,
                change_request_allowed=True,
            ),
        ),
    )

    response = client.post(
        "/control-plane/projects/project-1/sdk-bootstrap/change-request",
        json={
            "project_id": "project-1",
            "provider_repository_id": "provider-repo-1",
            "api_key_name": "Telemetry bootstrap",
            "allowed_origins": ["https://app.example.com"],
            "existing_browser_key_id": "browser-key-1",
            "existing_plaintext_key": existing_plaintext_key,
            "service_name": "billing-web",
            "environment": "production",
            "base_url": "https://stimpact.example.com",
            "branch_name": "stimpact/sdk-bootstrap-preview-existing-browser",
        },
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["browser_key"]["id"] == "browser-key-1"
    assert body["plaintext_key"] == existing_plaintext_key
    assert len(repository.project_browser_keys) == 1
    assert repository.project_browser_keys[0].allowed_origins == ["https://app.example.com"]


def test_sdk_bootstrap_preview_returns_patch_and_pr_metadata(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ADMIN_TOKEN", "super-admin-token")
    from services.sdk_bootstrap import (
        SdkBootstrapManualStep,
        SdkBootstrapPatch,
        SdkBootstrapPatchAttempt,
        SdkBootstrapPlan,
        SdkBootstrapPlannedFile,
        SdkBootstrapPreparedPreview,
        SdkBootstrapStrategy,
        SdkBootstrapVerification,
    )
    import api.routes.control_plane as control_plane_module

    app = build_test_app()
    repository = StubControlPlaneRepository()
    provider_service = StubProviderIntegrationService()
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_provider_integration_service] = lambda: provider_service
    client = TestClient(app)
    headers = {"Authorization": "Bearer super-admin-token"}

    monkeypatch.setattr(
        control_plane_module,
        "prepare_sdk_bootstrap_preview_from_clone",
        lambda **_: SdkBootstrapPreparedPreview(
            plan=SdkBootstrapPlan(
                runtime="javascript",
                warnings=[],
                recommended_strategy_id="javascript-next:.:src/app/layout.tsx",
                requires_confirmation=False,
                strategies=[
                    SdkBootstrapStrategy(
                        id="javascript-next:.:src/app/layout.tsx",
                        language="javascript",
                        framework="Next.js",
                        summary="Inject browser auto-capture into the app shell.",
                        confidence="high",
                        pr_supported=True,
                        target_subpath=".",
                        entrypoints=["src/app/layout.tsx"],
                        assumptions=["src/app/layout.tsx is the main browser shell."],
                        blockers=[],
                        planned_files=[
                            SdkBootstrapPlannedFile(
                                path="src/app/layout.tsx",
                                action="update",
                                reason="Mount the provider in the root shell.",
                            )
                        ],
                        manual_steps=[SdkBootstrapManualStep(title="Install", content="Run npm install @stimpact/sdk")],
                        install_command="npm install @stimpact/sdk",
                        package_name="@stimpact/sdk",
                        preview_snippet="import { StimpactClient } from '@stimpact/sdk';",
                        source="llm",
                        evidence=["src/app/layout.tsx", "package.json"],
                        confidence_reason="The root layout is the browser shell.",
                    )
                ],
            ),
            selected_strategy_id="javascript-next:.:src/app/layout.tsx",
            strategy=SdkBootstrapStrategy(
                id="javascript-next:.:src/app/layout.tsx",
                language="javascript",
                framework="Next.js",
                summary="Inject browser auto-capture into the app shell.",
                confidence="high",
                pr_supported=True,
                target_subpath=".",
                entrypoints=["src/app/layout.tsx"],
                assumptions=["src/app/layout.tsx is the main browser shell."],
                blockers=[],
                planned_files=[
                    SdkBootstrapPlannedFile(
                        path="src/app/layout.tsx",
                        action="update",
                        reason="Mount the provider in the root shell.",
                    )
                ],
                manual_steps=[SdkBootstrapManualStep(title="Install", content="Run npm install @stimpact/sdk")],
                install_command="npm install @stimpact/sdk",
                package_name="@stimpact/sdk",
                preview_snippet="import { StimpactClient } from '@stimpact/sdk';",
                source="llm",
                evidence=["src/app/layout.tsx", "package.json"],
                confidence_reason="The root layout is the browser shell.",
            ),
            patch=SdkBootstrapPatch(
                patch_diff="diff --git a/src/app/layout.tsx b/src/app/layout.tsx\n",
                attempt=SdkBootstrapPatchAttempt(
                    strategy_id="javascript-next:.:src/app/layout.tsx",
                    patch_source="llm",
                    patch_generated=True,
                    patch_applied=True,
                    verification=SdkBootstrapVerification(status="passed", summary="ok"),
                    preview_available=True,
                    change_request_allowed=True,
                ),
            ),
        ),
    )

    response = client.post(
        "/control-plane/projects/project-1/sdk-bootstrap/preview",
        json={
            "project_id": "project-1",
            "provider_repository_id": "provider-repo-1",
            "service_name": "billing-web",
            "environment": "production",
            "base_url": "https://stimpact.example.com",
            "strategy_id": "javascript-next:.:src/app/layout.tsx",
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["selected_strategy_id"] == "javascript-next:.:src/app/layout.tsx"
    assert body["strategy"]["framework"] == "Next.js"
    assert body["strategy"]["source"] == "llm"
    assert body["strategy"]["confidence_reason"] == "The root layout is the browser shell."
    assert body["strategy"]["evidence"] == ["src/app/layout.tsx", "package.json"]
    assert body["pull_request"]["branch_name"].startswith("stimpact/sdk-bootstrap-")
    assert body["pull_request"]["title"] == "Add Stimpact telemetry bootstrap for Next.js"
    assert body["patch_diff"].startswith("diff --git")
    assert body["run_id"]
    assert body["attempt"]["verification"]["status"] == "passed"
    assert len(body["attempts"]) >= 1


def test_sdk_bootstrap_plan_preview_returns_detected_strategies(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ADMIN_TOKEN", "super-admin-token")
    from services.sdk_bootstrap import (
        SdkBootstrapManualStep,
        SdkBootstrapPlan,
        SdkBootstrapPlannedFile,
        SdkBootstrapStrategy,
    )
    import api.routes.control_plane as control_plane_module

    app = build_test_app()
    repository = StubControlPlaneRepository()
    provider_service = StubProviderIntegrationService()
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_provider_integration_service] = lambda: provider_service
    client = TestClient(app)
    headers = {"Authorization": "Bearer super-admin-token"}

    monkeypatch.setattr(
        control_plane_module,
        "plan_sdk_bootstrap_from_clone",
        lambda **_: SdkBootstrapPlan(
            runtime="python",
            warnings=["Multiple app roots detected."],
            recommended_strategy_id="python-fastapi:backend:main.py",
            requires_confirmation=True,
            strategies=[
                SdkBootstrapStrategy(
                    id="python-fastapi:backend:main.py",
                    language="python",
                    framework="FastAPI",
                    summary="Inject request-scoped telemetry capture.",
                    confidence="high",
                    pr_supported=True,
                    target_subpath="backend",
                    entrypoints=["backend/main.py"],
                    assumptions=["backend/main.py is the primary ASGI entrypoint."],
                    blockers=[],
                    planned_files=[
                        SdkBootstrapPlannedFile(
                            path="backend/main.py",
                            action="update",
                            reason="Install middleware hook.",
                        )
                    ],
                    manual_steps=[
                        SdkBootstrapManualStep(
                            title="Install",
                            content="Run pip install stimpact-sdk",
                        )
                    ],
                    install_command="pip install stimpact-sdk",
                    package_name="stimpact-sdk",
                    preview_snippet="from stimpact_sdk import StimpactClient",
                )
            ],
        ),
    )

    response = client.post(
        "/control-plane/projects/project-1/sdk-bootstrap/plan",
        json={
            "project_id": "project-1",
            "provider_repository_id": "provider-repo-1",
            "service_name": "billing-api",
            "environment": "production",
            "base_url": "https://stimpact.example.com",
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["runtime"] == "python"
    assert body["recommended_strategy_id"] == "python-fastapi:backend:main.py"
    assert body["requires_confirmation"] is True
    assert body["warnings"] == ["Multiple app roots detected."]
    assert body["strategies"][0]["framework"] == "FastAPI"


def test_sdk_bootstrap_change_request_requires_preview_branch_name(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ADMIN_TOKEN", "super-admin-token")
    from services.sdk_bootstrap import (
        SdkBootstrapManualStep,
        SdkBootstrapPatch,
        SdkBootstrapPatchAttempt,
        SdkBootstrapPlan,
        SdkBootstrapPlannedFile,
        SdkBootstrapPreparedPreview,
        SdkBootstrapStrategy,
        SdkBootstrapVerification,
    )
    import api.routes.control_plane as control_plane_module

    app = build_test_app()
    repository = StubControlPlaneRepository()
    provider_service = StubProviderIntegrationService()
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_provider_integration_service] = lambda: provider_service
    client = TestClient(app)
    headers = {"Authorization": "Bearer super-admin-token"}

    monkeypatch.setattr(
        control_plane_module,
        "prepare_sdk_bootstrap_preview_from_clone",
        lambda **_: SdkBootstrapPreparedPreview(
            plan=SdkBootstrapPlan(
                runtime="javascript",
                warnings=[],
                recommended_strategy_id="javascript-next:.:src/app/layout.tsx",
                requires_confirmation=False,
                strategies=[
                    SdkBootstrapStrategy(
                        id="javascript-next:.:src/app/layout.tsx",
                        language="javascript",
                        framework="Next.js",
                        summary="Inject browser auto-capture into the app shell.",
                        confidence="high",
                        pr_supported=True,
                        target_subpath=".",
                        entrypoints=["src/app/layout.tsx"],
                        assumptions=[],
                        blockers=[],
                        planned_files=[
                            SdkBootstrapPlannedFile(
                                path="src/app/layout.tsx",
                                action="update",
                                reason="Mount the provider in the root shell.",
                            )
                        ],
                        manual_steps=[SdkBootstrapManualStep(title="Install", content="Run npm install @stimpact/sdk")],
                        install_command="npm install @stimpact/sdk",
                        package_name="@stimpact/sdk",
                        preview_snippet="import { StimpactClient } from '@stimpact/sdk';",
                    )
                ],
            ),
            selected_strategy_id="javascript-next:.:src/app/layout.tsx",
            strategy=SdkBootstrapStrategy(
                id="javascript-next:.:src/app/layout.tsx",
                language="javascript",
                framework="Next.js",
                summary="Inject browser auto-capture into the app shell.",
                confidence="high",
                pr_supported=True,
                target_subpath=".",
                entrypoints=["src/app/layout.tsx"],
                assumptions=[],
                blockers=[],
                planned_files=[
                    SdkBootstrapPlannedFile(
                        path="src/app/layout.tsx",
                        action="update",
                        reason="Mount the provider in the root shell.",
                    )
                ],
                manual_steps=[SdkBootstrapManualStep(title="Install", content="Run npm install @stimpact/sdk")],
                install_command="npm install @stimpact/sdk",
                package_name="@stimpact/sdk",
                preview_snippet="import { StimpactClient } from '@stimpact/sdk';",
            ),
            patch=SdkBootstrapPatch(
                patch_diff="diff --git a/src/app/layout.tsx b/src/app/layout.tsx\n",
                attempt=SdkBootstrapPatchAttempt(
                    strategy_id="javascript-next:.:src/app/layout.tsx",
                    patch_source="deterministic",
                    patch_generated=True,
                    patch_applied=True,
                    verification=SdkBootstrapVerification(status="passed", summary="ok"),
                    preview_available=True,
                    change_request_allowed=True,
                ),
            ),
        ),
    )

    response = client.post(
        "/control-plane/projects/project-1/sdk-bootstrap/change-request",
        json={
            "project_id": "project-1",
            "provider_repository_id": "provider-repo-1",
            "api_key_name": "Telemetry bootstrap",
            "service_name": "billing-web",
            "environment": "production",
            "base_url": "https://stimpact.example.com",
            "strategy_id": "javascript-next:.:src/app/layout.tsx",
        },
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "sdk_bootstrap_preview_required"


def test_sdk_bootstrap_change_request_blocks_unverified_preview(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ADMIN_TOKEN", "super-admin-token")
    from services.sdk_bootstrap import (
        SdkBootstrapManualStep,
        SdkBootstrapPatch,
        SdkBootstrapPatchAttempt,
        SdkBootstrapPlan,
        SdkBootstrapPlannedFile,
        SdkBootstrapPreparedPreview,
        SdkBootstrapStrategy,
        SdkBootstrapVerification,
    )
    import api.routes.control_plane as control_plane_module

    app = build_test_app()
    repository = StubControlPlaneRepository()
    provider_service = StubProviderIntegrationService()
    app.dependency_overrides[get_control_plane_repository] = lambda: repository
    app.dependency_overrides[get_provider_integration_service] = lambda: provider_service
    client = TestClient(app)
    headers = {"Authorization": "Bearer super-admin-token"}

    strategy = SdkBootstrapStrategy(
        id="javascript-next:.:src/app/layout.tsx",
        language="javascript",
        framework="Next.js",
        summary="Inject browser auto-capture into the app shell.",
        confidence="high",
        pr_supported=True,
        target_subpath=".",
        entrypoints=["src/app/layout.tsx"],
        assumptions=[],
        blockers=[],
        planned_files=[
            SdkBootstrapPlannedFile(
                path="src/app/layout.tsx",
                action="update",
                reason="Mount the provider in the root shell.",
            )
        ],
        manual_steps=[SdkBootstrapManualStep(title="Install", content="Run npm install @stimpact/sdk")],
        install_command="npm install @stimpact/sdk",
        package_name="@stimpact/sdk",
        preview_snippet="import { StimpactClient } from '@stimpact/sdk';",
    )
    monkeypatch.setattr(
        control_plane_module,
        "prepare_sdk_bootstrap_preview_from_clone",
        lambda **_: SdkBootstrapPreparedPreview(
            plan=SdkBootstrapPlan(
                runtime="javascript",
                warnings=[],
                recommended_strategy_id=strategy.id,
                requires_confirmation=False,
                strategies=[strategy],
            ),
            selected_strategy_id=strategy.id,
            strategy=strategy,
            patch=SdkBootstrapPatch(
                patch_diff="diff --git a/src/app/layout.tsx b/src/app/layout.tsx\n",
                attempt=SdkBootstrapPatchAttempt(
                    strategy_id=strategy.id,
                    patch_source="deterministic",
                    patch_generated=True,
                    patch_applied=True,
                    verification=SdkBootstrapVerification(
                        status="failed",
                        summary="Generated patch did not pass focused verification.",
                    ),
                    preview_available=True,
                    change_request_allowed=False,
                    failure_stage="verification",
                    failure_reason="Generated patch did not pass focused verification.",
                ),
            ),
        ),
    )

    response = client.post(
        "/control-plane/projects/project-1/sdk-bootstrap/change-request",
        json={
            "project_id": "project-1",
            "provider_repository_id": "provider-repo-1",
            "api_key_name": "Telemetry bootstrap",
            "service_name": "billing-web",
            "environment": "production",
            "base_url": "https://stimpact.example.com",
            "strategy_id": strategy.id,
            "branch_name": "stimpact/sdk-bootstrap-preview-1234",
        },
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "sdk_bootstrap_preview_verification_failed"
