from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from api.schemas.autonomous import AutonomousRunCreateRequest
from harness.autonomous.events import PersistentAutonomousRunEventStream
from harness.autonomous.storage import AutonomousRunArtifactStore
from harness.schemas.autonomous import AutonomousRunStatus
from models.control_plane import (
    AutonomyMode,
    ProjectPolicyRecord,
    ProjectServiceRecord,
    ProjectServiceRoutingHints,
    ProjectServiceType,
    ProviderKind,
    ProviderRepositoryRecord,
    RepoProfileRecord,
    RuntimeKind,
)
from models.incident import IncidentProcessingResult, IncidentRecord, IncidentSeverity, IncidentStatus, TelemetryRecord
from services.autonomous_runs import AutonomousRunService
from services.incident_creation import IncidentCreationService
from shared.events.incident_events import IncidentEventType
from shared.types.telemetry import Environment


class AcceptanceIncidentRepository:
    def __init__(self, telemetry: TelemetryRecord) -> None:
        self.telemetry = telemetry
        self.incident: IncidentRecord | None = None

    async def get_telemetry(self, telemetry_id: str) -> TelemetryRecord:
        assert telemetry_id == self.telemetry.id
        return self.telemetry

    async def attach_to_incident(
        self,
        *,
        telemetry: TelemetryRecord,
        event_type: str,
        event_payload: dict[str, object],
        severity,
        title: str,
        project_service_id: str | None = None,
        repo_profile_id: str | None = None,
    ) -> IncidentProcessingResult:
        assert telemetry.id == self.telemetry.id
        assert event_type == IncidentEventType.TELEMETRY_RECEIVED.value
        assert event_payload["telemetry_id"] == telemetry.id
        self.incident = IncidentRecord(
            id="incident-acceptance-1",
            project_id=telemetry.project_id,
            project_service_id=project_service_id,
            repo_profile_id=repo_profile_id,
            fingerprint=telemetry.fingerprint,
            service=telemetry.service,
            environment=telemetry.environment,
            title=title,
            status=IncidentStatus.OPEN,
            severity=severity,
            first_seen_at=telemetry.occurred_at,
            last_seen_at=telemetry.occurred_at,
            event_count=1,
            latest_telemetry_id=telemetry.id,
            created_at=telemetry.received_at,
            updated_at=telemetry.received_at,
        )
        return IncidentProcessingResult(
            incident_id=self.incident.id,
            created_new_incident=True,
            attached_telemetry=True,
            severity=severity,
            event_count=1,
        )

    async def get_incident(self, incident_id: str) -> IncidentRecord | None:
        if self.incident is None:
            return None
        if incident_id == self.incident.id:
            return self.incident
        return None


class AcceptanceControlPlaneRepository:
    def __init__(
        self,
        *,
        project_service: ProjectServiceRecord,
        repo_profile: RepoProfileRecord,
        provider_repository: ProviderRepositoryRecord,
        project_policy: ProjectPolicyRecord,
    ) -> None:
        self.project_service = project_service
        self.repo_profile = repo_profile
        self.provider_repository = provider_repository
        self.project_policy = project_policy

    async def resolve_project_service(
        self,
        *,
        project_id: str,
        service_name: str,
        stacktrace: str | None = None,
    ) -> ProjectServiceRecord | None:
        assert project_id == self.project_service.project_id
        _ = stacktrace
        if service_name == self.project_service.slug:
            return self.project_service
        return None

    async def get_project_service(self, service_id: str) -> ProjectServiceRecord | None:
        if service_id == self.project_service.id:
            return self.project_service
        return None

    async def list_project_service_dependencies(self, service_id: str):
        _ = service_id
        return []

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

    async def get_or_create_project_policy(self, project_id: str) -> ProjectPolicyRecord | None:
        if project_id == self.project_policy.project_id:
            return self.project_policy
        return None


