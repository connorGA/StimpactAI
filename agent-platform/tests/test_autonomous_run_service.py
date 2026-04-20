from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.schemas.autonomous import AutonomousRunApprovalRequest, AutonomousRunCreateRequest
from harness.autonomous.runner import AutonomousRepairRunner
from harness.autonomous.events import PersistentAutonomousRunEventStream
from harness.git_ops.checkpoints import GitCheckpointManager
from harness.autonomous.storage import AutonomousRunArtifactStore
from harness.schemas.autonomous import (
    AutonomousApprovalStatus,
    AutonomousExecutionMode,
    AutonomousPromotionStatus,
    AutonomousRunPhase,
    AutonomousRunStatus,
    AutonomousSolutionReview,
    AutonomousSolutionReviewRisk,
    AutonomousSolutionReviewRiskSeverity,
    AutonomousSolutionReviewVerdict,
    AutonomousToolFailure,
    AutonomousToolFailureClass,
    AutonomousVerificationEvidence,
)
from harness.schemas.verification import VerificationKind
from models.async_job import AsyncJobStatus, AsyncJobType
from models.control_plane import (
    AutonomyMode,
    ProjectPolicyRecord,
    ProviderKind,
    ProviderRepositoryRecord,
    RepoProfileRecord,
    RuntimeKind,
)
from models.incident import IncidentRecord, IncidentSeverity, IncidentStatus, TelemetryRecord
from models.patch import PatchProposal, PatchRunRecord, PatchRunStatus
from models.sandbox import SandboxRunRecord, SandboxRunStatus
from services.autonomous_runs import AutonomousRunService
from shared.types.telemetry import Environment


class StubIncidentRepository:
    def __init__(self, incident: IncidentRecord) -> None:
        self.incident = incident
        self.status_updates: list[IncidentStatus] = []
        now = datetime.now(UTC)
        self.telemetry = TelemetryRecord(
            id=incident.latest_telemetry_id,
            project_id=incident.project_id,
            environment=incident.environment,
            service=incident.service,
            error_message="Database timeout while waiting for checkout lock.",
            stacktrace='Traceback:\n  File "/workspace/repo/app.py", line 10, in handle_request\nTimeoutError',
            fingerprint=incident.fingerprint,
            request_payload={"method": "POST", "path": "/checkout"},
            response_payload={"status_code": 503},
            commit_sha="deadbeef",
            occurred_at=now,
            received_at=now,
        )

    async def get_incident(self, incident_id: str) -> IncidentRecord | None:
        if incident_id == self.incident.id:
            return self.incident
        return None

    async def get_telemetry(self, telemetry_id: str) -> TelemetryRecord:
        if telemetry_id != self.telemetry.id:
            raise AssertionError(f"unknown telemetry id {telemetry_id}")
        return self.telemetry

    async def list_incident_events(self, incident_id: str, *, limit: int = 50) -> list[object]:
        _ = limit
        if incident_id != self.incident.id:
            return []
        return []

    async def mark_resolved_by_autonomous_agent(self, incident_id: str) -> IncidentRecord | None:
        if incident_id != self.incident.id:
            return None
        return self.incident

    async def update_incident_status(
        self,
        incident_id: str,
        new_status: IncidentStatus,
        *,
        resolution_source: str | None = None,
    ) -> IncidentRecord:
        _ = resolution_source
        if incident_id != self.incident.id:
            raise AssertionError(f"unknown incident id {incident_id}")
        self.status_updates.append(new_status)
        self.incident = self.incident.model_copy(update={"status": new_status})
        return self.incident


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
    def __init__(
        self,
        event_stream,
        *,
        failure_class: AutonomousToolFailureClass,
        include_last_failure: bool = True,
        first_error: str | None = None,
        first_verification: AutonomousVerificationEvidence | None = None,
    ) -> None:
        self._event_stream = event_stream
        self.failure_class = failure_class
        self.include_last_failure = include_last_failure
        self.first_error = first_error
        self.first_verification = first_verification
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

    async def continue_run(self, *, run_id: str, decision_engine, max_steps: int = 20):
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
                        self.first_error
                        if self.first_error is not None
                        else (
                            "Tool execution failed: 1 validation error for FileViewRequest\n"
                            "page_size\n"
                            "  Input should be less than or equal to 100"
                            if not self.include_last_failure
                            else "Tool execution failed."
                        )
                    ),
                    "latest_verification": self.first_verification,
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


