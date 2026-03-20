from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.schemas.autonomous import AutonomousRunApprovalRequest, AutonomousRunCreateRequest
from harness.autonomous.runner import AutonomousRepairRunner
from harness.autonomous.events import PersistentAutonomousRunEventStream
from harness.autonomous.storage import AutonomousRunArtifactStore
from harness.schemas.autonomous import (
    AutonomousApprovalStatus,
    AutonomousExecutionMode,
    AutonomousPromotionStatus,
    AutonomousRunPhase,
    AutonomousRunStatus,
    AutonomousToolFailure,
    AutonomousToolFailureClass,
    AutonomousVerificationEvidence,
)
from harness.schemas.verification import VerificationKind
from models.control_plane import ProviderKind, ProviderRepositoryRecord, RepoProfileRecord, RuntimeKind
from models.incident import IncidentRecord, IncidentSeverity, IncidentStatus
from models.sandbox import SandboxRunRecord, SandboxRunStatus
from services.autonomous_runs import AutonomousRunService
from shared.types.telemetry import Environment


class StubIncidentRepository:
    def __init__(self, incident: IncidentRecord) -> None:
        self.incident = incident

    async def get_incident(self, incident_id: str) -> IncidentRecord | None:
        if incident_id == self.incident.id:
            return self.incident
        return None


class StubAsyncJobRepository:
    def __init__(self) -> None:
        self.jobs: list[object] = []

    async def create_job(self, *, job_type, payload, dedupe_key, status):
        job = type(
            "AsyncJob",
            (),
            {
                "id": f"job-{len(self.jobs) + 1}",
                "job_type": job_type,
                "payload": payload,
                "dedupe_key": dedupe_key,
                "status": status,
                "attempts": 1,
            },
        )()
        self.jobs.append(job)
        return job


class StubAutonomousRunRepository:
    def __init__(self) -> None:
        self.records: dict[str, object] = {}
        self.attempt_calls: list[dict[str, object]] = []

    async def create_run(self, **kwargs):
        record = SimpleNamespace(
            id=kwargs["run"].id,
            incident_id=kwargs["incident_id"],
            repo_profile_id=kwargs["repo_profile_id"],
            async_job_id=kwargs["async_job_id"],
            feature_seeds=kwargs["feature_seeds"],
            initializer_summary=kwargs["initializer_summary"],
            max_steps=kwargs["max_steps"],
            run=kwargs["run"],
            outcome=kwargs["outcome"],
        )
        self.records[record.id] = record
        return record

    async def update_run(self, run_id: str, **kwargs):
        existing = self.records[run_id]
        payload = dict(existing.__dict__)
        payload.update(
            {
                "async_job_id": kwargs["async_job_id"],
                "repo_profile_id": kwargs["repo_profile_id"],
                "run": kwargs["run"],
                "outcome": kwargs["outcome"],
            }
        )
        updated = SimpleNamespace(**payload)
        self.records[run_id] = updated
        return updated

    async def list_runs(self, incident_id: str):
        return [
            record
            for record in self.records.values()
            if record.incident_id == incident_id
        ]

    async def get_run(self, run_id: str):
        return self.records.get(run_id)

    async def find_runs_by_patch_run(self, patch_run_id: str):
        return [
            record
            for record in self.records.values()
            if record.run.patch_run_id == patch_run_id
        ]

    async def create_attempt(self, **kwargs) -> None:
        self.attempt_calls.append(kwargs)