@pytest.mark.asyncio
async def test_incident_telemetry_can_launch_an_autonomous_run(tmp_path: Path) -> None:
    now = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    telemetry = TelemetryRecord(
        id="telemetry-acceptance-1",
        project_id="project-1",
        environment=Environment.PRODUCTION,
        service="billing-api",
        error_message="Checkout timeout while waiting for the payment gateway lock.",
        stacktrace='Traceback:\n  File "/workspace/repo/app.py", line 22, in charge_customer\nTimeoutError',
        fingerprint="fp-acceptance-1",
        request_payload={"method": "POST", "path": "/api/charge"},
        response_payload={"status_code": 503},
        commit_sha="abc123def",
        occurred_at=now,
        received_at=now,
    )
    project_service = ProjectServiceRecord(
        id="service-1",
        project_id="project-1",
        name="Billing API",
        slug="billing-api",
        service_type=ProjectServiceType.API,
        repo_profile_id="repo-profile-1",
        owner="payments",
        deploy_target="staging",
        routing_hints=ProjectServiceRoutingHints(service_names=["billing-api"], path_prefixes=["/api/charge"]),
        startup_priority=10,
        sandbox_healthcheck_command="python healthcheck.py",
        sandbox_healthcheck_url=None,
        active=True,
        created_at=now,
        updated_at=now,
    )
    repo_profile = RepoProfileRecord(
        id="repo-profile-1",
        project_id="project-1",
        provider_repository_id="provider-repo-1",
        runtime_kind=RuntimeKind.PYTHON,
        base_image="python:3.12",
        install_command="pip install -r requirements.txt",
        startup_commands=["python app.py"],
        reproduce_command="pytest tests/test_charge.py::test_timeout",
        verify_command="pytest tests/test_charge.py::test_timeout_fixed",
        success_criteria="The timeout no longer reproduces and checkout verification passes.",
        network_allowlist=["pypi.org"],
        active=True,
        created_at=now,
        updated_at=now,
    )
    provider_repository = ProviderRepositoryRecord(
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
    project_policy = ProjectPolicyRecord(
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
    incident_repository = AcceptanceIncidentRepository(telemetry)
    control_plane_repository = AcceptanceControlPlaneRepository(
        project_service=project_service,
        repo_profile=repo_profile,
        provider_repository=provider_repository,
        project_policy=project_policy,
    )
    creation_service = IncidentCreationService(
        repository=incident_repository,
        control_plane_repository=control_plane_repository,
    )

    result = await creation_service.process_telemetry_received(
        {
            "event_type": IncidentEventType.TELEMETRY_RECEIVED.value,
            "telemetry_id": telemetry.id,
            "project_id": telemetry.project_id,
            "fingerprint": telemetry.fingerprint,
            "occurred_at": telemetry.occurred_at.isoformat(),
            "payload": {},
        }
    )

    assert result.created_new_incident is True
    assert result.severity is IncidentSeverity.CRITICAL
    assert incident_repository.incident is not None
    assert incident_repository.incident.project_service_id == "service-1"
    assert incident_repository.incident.repo_profile_id == "repo-profile-1"

    artifact_store = AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts")
    run_service = AutonomousRunService(
        incident_repository,
        async_job_repository=None,
        autonomous_repository=None,
        control_plane_repository=control_plane_repository,
        patch_repository=None,
        repository_root=tmp_path,
        artifact_store=artifact_store,
        event_stream=PersistentAutonomousRunEventStream(artifact_store=artifact_store),
    )

    detail = await run_service.start_run(
        incident_repository.incident.id,
        AutonomousRunCreateRequest(
            execution_mode="repair_only",
            repository_root=str(tmp_path),
            benchmark_scenario_id="acceptance-charge-timeout",
            benchmark_bug_class="checkout-timeout",
        ),
    )

    assert detail.run.status is AutonomousRunStatus.QUEUED
    assert detail.run.project_id == "project-1"
    assert detail.run.service_name == "billing-api"
    assert detail.run.environment == "production"
    assert detail.run.latest_telemetry_id == telemetry.id
    assert detail.run.latest_telemetry_commit_sha == "abc123def"
    assert detail.run.provider_repository_owner == "acme"
    assert detail.run.provider_repository_name == "billing-api"
    assert detail.run.runtime_kind == "python"
    assert detail.run.install_command == "pip install -r requirements.txt"
    assert detail.run.reproduce_command == "pytest tests/test_charge.py::test_timeout"
    assert detail.run.verify_command == "pytest tests/test_charge.py::test_timeout_fixed"
    assert detail.run.success_criteria == "The timeout no longer reproduces and checkout verification passes."