class StubPersistedRetryStateRunner:
    def __init__(self, event_stream) -> None:
        self._event_stream = event_stream
        self.checked_reset_state = False

    def bootstrap_run(self, **kwargs):
        raise AssertionError("bootstrap_run should not be called in this test")

    def ensure_sessions(self, **kwargs):
        snapshot = self._event_stream.get_snapshot(kwargs["run_id"])
        run = snapshot.run
        assert run.status is AutonomousRunStatus.QUEUED
        assert run.phase is AutonomousRunPhase.CODING
        assert run.initializer_session_id is None
        assert run.coding_session_id is None
        assert run.latest_verification is None
        self.checked_reset_state = True
        updated = run.model_copy(
            update={
                "initializer_session_id": "retry-initializer",
                "coding_session_id": "retry-coding",
            }
        )
        self._event_stream.upsert_run(updated)
        return self._event_stream.get_snapshot(run.id)

    async def continue_run(self, *, run_id: str, decision_engine, max_steps: int = 20):
        _ = (decision_engine, max_steps)
        snapshot = self._event_stream.get_snapshot(run_id)
        run = snapshot.run
        failed = run.model_copy(
            update={
                "status": AutonomousRunStatus.FAILED,
                "phase": AutonomousRunPhase.FAILED,
                "last_error": "Verification still failing after retry.",
                "latest_verification": AutonomousVerificationEvidence(
                    source="tool",
                    kind="integration",
                    summary="Command exited with status 1.",
                    passed=False,
                    command="npm run build",
                    recorded_at=run.updated_at + timedelta(seconds=1),
                    metadata={},
                ),
                "loop_state": run.loop_state.model_copy(
                    update={
                        "last_failure": AutonomousToolFailure(
                            tool_name="run_command",
                            failure_class=AutonomousToolFailureClass.VERIFICATION,
                            message="Verification still failing after retry.",
                            hint="Fix the verification error before trying again.",
                            signature="run_command:verification:retry-state",
                            repeated_count=1,
                        ),
                    }
                ),
            }
        )
        self._event_stream.upsert_run(failed)
        return self._event_stream.get_snapshot(run_id)


class StubControlPlaneRepository:
    def __init__(
        self,
        repo_profile: RepoProfileRecord,
        provider_repository: ProviderRepositoryRecord,
        *,
        project_policy: ProjectPolicyRecord | None = None,
    ) -> None:
        self.repo_profile = repo_profile
        self.provider_repository = provider_repository
        self.project_policy = project_policy

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

    async def get_or_create_project_policy(self, project_id: str):
        if self.project_policy is not None and project_id == self.project_policy.project_id:
            return self.project_policy
        return None


class StubMissingRepoProfileControlPlaneRepository:
    async def get_active_repo_profile(self, project_id: str):
        _ = project_id
        return None


class StubPatchRepository:
    def __init__(self) -> None:
        self.created_runs: list[PatchRunRecord] = []

    async def get_patch_run(self, patch_run_id: str):
        return SimpleNamespace(
            id=patch_run_id,
            patch_summary="Fix billing timeout handling.",
            rationale="Retry the downstream call with a shorter lock window.",
            target_files=[SimpleNamespace(path="app.py", reason="Repair logic changed.")],
            verification_steps=["pytest tests/test_billing.py::test_timeout_fixed"],
            diff_line_count=2,
            file_count=1,
            unified_diff=(
                "diff --git a/app.py b/app.py\n"
                "--- a/app.py\n"
                "+++ b/app.py\n"
                "@@ -1 +1 @@\n"
                "-print('broken')\n"
                "+print('fixed')\n"
            ),
        )

    async def create_patch_run(self, **kwargs):
        now = datetime.now(UTC)
        proposal: PatchProposal = kwargs["proposal"]
        record = PatchRunRecord(
            id="patch-generated-1",
            incident_id=kwargs["incident_id"],
            repo_profile_id=kwargs["repo_profile_id"],
            status=PatchRunStatus.GENERATED,
            patch_summary=proposal.patch_summary,
            rationale=proposal.rationale,
            target_files=proposal.target_files,
            unified_diff=proposal.unified_diff,
            verification_steps=proposal.verification_steps,
            confidence=proposal.confidence,
            model_name=kwargs["model_name"],
            based_on_commit_sha=kwargs["based_on_commit_sha"],
            diff_line_count=kwargs["diff_line_count"],
            file_count=kwargs["file_count"],
            created_at=now,
            updated_at=now,
        )
        self.created_runs.append(record)
        return record


class StubSolutionReviewService:
    def __init__(self, review: AutonomousSolutionReview) -> None:
        self.review = review
        self.calls: list[dict[str, object]] = []

    async def review_solution(self, **kwargs) -> AutonomousSolutionReview:
        self.calls.append(kwargs)
        return self.review


class StubPostVerificationRetryRunner:
    def __init__(self, event_stream) -> None:
        self._event_stream = event_stream
        self.retry_contexts: list[dict[str, object]] = []

    def prepare_for_retry(self, *, run_id: str, retry_context: dict[str, object] | None = None):
        self.retry_contexts.append(retry_context or {})
        snapshot = self._event_stream.get_snapshot(run_id)
        run = snapshot.run
        retried_run = run.model_copy(
            update={
                "status": AutonomousRunStatus.QUEUED,
                "phase": AutonomousRunPhase.CODING,
                "last_error": None,
                "latest_verification": None,
                "latest_review": None,
                "patch_run_id": None,
                "sandbox_run_id": None,
                "promotion_status": AutonomousPromotionStatus.NOT_REQUESTED,
                "loop_state": run.loop_state.model_copy(
                    update={
                        "last_retry_context": retry_context or {},
                    }
                ),
            }
        )
        self._event_stream.upsert_run(retried_run)
        return self._event_stream.get_snapshot(run_id)


