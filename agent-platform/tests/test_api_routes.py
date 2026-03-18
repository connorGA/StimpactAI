from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.core.errors import register_exception_handlers
from api.events.publisher import IncidentEventPublisher
from api.routes.control_plane import (
    get_control_plane_repository,
    get_provider_integration_service,
    get_secrets_writer,
    public_router as provider_callback_router,
    router as control_plane_router,
)
from api.routes.incidents import (
    get_artifact_repository,
    get_failure_classifier,
    get_incident_repository,
    get_patch_generation_service,
    get_root_cause_analysis_service,
    get_sandbox_repository,
    get_sandbox_verification_service,
    router as incidents_router,
)
from api.routes.telemetry import (
    get_incident_event_publisher,
    get_outbox_signaler,
    get_telemetry_repository,
    router as telemetry_router,
)
from models.async_job import AsyncJobStatus
from models.control_plane import (
    ProviderIntegrationRecord,
    ProviderIntegrationStatus,
    ProviderKind,
    ProviderRepositoryRecord,
    RepoProfileRecord,
    RuntimeKind,
    SecretBackend,
    SecretRefRecord,
)
from models.failure_classification import FailureCategory, FailureClassification
from models.incident import IncidentEventRecord, IncidentRecord, IncidentSeverity, IncidentStatus
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
from services.provider_integration_service import GitHubCallbackPreview, GitLabCallbackResult


def build_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(telemetry_router)
    app.include_router(incidents_router)
    app.include_router(control_plane_router)
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


class StubFailureClassifier:
    def classify(
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


class StubControlPlaneRepository:
    def __init__(self) -> None:
        now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
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
            metadata={},
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

    async def create_secret_ref(self, **kwargs) -> SecretRefRecord:
        assert kwargs["project_id"] == "project-1"
        return self.secret_ref

    async def list_secret_refs(self, project_id: str) -> list[SecretRefRecord]:
        assert project_id == "project-1"
        return [self.secret_ref]

    async def create_provider_integration(self, **kwargs) -> ProviderIntegrationRecord:
        assert kwargs["provider"] is ProviderKind.GITHUB
        return self.provider_integration

    async def list_provider_integrations(self) -> list[ProviderIntegrationRecord]:
        return [self.provider_integration]

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

    async def list_repo_profile_secret_refs(self, repo_profile_id: str) -> list[SecretRefRecord]:
        assert repo_profile_id == self.repo_profile.id
        return [self.secret_ref]

    async def list_repo_profiles(self, project_id: str) -> list[RepoProfileRecord]:
        assert project_id == "project-1"
        return [self.repo_profile]


class StubSecretsWriter:
    def put_secret(self, *, project_id: str, label: str, value: str) -> str:
        assert project_id == "project-1"
        assert label == "OPENAI_API_KEY"
        assert value == "super-secret-value"
        return "arn:aws:secretsmanager:us-east-1:123456789012:secret:stimpact/project-1/OPENAI_API_KEY"


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


def test_ingest_error_returns_accepted_response_and_signals_outbox() -> None:
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


def test_get_missing_incident_returns_not_found() -> None:
    app = build_test_app()
    repository = StubIncidentRepository()
    app.dependency_overrides[get_incident_repository] = lambda: repository

    client = TestClient(app)
    response = client.get("/incidents/missing-incident")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "incident_not_found"


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
    app.dependency_overrides[get_sandbox_verification_service] = StubSandboxVerificationService

    client = TestClient(app)
    response = client.post("/incidents/incident-1/sandbox-run", params={"event_limit": 20})

    assert response.status_code == 202
    body = response.json()
    assert body["sandbox_run"]["incident_id"] == "incident-1"
    assert body["async_job_id"] == "job-1"


def test_list_incident_sandbox_runs_returns_history() -> None:
    app = build_test_app()
    app.dependency_overrides[get_sandbox_verification_service] = StubSandboxVerificationService

    client = TestClient(app)
    response = client.get("/incidents/incident-1/sandbox-runs", params={"limit": 20})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "succeeded"


def test_get_incident_sandbox_run_detail_returns_steps_and_artifacts() -> None:
    app = build_test_app()
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
    assert body["external_ref"].startswith("arn:aws:secretsmanager:")


def test_create_repo_profile_returns_profile_with_secret_refs() -> None:
    app = build_test_app()
    app.dependency_overrides[get_control_plane_repository] = StubControlPlaneRepository

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