class StubRetryRunner:
    def __init__(self, event_stream, *, failure_class: AutonomousToolFailureClass, include_last_failure: bool = True) -> None:
        self._event_stream = event_stream
        self.failure_class = failure_class
        self.include_last_failure = include_last_failure
        self.continue_calls = 0
        self.retry_contexts: list[dict[str, object]] = []

    def bootstrap_run(self, **kwargs):
        raise AssertionError("bootstrap_run should be handled by the real runner in this test")

    def ensure_sessions(self, **kwargs):
        run_id = kwargs["run_id"]
        snapshot = self._event_stream.get_snapshot(run_id)
        run = snapshot.run
        if run.initializer_session_id is not None and run.coding_session_id is not None:
            return snapshot
        updated = run.model_copy(
            update={
                "initializer_session_id": run.initializer_session_id or "retry-initializer",
                "coding_session_id": run.coding_session_id or "retry-coding",
            }
        )
        self._event_stream.upsert_run(updated)
        return self._event_stream.get_snapshot(run_id)

    async def continue_run(self, *, run_id: str, decision_engine, max_steps: int = 12):
        _ = (decision_engine, max_steps)
        self.continue_calls += 1
        snapshot = self._event_stream.get_snapshot(run_id)
        run = snapshot.run
        if self.continue_calls == 1:
            loop_state = run.loop_state.model_copy(
                update={
                    "step_index": 3,
                    "checkpoint_ref": "stimpact-checkpoint/autonomous-baseline",
                    "last_tool_name": "view_at_line",
                    "recent_tool_names": ["checkpoint", "run_command", "view_at_line"],
                    "recovery_attempts": 2,
                    "last_failure": (
                        AutonomousToolFailure(
                            tool_name="view_at_line",
                            failure_class=self.failure_class,
                            message="Input should be less than or equal to 100.",
                            hint="Use a smaller page size.",
                            signature="view_at_line:validation:page-size",
                            repeated_count=1,
                        )
                        if self.include_last_failure
                        else None
                    ),
                }
            )
            failed = run.model_copy(
                update={
                    "status": AutonomousRunStatus.FAILED,
                    "phase": AutonomousRunPhase.FAILED,
                    "last_error": (
                        "Tool execution failed: 1 validation error for FileViewRequest\n"
                        "page_size\n"
                        "  Input should be less than or equal to 100"
                        if not self.include_last_failure
                        else "Tool execution failed."
                    ),
                    "loop_state": loop_state,
                }
            )
            self._event_stream.upsert_run(failed)
            return self._event_stream.get_snapshot(run_id)

        succeeded = run.model_copy(
            update={
                "status": AutonomousRunStatus.SUCCEEDED,
                "phase": AutonomousRunPhase.COMPLETED,
                "latest_verification": AutonomousVerificationEvidence(
                    source="tool",
                    kind="integration",
                    summary="Verification passed.",
                    passed=True,
                    command="pytest -q",
                    recorded_at=datetime.now(UTC),
                    metadata={"attempt": self.continue_calls},
                ),
                "loop_state": run.loop_state.model_copy(
                    update={
                        "step_index": 4,
                        "checkpoint_ref": run.loop_state.checkpoint_ref or "stimpact-checkpoint/autonomous-baseline",
                        "last_tool_name": "run_command",
                        "last_tool_ok": True,
                    }
                ),
            }
        )
        self._event_stream.upsert_run(succeeded)
        return self._event_stream.get_snapshot(run_id)

    def prepare_for_retry(self, *, run_id: str, retry_context: dict[str, object] | None = None):
        self.retry_contexts.append(retry_context or {})
        snapshot = self._event_stream.get_snapshot(run_id)
        run = snapshot.run
        reset = run.model_copy(
            update={
                "status": AutonomousRunStatus.QUEUED,
                "phase": AutonomousRunPhase.CODING,
                "initializer_session_id": None,
                "coding_session_id": None,
                "last_error": None,
                "latest_verification": None,
                "patch_run_id": None,
                "sandbox_run_id": None,
                "loop_state": run.loop_state.model_copy(
                    update={
                        "step_index": 0,
                        "recovery_attempts": 0,
                        "consecutive_failures": 0,
                        "stagnation_count": 0,
                        "last_tool_name": "discard_failed_work",
                        "recent_tool_names": [],
                        "last_tool_ok": True,
                        "last_tool_result": {"retry_context": retry_context or {}},
                        "last_failure": None,
                        "recent_failure_signatures": [],
                    }
                ),
            }
        )
        self._event_stream.upsert_run(reset)
        return self._event_stream.get_snapshot(run_id)


class StubControlPlaneRepository:
    def __init__(self, repo_profile: RepoProfileRecord, provider_repository: ProviderRepositoryRecord) -> None:
        self.repo_profile = repo_profile
        self.provider_repository = provider_repository

    async def get_active_repo_profile(self, project_id: str):
        if project_id == self.repo_profile.project_id:
            return self.repo_profile
        return None

    async def get_repo_profile(self, repo_profile_id: str):
        if repo_profile_id == self.repo_profile.id:
            return self.repo_profile
        return None

    async def get_provider_repository(self, provider_repository_id: str):
        if provider_repository_id == self.provider_repository.id:
            return self.provider_repository
        return None


class StubMissingRepoProfileControlPlaneRepository:
    async def get_active_repo_profile(self, project_id: str):
        _ = project_id
        return None