class StubSandboxVerificationService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def queue_sandbox_run(self, incident_id: str, **kwargs):
        self.calls.append({"incident_id": incident_id, **kwargs})
        now = datetime.now(UTC)
        run = SandboxRunRecord(
            id="sandbox-generated-1",
            incident_id=incident_id,
            patch_run_id=str(kwargs["patch_run_id"]),
            repo_profile_id="profile-1",
            async_job_id="job-sandbox-1",
            status=SandboxRunStatus.QUEUED,
            executor_backend="local",
            external_job_id=None,
            install_command="npm install",
            reproduce_command="npm test",
            verify_command="npm run build",
            reproduction_succeeded=False,
            patch_applied=False,
            verification_succeeded=False,
            summary="queued",
            execution_log="",
            created_at=now,
            updated_at=now,
        )
        return run, SimpleNamespace(id="job-sandbox-1")


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


def _build_project_policy(
    now: datetime,
    *,
    autonomy_mode: AutonomyMode,
    allow_production_writes: bool = True,
    approved_services: list[str] | None = None,
    restrict_to_approved_services: bool = False,
) -> ProjectPolicyRecord:
    return ProjectPolicyRecord(
        project_id="project-1",
        autonomy_mode=autonomy_mode,
        require_human_approval=autonomy_mode is not AutonomyMode.AUTONOMOUS,
        allow_production_writes=allow_production_writes,
        allow_low_risk_autonomy=autonomy_mode is AutonomyMode.AUTONOMOUS,
        block_during_active_deploys=False,
        restrict_to_approved_services=restrict_to_approved_services,
        require_rollback_plan=False,
        require_post_action_verification=False,
        approved_services=approved_services or [],
        failure_classifier_enabled=True,
        root_cause_enabled=True,
        patch_planner_enabled=True,
        runbook_executor_enabled=True,
        created_at=now,
        updated_at=now,
    )


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
    approving_reviewer = StubSolutionReviewService(
        AutonomousSolutionReview(
            verdict=AutonomousSolutionReviewVerdict.APPROVE,
            summary="The patch looks appropriately scoped.",
            risks=[],
            requested_checks=[],
            feedback_for_repair=[],
            reviewed_at=now,
            model_name="gpt-test",
        )
    )
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
        solution_review_service=approving_reviewer,
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
    assert detail.run.async_job_id == "job-1"
    assert detail.run.policy.requires_human_approval is True
    assert detail.run.benchmark_scenario_id == "status-429"
    assert detail.run.benchmark_bug_class == "retry-policy-429"
    assert detail.run.project_id == "project-1"
    assert detail.run.incident_title == "billing-api: Database timeout"
    assert detail.run.incident_fingerprint == "fp-1"
    assert detail.run.service_name == "billing-api"
    assert detail.run.environment == "production"
    assert detail.run.latest_telemetry_id == "telemetry-1"
    assert detail.run.latest_telemetry_commit_sha == "deadbeef"
    assert detail.run.provider_repository_owner == "acme"
    assert detail.run.provider_repository_name == "billing-api"
    assert detail.run.runtime_kind == "python"
    assert detail.run.reproduce_command == "pytest tests/test_billing.py::test_timeout"
    assert detail.run.verify_command == "pytest tests/test_billing.py::test_timeout_fixed"
    assert detail.run.network_allowlist == ["pypi.org"]

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

    promoted = await service.get_run_detail("incident-1", detail.run.id)
    assert promoted.run.sandbox_run_id == "sandbox-1"
    assert promoted.run.promotion_status is AutonomousPromotionStatus.PROPOSED
    assert promoted.run.promotion_branch_name == f"stimpact/fix/incident-1-{detail.run.id[:8]}"
    assert promoted.run.promotion_url == "https://github.com/acme/billing-api/pull/99"
    assert provider_service.calls[0]["provider_repository_id"] == "provider-repo-1"
    assert "Fix incident incident-1" in str(provider_service.calls[0]["commit_message"])


@pytest.mark.asyncio
async def test_autonomous_run_service_excludes_lockfile_only_install_drift_from_sandbox_patch(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    incident, repo_profile, provider_repository = _build_incident_and_profile(now)
    patch_repository = StubPatchRepository()
    sandbox_service = StubSandboxVerificationService()
    artifact_store = AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts")
    service = AutonomousRunService(
        StubIncidentRepository(incident),
        async_job_repository=StubAsyncJobRepository(),
        autonomous_repository=StubAutonomousRunRepository(),
        control_plane_repository=StubControlPlaneRepository(repo_profile, provider_repository),
        patch_repository=patch_repository,
        sandbox_verification_service=sandbox_service,
        repository_root=tmp_path,
        artifact_store=artifact_store,
        event_stream=PersistentAutonomousRunEventStream(artifact_store=artifact_store),
    )

    (tmp_path / "server").mkdir(parents=True, exist_ok=True)
    tracked_file = tmp_path / "server" / "routes.ts"
    tracked_file.write_text(
        "export async function registerRoutes(app: Express): Promise<Server> {\n"
        "  // Internal secured endpoints for webhook operations\n"
        "  // These endpoints require the INTERNAL_WEBHOOK_SECRET header\n"
        "  return {} as Server;\n"
        "}\n",
        encoding="utf-8",
    )
    package_json = tmp_path / "package.json"
    package_json.write_text(
        '{\n'
        '  "name": "demo",\n'
        '  "dependencies": {\n'
        '    "@stimpact/sdk": "^0.1.0"\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text('{"name":"demo","lockfileVersion":3}\n', encoding="utf-8")
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "add", "server/routes.ts", "package.json", "package-lock.json"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=tmp_path, check=True, capture_output=True, text=True)
    checkpoint = GitCheckpointManager().create_checkpoint(
        repository_root=str(tmp_path),
        label="autonomous-baseline",
    )

    detail = await service.start_run(
        "incident-1",
        AutonomousRunCreateRequest(
            execution_mode=AutonomousExecutionMode.REPAIR_AND_PROPOSE,
            repository_root=str(tmp_path),
        ),
    )

    tracked_file.write_text(
        "export async function registerRoutes(app: Express): Promise<Server> {\n"
        "  app.post(\"/api/stimpact-token\", async (_req, res) => {\n"
        "    return res.status(200).json({ ok: true });\n"
        "  });\n"
        "\n"
        "  // Internal secured endpoints for webhook operations\n"
        "  // These endpoints require the INTERNAL_WEBHOOK_SECRET header\n"
        "  return {} as Server;\n"
        "}\n",
        encoding="utf-8",
    )
    lockfile.write_text('{"name":"demo","lockfileVersion":3,"packages":{"":{}}}\n', encoding="utf-8")

    updated_run = detail.run.model_copy(
        update={
            "status": AutonomousRunStatus.SUCCEEDED,
            "phase": AutonomousRunPhase.COMPLETED,
            "loop_state": detail.run.loop_state.model_copy(update={"checkpoint_ref": checkpoint.checkpoint.tag_name}),
        }
    )
    service._event_stream.upsert_run(updated_run)  # noqa: SLF001

    snapshot = service._event_stream.get_snapshot(updated_run.id)  # noqa: SLF001
    processed = await service._postprocess_completed_run(snapshot)  # noqa: SLF001

    expected_diff = GitCheckpointManager().diff_since_checkpoint(
        repository_root=str(tmp_path),
        checkpoint_ref=checkpoint.checkpoint.tag_name,
        paths=["server/routes.ts"],
    ).diff
    assert expected_diff is not None
    assert len(patch_repository.created_runs) == 1
    assert patch_repository.created_runs[0].unified_diff == expected_diff.patch
    assert patch_repository.created_runs[0].file_count == 1
    assert [target.path for target in patch_repository.created_runs[0].target_files] == [
        "server/routes.ts",
    ]
    assert len(sandbox_service.calls) == 1
    assert sandbox_service.calls[0]["patch_run_id"] == patch_repository.created_runs[0].id
    assert processed.run.patch_run_id == patch_repository.created_runs[0].id
    assert processed.run.sandbox_run_id == "sandbox-generated-1"


@pytest.mark.asyncio
async def test_autonomous_run_service_preserves_lockfile_when_manifest_changes(tmp_path: Path) -> None:
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    incident, repo_profile, provider_repository = _build_incident_and_profile(now)
    patch_repository = StubPatchRepository()
    sandbox_service = StubSandboxVerificationService()
    artifact_store = AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts")
    service = AutonomousRunService(
        StubIncidentRepository(incident),
        async_job_repository=StubAsyncJobRepository(),
        autonomous_repository=StubAutonomousRunRepository(),
        control_plane_repository=StubControlPlaneRepository(repo_profile, provider_repository),
        patch_repository=patch_repository,
        sandbox_verification_service=sandbox_service,
        repository_root=tmp_path,
        artifact_store=artifact_store,
        event_stream=PersistentAutonomousRunEventStream(artifact_store=artifact_store),
    )

    package_json = tmp_path / "package.json"
    package_json.write_text('{"name":"demo","dependencies":{"react":"^18.0.0"}}\n', encoding="utf-8")
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text('{"name":"demo","lockfileVersion":3}\n', encoding="utf-8")
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "package.json", "package-lock.json"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=tmp_path, check=True, capture_output=True, text=True)
    checkpoint = GitCheckpointManager().create_checkpoint(
        repository_root=str(tmp_path),
        label="autonomous-baseline",
    )

    detail = await service.start_run(
        "incident-1",
        AutonomousRunCreateRequest(
            execution_mode=AutonomousExecutionMode.REPAIR_AND_PROPOSE,
            repository_root=str(tmp_path),
        ),
    )

    package_json.write_text(
        '{"name":"demo","dependencies":{"react":"^18.0.0","@stimpact/sdk":"^0.1.0"}}\n',
        encoding="utf-8",
    )
    lockfile.write_text('{"name":"demo","lockfileVersion":3,"packages":{"":{"dependencies":{"@stimpact/sdk":"^0.1.0"}}}}\n', encoding="utf-8")

    updated_run = detail.run.model_copy(
        update={
            "status": AutonomousRunStatus.SUCCEEDED,
            "phase": AutonomousRunPhase.COMPLETED,
            "loop_state": detail.run.loop_state.model_copy(update={"checkpoint_ref": checkpoint.checkpoint.tag_name}),
        }
    )
    service._event_stream.upsert_run(updated_run)  # noqa: SLF001

    snapshot = service._event_stream.get_snapshot(updated_run.id)  # noqa: SLF001
    processed = await service._postprocess_completed_run(snapshot)  # noqa: SLF001

    expected_diff = GitCheckpointManager().diff_since_checkpoint(
        repository_root=str(tmp_path),
        checkpoint_ref=checkpoint.checkpoint.tag_name,
        paths=["package.json", "package-lock.json"],
    ).diff
    assert expected_diff is not None
    assert len(patch_repository.created_runs) == 1
    assert patch_repository.created_runs[0].unified_diff == expected_diff.patch
    assert patch_repository.created_runs[0].file_count == 2
    assert [target.path for target in patch_repository.created_runs[0].target_files] == [
        "package-lock.json",
        "package.json",
    ]
    assert len(sandbox_service.calls) == 1
    assert sandbox_service.calls[0]["patch_run_id"] == patch_repository.created_runs[0].id
    assert processed.run.patch_run_id == patch_repository.created_runs[0].id