class StubPatchRepository:
    async def get_patch_run(self, patch_run_id: str):
        return SimpleNamespace(
            id=patch_run_id,
            unified_diff=(
                "diff --git a/app.py b/app.py\n"
                "--- a/app.py\n"
                "+++ b/app.py\n"
                "@@ -1 +1 @@\n"
                "-print('broken')\n"
                "+print('fixed')\n"
            ),
        )


class StubProviderIntegrationService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def propose_patch_writeback(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            branch_name=kwargs["branch_name"],
            commit_sha="deadbeef",
            change_request_url="https://github.com/acme/billing-api/pull/99",
            reference_id="99",
            mergeable=True,
        )


def _build_incident_and_profile(now: datetime) -> tuple[IncidentRecord, RepoProfileRecord, ProviderRepositoryRecord]:
    incident = IncidentRecord(
        id="incident-1",
        project_id="project-1",
        fingerprint="fp-1",
        service="billing-api",
        environment=Environment.PRODUCTION,
        title="billing-api: Database timeout",
        status=IncidentStatus.OPEN,
        severity=IncidentSeverity.HIGH,
        first_seen_at=now,
        last_seen_at=now,
        event_count=4,
        latest_telemetry_id="telemetry-1",
        created_at=now,
        updated_at=now,
    )
    repo_profile = RepoProfileRecord(
        id="profile-1",
        project_id="project-1",
        provider_repository_id="provider-repo-1",
        runtime_kind=RuntimeKind.PYTHON,
        base_image=None,
        install_command="pip install -r requirements.txt",
        startup_commands=["python app.py"],
        reproduce_command="pytest tests/test_billing.py::test_timeout",
        verify_command="pytest tests/test_billing.py::test_timeout_fixed",
        success_criteria="Billing timeout no longer reproduces.",
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
    return incident, repo_profile, provider_repository


@pytest.mark.asyncio
async def test_autonomous_run_service_supports_approval_verification_and_promotion(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    incident = IncidentRecord(
        id="incident-1",
        project_id="project-1",
        fingerprint="fp-1",
        service="billing-api",
        environment=Environment.PRODUCTION,
        title="billing-api: Database timeout",
        status=IncidentStatus.OPEN,
        severity=IncidentSeverity.CRITICAL,
        first_seen_at=now,
        last_seen_at=now,
        event_count=4,
        latest_telemetry_id="telemetry-1",
        created_at=now,
        updated_at=now,
    )
    repo_profile = RepoProfileRecord(
        id="profile-1",
        project_id="project-1",
        provider_repository_id="provider-repo-1",
        runtime_kind=RuntimeKind.PYTHON,
        base_image=None,
        install_command="pip install -r requirements.txt",
        startup_commands=["python app.py"],
        reproduce_command="pytest tests/test_billing.py::test_timeout",
        verify_command="pytest tests/test_billing.py::test_timeout_fixed",
        success_criteria="Billing timeout no longer reproduces.",
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
    artifact_store = AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts")
    provider_service = StubProviderIntegrationService()
    service = AutonomousRunService(
        StubIncidentRepository(incident),
        async_job_repository=StubAsyncJobRepository(),
        autonomous_repository=StubAutonomousRunRepository(),
        control_plane_repository=StubControlPlaneRepository(repo_profile, provider_repository),
        patch_repository=StubPatchRepository(),
        repository_root=tmp_path,
        artifact_store=artifact_store,
        event_stream=PersistentAutonomousRunEventStream(artifact_store=artifact_store),
        provider_integration_service=provider_service,
    )

    detail = await service.start_run(
        "incident-1",
        AutonomousRunCreateRequest(
            execution_mode=AutonomousExecutionMode.REPAIR_AND_PROPOSE,
            repository_root=str(tmp_path),
            benchmark_scenario_id="status-429",
            benchmark_bug_class="retry-policy-429",
        ),
    )

    assert detail.run.status is AutonomousRunStatus.QUEUED
    assert detail.run.approval_status is AutonomousApprovalStatus.PENDING
    assert detail.run.async_job_id is None
    assert detail.run.policy.requires_human_approval is True
    assert detail.run.benchmark_scenario_id == "status-429"
    assert detail.run.benchmark_bug_class == "retry-policy-429"

    approved = await service.approve_run(
        "incident-1",
        detail.run.id,
        AutonomousRunApprovalRequest(approval_status=AutonomousApprovalStatus.APPROVED),
    )

    assert approved.run.approval_status is AutonomousApprovalStatus.APPROVED
    assert approved.run.async_job_id == "job-1"

    run_with_patch = approved.run.model_copy(update={"patch_run_id": "patch-1"})
    service._event_stream.upsert_run(run_with_patch)  # noqa: SLF001
    await service._autonomous_repository.update_run(  # type: ignore[union-attr]  # noqa: SLF001
        run_with_patch.id,
        async_job_id=run_with_patch.async_job_id,
        repo_profile_id=run_with_patch.repo_profile_id,
        run=run_with_patch,
        outcome=None,
    )

    await service.record_sandbox_result(
        SandboxRunRecord(
            id="sandbox-1",
            incident_id="incident-1",
            patch_run_id="patch-1",
            repo_profile_id="profile-1",
            async_job_id="job-2",
            status=SandboxRunStatus.SUCCEEDED,
            executor_backend="kubernetes",
            external_job_id="stimpact-sandbox-1",
            install_command="pip install -r requirements.txt",
            reproduce_command="pytest tests/test_billing.py::test_timeout",
            verify_command="pytest tests/test_billing.py::test_timeout_fixed",
            reproduction_succeeded=True,
            patch_applied=True,
            verification_succeeded=True,
            summary="Sandbox verified the autonomous repair.",
            execution_log="sandbox log",
            created_at=now,
            updated_at=now,
        )
    )

    ready = await service.get_run_detail("incident-1", detail.run.id)
    assert ready.run.sandbox_run_id == "sandbox-1"
    assert ready.run.promotion_status is AutonomousPromotionStatus.READY

    promoted = await service.promote_run("incident-1", detail.run.id)

    assert promoted.run.promotion_status is AutonomousPromotionStatus.PROPOSED
    assert promoted.run.promotion_branch_name == f"stimpact/fix/incident-1-{detail.run.id[:8]}"
    assert promoted.run.promotion_url == "https://github.com/acme/billing-api/pull/99"
    assert provider_service.calls[0]["provider_repository_id"] == "provider-repo-1"
    assert "Fix incident incident-1" in str(provider_service.calls[0]["commit_message"])


@pytest.mark.asyncio
async def test_autonomous_run_service_does_not_queue_without_active_repo_profile(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    incident = IncidentRecord(
        id="incident-1",
        project_id="project-1",
        fingerprint="fp-1",
        service="billing-api",
        environment=Environment.PRODUCTION,
        title="billing-api: Database timeout",
        status=IncidentStatus.OPEN,
        severity=IncidentSeverity.HIGH,
        first_seen_at=now,
        last_seen_at=now,
        event_count=4,
        latest_telemetry_id="telemetry-1",
        created_at=now,
        updated_at=now,
    )
    artifact_store = AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts")
    async_jobs = StubAsyncJobRepository()
    service = AutonomousRunService(
        StubIncidentRepository(incident),
        async_job_repository=async_jobs,
        autonomous_repository=StubAutonomousRunRepository(),
        control_plane_repository=StubMissingRepoProfileControlPlaneRepository(),
        repository_root=tmp_path,
        artifact_store=artifact_store,
        event_stream=PersistentAutonomousRunEventStream(artifact_store=artifact_store),
    )

    detail = await service.start_run(
        "incident-1",
        AutonomousRunCreateRequest(
            execution_mode=AutonomousExecutionMode.REPAIR_ONLY,
            repository_root=str(tmp_path),
        ),
    )

    assert detail.run.async_job_id is None
    assert detail.run.policy.auto_run_allowed is False
    assert async_jobs.jobs == []


@pytest.mark.asyncio
async def test_autonomous_run_service_retries_retryable_failed_run(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    incident, repo_profile, provider_repository = _build_incident_and_profile(now)
    artifact_store = AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts")
    event_stream = PersistentAutonomousRunEventStream(artifact_store=artifact_store)
    async_jobs = StubAsyncJobRepository()
    repository = StubAutonomousRunRepository()
    service = AutonomousRunService(
        StubIncidentRepository(incident),
        async_job_repository=async_jobs,
        autonomous_repository=repository,
        control_plane_repository=StubControlPlaneRepository(repo_profile, provider_repository),
        repository_root=tmp_path,
        artifact_store=artifact_store,
        event_stream=event_stream,
        runner=AutonomousRepairRunner(event_stream=event_stream),
        decision_engine_factory=lambda: object(),  # type: ignore[arg-type]
    )

    detail = await service.start_run(
        "incident-1",
        AutonomousRunCreateRequest(
            execution_mode=AutonomousExecutionMode.REPAIR_ONLY,
            repository_root=str(tmp_path),
        ),
    )
    retry_runner = StubRetryRunner(
        event_stream,
        failure_class=AutonomousToolFailureClass.VALIDATION,
        include_last_failure=False,
    )
    service._runner = retry_runner  # noqa: SLF001

    final_detail = await service.process_async_job(async_jobs.jobs[0])

    assert retry_runner.continue_calls == 2
    assert len(retry_runner.retry_contexts) == 1
    assert retry_runner.retry_contexts[0]["previous_failure_class"] == AutonomousToolFailureClass.VALIDATION.value
    assert final_detail.run.status is AutonomousRunStatus.SUCCEEDED
    assert final_detail.run.phase is AutonomousRunPhase.COMPLETED
    assert [call["attempt_number"] for call in repository.attempt_calls] == [1, 1, 2, 2]
    assert repository.records[detail.run.id].run.status is AutonomousRunStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_autonomous_run_service_does_not_retry_non_retryable_failed_run(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    incident, repo_profile, provider_repository = _build_incident_and_profile(now)
    artifact_store = AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts")
    event_stream = PersistentAutonomousRunEventStream(artifact_store=artifact_store)
    async_jobs = StubAsyncJobRepository()
    repository = StubAutonomousRunRepository()
    service = AutonomousRunService(
        StubIncidentRepository(incident),
        async_job_repository=async_jobs,
        autonomous_repository=repository,
        control_plane_repository=StubControlPlaneRepository(repo_profile, provider_repository),
        repository_root=tmp_path,
        artifact_store=artifact_store,
        event_stream=event_stream,
        runner=AutonomousRepairRunner(event_stream=event_stream),
        decision_engine_factory=lambda: object(),  # type: ignore[arg-type]
    )

    await service.start_run(
        "incident-1",
        AutonomousRunCreateRequest(
            execution_mode=AutonomousExecutionMode.REPAIR_ONLY,
            repository_root=str(tmp_path),
        ),
    )
    retry_runner = StubRetryRunner(event_stream, failure_class=AutonomousToolFailureClass.VERIFICATION)
    service._runner = retry_runner  # noqa: SLF001

    final_detail = await service.process_async_job(async_jobs.jobs[0])

    assert retry_runner.continue_calls == 1
    assert retry_runner.retry_contexts == []
    assert final_detail.run.status is AutonomousRunStatus.FAILED
    assert [call["attempt_number"] for call in repository.attempt_calls] == [1, 1]


@pytest.mark.asyncio
async def test_autonomous_run_service_derived_feature_seed_tracks_repo_commands(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    incident = IncidentRecord(
        id="incident-1",
        project_id="project-1",
        fingerprint="fp-1",
        service="billing-api",
        environment=Environment.PRODUCTION,
        title="billing-api: Database timeout",
        status=IncidentStatus.OPEN,
        severity=IncidentSeverity.HIGH,
        first_seen_at=now,
        last_seen_at=now,
        event_count=4,
        latest_telemetry_id="telemetry-1",
        created_at=now,
        updated_at=now,
    )
    repo_profile = RepoProfileRecord(
        id="profile-1",
        project_id="project-1",
        provider_repository_id="provider-repo-1",
        runtime_kind=RuntimeKind.PYTHON,
        base_image=None,
        install_command="pip install -r requirements.txt",
        startup_commands=[],
        reproduce_command="pytest tests/test_billing.py::test_timeout",
        verify_command="pytest tests/test_billing.py::test_timeout_fixed",
        success_criteria="Billing timeout no longer reproduces.",
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
    repository = StubAutonomousRunRepository()
    service = AutonomousRunService(
        StubIncidentRepository(incident),
        async_job_repository=StubAsyncJobRepository(),
        autonomous_repository=repository,
        control_plane_repository=StubControlPlaneRepository(repo_profile, provider_repository),
        repository_root=tmp_path,
        artifact_store=AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts"),
        event_stream=PersistentAutonomousRunEventStream(
            artifact_store=AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts-stream")
        ),
    )

    detail = await service.start_run(
        "incident-1",
        AutonomousRunCreateRequest(
            execution_mode=AutonomousExecutionMode.REPAIR_ONLY,
            repository_root=str(tmp_path),
        ),
    )

    record = repository.records[detail.run.id]
    assert record.feature_seeds[0].reproduction_command == "pytest tests/test_billing.py::test_timeout"
    assert record.feature_seeds[0].verification_command == "pytest tests/test_billing.py::test_timeout_fixed"
    assert record.feature_seeds[0].browser_required is False
    assert detail.run.policy.require_browser_verification is False


@pytest.mark.asyncio
async def test_autonomous_run_service_aligns_browser_policy_with_browser_capability(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    incident = IncidentRecord(
        id="incident-1",
        project_id="project-1",
        fingerprint="fp-1",
        service="billing-api",
        environment=Environment.PRODUCTION,
        title="billing-api: Checkout broken",
        status=IncidentStatus.OPEN,
        severity=IncidentSeverity.HIGH,
        first_seen_at=now,
        last_seen_at=now,
        event_count=4,
        latest_telemetry_id="telemetry-1",
        created_at=now,
        updated_at=now,
    )
    repo_profile = RepoProfileRecord(
        id="profile-1",
        project_id="project-1",
        provider_repository_id="provider-repo-1",
        runtime_kind=RuntimeKind.PYTHON,
        base_image=None,
        install_command="pip install -r requirements.txt",
        startup_commands=["python app.py"],
        reproduce_command="pytest tests/test_checkout.py::test_checkout_fails",
        verify_command="pytest tests/test_checkout.py::test_checkout_fixed",
        success_criteria="Checkout succeeds after the repair.",
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
    repository = StubAutonomousRunRepository()
    service = AutonomousRunService(
        StubIncidentRepository(incident),
        async_job_repository=StubAsyncJobRepository(),
        autonomous_repository=repository,
        control_plane_repository=StubControlPlaneRepository(repo_profile, provider_repository),
        repository_root=tmp_path,
        artifact_store=AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts"),
        event_stream=PersistentAutonomousRunEventStream(
            artifact_store=AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts-stream")
        ),
    )

    detail = await service.start_run(
        "incident-1",
        AutonomousRunCreateRequest(
            execution_mode=AutonomousExecutionMode.REPAIR_ONLY,
            repository_root=str(tmp_path),
        ),
    )

    record = repository.records[detail.run.id]
    assert detail.run.policy.require_browser_verification is True
    assert record.feature_seeds[0].browser_required is True
    assert record.feature_seeds[0].required_verification == [VerificationKind.BROWSER]


@pytest.mark.asyncio
async def test_autonomous_run_service_prefers_newer_persisted_snapshot_over_stale_in_memory_state(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    incident = IncidentRecord(
        id="incident-1",
        project_id="project-1",
        fingerprint="fp-1",
        service="billing-api",
        environment=Environment.STAGING,
        title="billing-api: Database timeout",
        status=IncidentStatus.OPEN,
        severity=IncidentSeverity.HIGH,
        first_seen_at=now,
        last_seen_at=now,
        event_count=1,
        latest_telemetry_id="telemetry-1",
        created_at=now,
        updated_at=now,
    )
    artifact_store = AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts")
    repository = StubAutonomousRunRepository()
    event_stream = PersistentAutonomousRunEventStream(artifact_store=artifact_store)
    service = AutonomousRunService(
        StubIncidentRepository(incident),
        async_job_repository=StubAsyncJobRepository(),
        autonomous_repository=repository,
        control_plane_repository=StubMissingRepoProfileControlPlaneRepository(),
        repository_root=tmp_path,
        artifact_store=artifact_store,
        event_stream=event_stream,
    )

    detail = await service.start_run(
        "incident-1",
        AutonomousRunCreateRequest(
            execution_mode=AutonomousExecutionMode.REPAIR_ONLY,
            repository_root=str(tmp_path),
        ),
    )

    persisted_run = detail.run.model_copy(
        update={
            "status": AutonomousRunStatus.SUCCEEDED,
            "phase": AutonomousRunPhase.COMPLETED,
            "updated_at": detail.run.updated_at + timedelta(minutes=1),
        }
    )
    event_stream.artifact_store.persist_snapshot(
        event_stream.get_snapshot(detail.run.id).model_copy(update={"run": persisted_run})
    )
    await repository.update_run(
        detail.run.id,
        async_job_id=detail.run.async_job_id,
        repo_profile_id=detail.run.repo_profile_id,
        run=persisted_run,
        outcome=None,
    )

    refreshed = service.get_run_detail_sync("incident-1", detail.run.id)
    assert refreshed.run.status is AutonomousRunStatus.SUCCEEDED
    assert refreshed.run.phase is AutonomousRunPhase.COMPLETED