@pytest.mark.asyncio
async def test_autonomous_run_service_recommend_mode_disables_writeback(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    incident, repo_profile, provider_repository = _build_incident_and_profile(now)
    async_jobs = StubAsyncJobRepository()
    service = AutonomousRunService(
        StubIncidentRepository(incident),
        async_job_repository=async_jobs,
        autonomous_repository=StubAutonomousRunRepository(),
        control_plane_repository=StubControlPlaneRepository(
            repo_profile,
            provider_repository,
            project_policy=_build_project_policy(now, autonomy_mode=AutonomyMode.RECOMMEND),
        ),
        repository_root=tmp_path,
        artifact_store=AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts"),
        event_stream=PersistentAutonomousRunEventStream(
            artifact_store=AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts-stream")
        ),
    )

    detail = await service.start_run(
        "incident-1",
        AutonomousRunCreateRequest(
            execution_mode=AutonomousExecutionMode.REPAIR_AND_PROPOSE,
            repository_root=str(tmp_path),
        ),
    )

    assert detail.run.approval_status is AutonomousApprovalStatus.PENDING
    assert detail.run.async_job_id == "job-1"
    assert detail.run.policy.requires_human_approval is True
    assert detail.run.policy.allow_writeback is False


@pytest.mark.asyncio
async def test_autonomous_run_service_autonomous_mode_queues_without_manual_approval(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    incident, repo_profile, provider_repository = _build_incident_and_profile(now)
    async_jobs = StubAsyncJobRepository()
    service = AutonomousRunService(
        StubIncidentRepository(incident),
        async_job_repository=async_jobs,
        autonomous_repository=StubAutonomousRunRepository(),
        control_plane_repository=StubControlPlaneRepository(
            repo_profile,
            provider_repository,
            project_policy=_build_project_policy(now, autonomy_mode=AutonomyMode.AUTONOMOUS),
        ),
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

    assert detail.run.approval_status is AutonomousApprovalStatus.NOT_REQUIRED
    assert detail.run.policy.requires_human_approval is False
    assert detail.run.async_job_id == "job-1"
    assert len(async_jobs.jobs) == 1


@pytest.mark.asyncio
async def test_autonomous_run_service_observe_mode_stays_non_runnable_after_approval(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    incident, repo_profile, provider_repository = _build_incident_and_profile(now)
    async_jobs = StubAsyncJobRepository()
    service = AutonomousRunService(
        StubIncidentRepository(incident),
        async_job_repository=async_jobs,
        autonomous_repository=StubAutonomousRunRepository(),
        control_plane_repository=StubControlPlaneRepository(
            repo_profile,
            provider_repository,
            project_policy=_build_project_policy(now, autonomy_mode=AutonomyMode.OBSERVE),
        ),
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

    assert detail.run.approval_status is AutonomousApprovalStatus.PENDING
    assert detail.run.policy.auto_run_allowed is False
    assert detail.run.async_job_id is None

    approved = await service.approve_run(
        "incident-1",
        detail.run.id,
        AutonomousRunApprovalRequest(approval_status=AutonomousApprovalStatus.APPROVED),
    )

    assert approved.run.approval_status is AutonomousApprovalStatus.APPROVED
    assert approved.run.async_job_id is None
    assert async_jobs.jobs == []


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
async def test_autonomous_run_service_retries_patch_apply_failure(
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
    retry_runner = StubRetryRunner(
        event_stream,
        failure_class=AutonomousToolFailureClass.UNKNOWN,
        include_last_failure=False,
        first_error="Sandbox reproduced the incident but failed to apply the generated patch.",
        first_verification=AutonomousVerificationEvidence(
            source="sandbox",
            kind="sandbox",
            summary="Sandbox reproduced the incident but failed to apply the generated patch.",
            passed=False,
            command="npm run build",
            recorded_at=now,
            metadata={"patch_applied": False, "reproduction_succeeded": True},
        ),
    )
    service._runner = retry_runner  # noqa: SLF001

    final_detail = await service.process_async_job(async_jobs.jobs[0])

    assert retry_runner.continue_calls == 2
    assert len(retry_runner.retry_contexts) == 1
    assert retry_runner.retry_contexts[0]["retry_driver"] == "patch_apply_recovery"
    assert retry_runner.retry_contexts[0]["previous_patch_applied"] is False
    assert retry_runner.retry_contexts[0]["previous_reproduction_succeeded"] is True
    assert final_detail.run.status is AutonomousRunStatus.SUCCEEDED


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
async def test_autonomous_run_service_retries_when_completion_lacks_durable_diff(
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
    retry_runner = StubRetryRunner(
        event_stream,
        failure_class=AutonomousToolFailureClass.UNKNOWN,
        include_last_failure=False,
        first_error=(
            "Autonomous repair cannot complete without producing a code change "
            "relative to the baseline checkpoint."
        ),
    )
    service._runner = retry_runner  # noqa: SLF001

    final_detail = await service.process_async_job(async_jobs.jobs[0])

    assert retry_runner.continue_calls == 2
    assert len(retry_runner.retry_contexts) == 1
    assert (
        retry_runner.retry_contexts[0]["previous_failure_class"]
        == AutonomousToolFailureClass.STAGNATION.value
    )
    assert final_detail.run.status is AutonomousRunStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_autonomous_run_service_does_not_retry_repository_setup_failure(
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
    retry_runner = StubRetryRunner(
        event_stream,
        failure_class=AutonomousToolFailureClass.UNKNOWN,
        include_last_failure=False,
        first_error="Repository root does not exist for sandbox execution.",
        first_verification=AutonomousVerificationEvidence(
            source="sandbox",
            kind="sandbox",
            summary="Repository root does not exist for sandbox execution.",
            passed=False,
            command="npm run build",
            recorded_at=now,
            metadata={"patch_applied": False, "reproduction_succeeded": False},
        ),
    )
    service._runner = retry_runner  # noqa: SLF001

    final_detail = await service.process_async_job(async_jobs.jobs[0])

    assert retry_runner.continue_calls == 1
    assert retry_runner.retry_contexts == []
    assert final_detail.run.status is AutonomousRunStatus.FAILED


@pytest.mark.asyncio
async def test_approve_run_auto_promotes_when_verified_run_is_already_ready(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    incident, repo_profile, provider_repository = _build_incident_and_profile(now)
    repository = StubAutonomousRunRepository()
    provider_service = StubProviderIntegrationService()
    artifact_store = AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts")
    service = AutonomousRunService(
        StubIncidentRepository(incident),
        async_job_repository=StubAsyncJobRepository(),
        autonomous_repository=repository,
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
        ),
    )

    ready_run = detail.run.model_copy(
        update={
            "status": AutonomousRunStatus.SUCCEEDED,
            "phase": AutonomousRunPhase.COMPLETED,
            "approval_status": AutonomousApprovalStatus.PENDING,
            "promotion_status": AutonomousPromotionStatus.READY,
            "patch_run_id": "patch-1",
            "sandbox_run_id": "sandbox-1",
        }
    )
    service._event_stream.upsert_run(ready_run)  # noqa: SLF001
    await repository.update_run(
        ready_run.id,
        async_job_id=ready_run.async_job_id,
        repo_profile_id=ready_run.repo_profile_id,
        run=ready_run,
        outcome=None,
    )

    approved = await service.approve_run(
        "incident-1",
        ready_run.id,
        AutonomousRunApprovalRequest(approval_status=AutonomousApprovalStatus.APPROVED),
    )

    assert approved.run.approval_status is AutonomousApprovalStatus.APPROVED
    assert approved.run.promotion_status is AutonomousPromotionStatus.PROPOSED
    assert approved.run.promotion_url == "https://github.com/acme/billing-api/pull/99"
    assert provider_service.calls


@pytest.mark.asyncio
async def test_autonomous_run_service_reopens_acknowledged_incident_on_start(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    incident, repo_profile, provider_repository = _build_incident_and_profile(now)
    incident = incident.model_copy(update={"status": IncidentStatus.ACKNOWLEDGED})
    repository = StubIncidentRepository(incident)
    artifact_store = AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts")
    event_stream = PersistentAutonomousRunEventStream(artifact_store=artifact_store)
    service = AutonomousRunService(
        repository,
        async_job_repository=StubAsyncJobRepository(),
        autonomous_repository=StubAutonomousRunRepository(),
        control_plane_repository=StubControlPlaneRepository(repo_profile, provider_repository),
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

    assert repository.status_updates == [IncidentStatus.OPEN]
    assert repository.incident.status is IncidentStatus.OPEN
    assert detail.run.incident_id == "incident-1"


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


@pytest.mark.asyncio
async def test_process_async_job_prefers_persisted_retry_state_over_stale_artifact_snapshot(
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
    initial_event_stream = PersistentAutonomousRunEventStream(artifact_store=artifact_store)
    initial_service = AutonomousRunService(
        StubIncidentRepository(incident),
        async_job_repository=StubAsyncJobRepository(),
        autonomous_repository=repository,
        control_plane_repository=StubMissingRepoProfileControlPlaneRepository(),
        repository_root=tmp_path,
        artifact_store=artifact_store,
        event_stream=initial_event_stream,
    )

    detail = await initial_service.start_run(
        "incident-1",
        AutonomousRunCreateRequest(
            execution_mode=AutonomousExecutionMode.REPAIR_ONLY,
            repository_root=str(tmp_path),
        ),
    )

    stale_success_run = detail.run.model_copy(
        update={
            "status": AutonomousRunStatus.SUCCEEDED,
            "phase": AutonomousRunPhase.COMPLETED,
            "initializer_session_id": "stale-initializer",
            "coding_session_id": "stale-coding",
            "latest_verification": AutonomousVerificationEvidence(
                source="tool",
                kind="integration",
                summary="Verification passed.",
                passed=True,
                command="npm run build",
                recorded_at=detail.run.updated_at + timedelta(minutes=1),
                metadata={"attempt": 1},
            ),
            "updated_at": detail.run.updated_at + timedelta(minutes=1),
        }
    )
    initial_event_stream.upsert_run(stale_success_run)

    retry_ready_run = stale_success_run.model_copy(
        update={
            "status": AutonomousRunStatus.QUEUED,
            "phase": AutonomousRunPhase.CODING,
            "async_job_id": "job-retry",
            "initializer_session_id": None,
            "coding_session_id": None,
            "last_error": None,
            "latest_verification": None,
            "updated_at": stale_success_run.updated_at + timedelta(seconds=1),
        }
    )
    await repository.update_run(
        detail.run.id,
        async_job_id="job-retry",
        repo_profile_id=detail.run.repo_profile_id,
        run=retry_ready_run,
        outcome=None,
    )

    retry_event_stream = PersistentAutonomousRunEventStream(artifact_store=artifact_store)
    retry_runner = StubPersistedRetryStateRunner(retry_event_stream)
    retry_service = AutonomousRunService(
        StubIncidentRepository(incident),
        async_job_repository=StubAsyncJobRepository(),
        autonomous_repository=repository,
        control_plane_repository=StubMissingRepoProfileControlPlaneRepository(),
        repository_root=tmp_path,
        artifact_store=artifact_store,
        event_stream=retry_event_stream,
        runner=retry_runner,
        decision_engine_factory=lambda: object(),  # type: ignore[arg-type]
    )

    job = SimpleNamespace(
        id="job-retry",
        job_type=AsyncJobType.AUTONOMOUS_REPAIR,
        payload={"incident_id": "incident-1", "autonomous_run_id": detail.run.id},
        status=AsyncJobStatus.QUEUED,
    )

    final_detail = await retry_service.process_async_job(job)

    assert retry_runner.checked_reset_state is True
    assert final_detail.run.status is AutonomousRunStatus.FAILED
    assert final_detail.run.last_error == "Verification still failing after retry."


@pytest.mark.asyncio
async def test_autonomous_run_service_applies_adaptive_policy_and_step_budgets(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    incident, repo_profile, provider_repository = _build_incident_and_profile(now)
    artifact_store = AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts")
    service = AutonomousRunService(
        StubIncidentRepository(incident),
        async_job_repository=StubAsyncJobRepository(),
        autonomous_repository=StubAutonomousRunRepository(),
        control_plane_repository=StubControlPlaneRepository(repo_profile, provider_repository),
        patch_repository=StubPatchRepository(),
        repository_root=tmp_path,
        artifact_store=artifact_store,
        event_stream=PersistentAutonomousRunEventStream(artifact_store=artifact_store),
    )

    detail = await service.start_run(
        "incident-1",
        AutonomousRunCreateRequest(
            execution_mode=AutonomousExecutionMode.REPAIR_AND_PROPOSE,
            repository_root=str(tmp_path),
            max_steps=20,
        ),
    )

    assert detail.run.policy.max_repair_attempts >= 3
    assert detail.run.policy.max_retry_budget >= 3
    assert detail.run.loop_state.max_steps >= 32


@pytest.mark.asyncio
async def test_autonomous_run_service_retry_context_includes_diff_and_review_memory(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    incident, repo_profile, provider_repository = _build_incident_and_profile(now)
    patch_repository = StubPatchRepository()
    artifact_store = AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts")
    service = AutonomousRunService(
        StubIncidentRepository(incident),
        async_job_repository=StubAsyncJobRepository(),
        autonomous_repository=StubAutonomousRunRepository(),
        control_plane_repository=StubControlPlaneRepository(repo_profile, provider_repository),
        patch_repository=patch_repository,
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
    run = detail.run.model_copy(
        update={
            "patch_run_id": "patch-1",
            "last_error": "Reviewer requested a narrower patch.",
            "latest_verification": AutonomousVerificationEvidence(
                source="sandbox",
                kind="sandbox",
                summary="Patch passed verification, but follow-up review flagged risk.",
                passed=False,
                command="pytest tests/test_billing.py::test_timeout_fixed",
                recorded_at=now,
                metadata={"patch_applied": True, "reproduction_succeeded": True},
            ),
            "latest_review": AutonomousSolutionReview(
                verdict=AutonomousSolutionReviewVerdict.NEEDS_CHANGES,
                summary="The patch may affect unrelated checkout paths.",
                risks=[
                    AutonomousSolutionReviewRisk(
                        area="checkout flow",
                        severity=AutonomousSolutionReviewRiskSeverity.MEDIUM,
                        reasoning="The diff broadens retry logic beyond the failing path.",
                    )
                ],
                requested_checks=["pytest tests/test_checkout.py"],
                feedback_for_repair=["Limit the retry branch to the checkout timeout path only."],
                reviewed_at=now,
                model_name="gpt-test",
            ),
            "loop_state": detail.run.loop_state.model_copy(
                update={
                    "repair_attempt_count": 1,
                    "last_retry_context": {"retry_driver": "sandbox_recovery"},
                }
            ),
        }
    )

    retry_context = await service._build_retry_context(  # noqa: SLF001
        run,
        next_attempt_number=2,
        sandbox_excerpt="sandbox output excerpt",
    )

    assert retry_context["previous_diff_fingerprint"] == {
        "patch_run_id": "patch-1",
        "file_count": 1,
        "diff_line_count": 2,
        "target_files": ["app.py"],
    }
    assert retry_context["previous_review_summary"] == "The patch may affect unrelated checkout paths."
    assert retry_context["review_feedback_for_repair"] == [
        "Limit the retry branch to the checkout timeout path only."
    ]
    assert retry_context["previous_sandbox_excerpt"] == "sandbox output excerpt"


@pytest.mark.asyncio
async def test_autonomous_run_service_retries_after_reviewer_requests_changes(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    incident, repo_profile, provider_repository = _build_incident_and_profile(now)
    async_jobs = StubAsyncJobRepository()
    repository = StubAutonomousRunRepository()
    patch_repository = StubPatchRepository()
    artifact_store = AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts")
    event_stream = PersistentAutonomousRunEventStream(artifact_store=artifact_store)
    reviewer = StubSolutionReviewService(
        AutonomousSolutionReview(
            verdict=AutonomousSolutionReviewVerdict.NEEDS_CHANGES,
            summary="The fix should be narrowed to the incident path before promotion.",
            risks=[
                AutonomousSolutionReviewRisk(
                    area="billing-api",
                    severity=AutonomousSolutionReviewRiskSeverity.MEDIUM,
                    reasoning="The current diff appears broader than the failing timeout path.",
                )
            ],
            requested_checks=["pytest tests/test_billing.py::test_timeout_fixed"],
            feedback_for_repair=["Scope the retry logic to the checkout timeout code path only."],
            reviewed_at=now,
            model_name="gpt-test",
        )
    )
    service = AutonomousRunService(
        StubIncidentRepository(incident),
        async_job_repository=async_jobs,
        autonomous_repository=repository,
        control_plane_repository=StubControlPlaneRepository(repo_profile, provider_repository),
        patch_repository=patch_repository,
        repository_root=tmp_path,
        artifact_store=artifact_store,
        event_stream=event_stream,
        solution_review_service=reviewer,
    )

    detail = await service.start_run(
        "incident-1",
        AutonomousRunCreateRequest(
            execution_mode=AutonomousExecutionMode.REPAIR_ONLY,
            repository_root=str(tmp_path),
        ),
    )
    run_with_patch = detail.run.model_copy(
        update={
            "patch_run_id": "patch-1",
            "loop_state": detail.run.loop_state.model_copy(
                update={
                    "checkpoint_ref": "stimpact-checkpoint/autonomous-baseline",
                    "repair_attempt_count": 1,
                }
            ),
        }
    )
    service._event_stream.upsert_run(run_with_patch)  # noqa: SLF001
    await repository.update_run(
        run_with_patch.id,
        async_job_id=run_with_patch.async_job_id,
        repo_profile_id=run_with_patch.repo_profile_id,
        run=run_with_patch,
        outcome=None,
    )
    retry_runner = StubPostVerificationRetryRunner(service._event_stream)  # noqa: SLF001
    service._runner = retry_runner  # type: ignore[assignment]  # noqa: SLF001

    await service.record_sandbox_result(
        SandboxRunRecord(
            id="sandbox-1",
            incident_id="incident-1",
            patch_run_id="patch-1",
            repo_profile_id="profile-1",
            async_job_id="job-sandbox-1",
            status=SandboxRunStatus.SUCCEEDED,
            executor_backend="kubernetes",
            external_job_id="sandbox-ext-1",
            install_command="pip install -r requirements.txt",
            reproduce_command="pytest tests/test_billing.py::test_timeout",
            verify_command="pytest tests/test_billing.py::test_timeout_fixed",
            reproduction_succeeded=True,
            patch_applied=True,
            verification_succeeded=True,
            summary="Sandbox verified the autonomous repair.",
            execution_log="sandbox execution log",
            created_at=now,
            updated_at=now,
        )
    )

    refreshed = await service.get_run_detail("incident-1", detail.run.id)
    assert refreshed.run.status is AutonomousRunStatus.QUEUED
    assert refreshed.run.phase is AutonomousRunPhase.CODING
    assert refreshed.run.async_job_id == "job-2"
    assert refreshed.run.loop_state.last_retry_context["previous_review_summary"] == (
        "The fix should be narrowed to the incident path before promotion."
    )
    assert refreshed.run.loop_state.last_retry_context["review_feedback_for_repair"] == [
        "Scope the retry logic to the checkout timeout code path only."
    ]
    assert refreshed.run.loop_state.last_retry_context["previous_diff_fingerprint"] == {
        "patch_run_id": "patch-1",
        "file_count": 1,
        "diff_line_count": 2,
        "target_files": ["app.py"],
    }
    assert retry_runner.retry_contexts
    assert reviewer.calls
