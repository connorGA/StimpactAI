"""End-to-end style flows covering reviewer + sandbox cycles, benchmark corpus, and telemetry policy.

These run in CI without a live API server; they exercise the same services and harness
code paths as production, with deterministic stubs where external systems would sit.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from api.schemas.autonomous import AutonomousRunCreateRequest
from harness.autonomous.events import PersistentAutonomousRunEventStream
from harness.autonomous.runner import AutonomousRepairRunner
from harness.autonomous.storage import AutonomousRunArtifactStore
from harness.schemas.autonomous import (
    AutonomousDecision,
    AutonomousDecisionAction,
    AutonomousEventType,
    AutonomousExecutionMode,
    AutonomousRunPhase,
    AutonomousRunStatus,
    AutonomousSolutionReview,
    AutonomousSolutionReviewRisk,
    AutonomousSolutionReviewRiskSeverity,
    AutonomousSolutionReviewVerdict,
)
from harness.schemas.initializer import FeatureSeed
from harness.schemas.verification import VerificationKind
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
from models.incident import TelemetryRecord
from models.sandbox import SandboxRunRecord, SandboxRunStatus
from services.autonomous_runs import AutonomousRunService
from services.incident_creation import IncidentCreationService
from shared.events.incident_events import IncidentEventType
from shared.types.telemetry import Environment
from staging_drill import _seed_drill_fixture
from test_autonomous_run_service import (
    StubAsyncJobRepository,
    StubAutonomousRunRepository,
    StubControlPlaneRepository,
    StubIncidentRepository,
    StubPatchRepository,
    StubPostVerificationRetryRunner,
    _build_incident_and_profile,
)
from test_harness_autonomous_runner import _init_git_repo
from test_incident_loop_acceptance import (
    AcceptanceControlPlaneRepository,
    AcceptanceIncidentRepository,
)


class ToggleSolutionReviewService:
    """Returns the first review on the first sandbox success, then the second review."""

    def __init__(
        self,
        first: AutonomousSolutionReview,
        second: AutonomousSolutionReview,
    ) -> None:
        self._first = first
        self._second = second
        self.calls: list[dict[str, object]] = []

    async def review_solution(self, **kwargs) -> AutonomousSolutionReview:
        self.calls.append(kwargs)
        return self._first if len(self.calls) == 1 else self._second


class StagingDrillHeaderKeyDecisionEngine:
    """Same control flow as the harness unit tests, but paths match ``staging_drill`` corpus layout."""

    def __init__(self, *, feature_id: str) -> None:
        self._feature_id = feature_id

    async def decide(
        self,
        *,
        run,
        coding_session,
        available_tools,
        last_tool_result=None,
        recent_events=None,
    ) -> AutonomousDecision:
        step_index = run.loop_state.step_index
        if step_index == 0:
            return AutonomousDecision(
                summary="Fix the retry-after header lookup.",
                rationale="Use the standard Retry-After header per the staging drill corpus.",
                action=AutonomousDecisionAction.INVOKE_TOOL,
                selected_tool="edit_file",
                arguments={
                    "relative_path": "staging_drill_fixture/buggy_retry.py",
                    "new_content": (
                        "def read_retry_after(headers: dict[str, str]) -> int:\n"
                        '    return int(headers["Retry-After"])\n'
                    ),
                },
                arguments_summary="Replace the buggy file contents.",
                feature_id=self._feature_id,
            )
        if step_index == 1:
            return AutonomousDecision(
                summary="Run the verification command.",
                rationale="The drill package tests must pass.",
                action=AutonomousDecisionAction.INVOKE_TOOL,
                selected_tool="run_command",
                arguments={
                    "command": f"{sys.executable} -m pytest staging_drill_fixture/test_buggy_retry.py -q",
                },
                arguments_summary="Run pytest for the staging drill fixture.",
                feature_id=self._feature_id,
                verification_kind=VerificationKind.INTEGRATION.value,
            )
        return AutonomousDecision(
            summary="The required verification command passed.",
            rationale="Integration verification is fully satisfied.",
            action=AutonomousDecisionAction.COMPLETE,
        )


@pytest.mark.asyncio
async def test_e2e_reviewer_needs_changes_then_approve_completes_run(tmp_path: Path) -> None:
    now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
    incident, repo_profile, provider_repository = _build_incident_and_profile(now)
    async_jobs = StubAsyncJobRepository()
    repository = StubAutonomousRunRepository()
    patch_repository = StubPatchRepository()
    artifact_store = AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts")
    event_stream = PersistentAutonomousRunEventStream(artifact_store=artifact_store)

    needs_changes = AutonomousSolutionReview(
        verdict=AutonomousSolutionReviewVerdict.NEEDS_CHANGES,
        summary="Narrow the patch before promotion.",
        risks=[
            AutonomousSolutionReviewRisk(
                area="billing-api",
                severity=AutonomousSolutionReviewRiskSeverity.MEDIUM,
                reasoning="Diff spans more than the failing path.",
            )
        ],
        requested_checks=["pytest tests/test_billing.py::test_timeout_fixed"],
        feedback_for_repair=["Limit the change to the retry-after reader."],
        reviewed_at=now,
        model_name="gpt-test",
    )
    approve = AutonomousSolutionReview(
        verdict=AutonomousSolutionReviewVerdict.APPROVE,
        summary="The follow-up patch addresses the review feedback.",
        reviewed_at=now,
        model_name="gpt-test",
    )
    reviewer = ToggleSolutionReviewService(needs_changes, approve)

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

    after_retry = await service.get_run_detail("incident-1", detail.run.id)
    assert after_retry.run.status is AutonomousRunStatus.QUEUED
    assert len(reviewer.calls) == 1

    queued = after_retry.run.model_copy(
        update={
            "patch_run_id": "patch-2",
        }
    )
    service._event_stream.upsert_run(queued)  # noqa: SLF001
    await repository.update_run(
        queued.id,
        async_job_id=queued.async_job_id,
        repo_profile_id=queued.repo_profile_id,
        run=queued,
        outcome=None,
    )

    await service.record_sandbox_result(
        SandboxRunRecord(
            id="sandbox-2",
            incident_id="incident-1",
            patch_run_id="patch-2",
            repo_profile_id="profile-1",
            async_job_id="job-sandbox-2",
            status=SandboxRunStatus.SUCCEEDED,
            executor_backend="kubernetes",
            external_job_id="sandbox-ext-2",
            install_command="pip install -r requirements.txt",
            reproduce_command="pytest tests/test_billing.py::test_timeout",
            verify_command="pytest tests/test_billing.py::test_timeout_fixed",
            reproduction_succeeded=True,
            patch_applied=True,
            verification_succeeded=True,
            summary="Second sandbox verified the narrowed repair.",
            execution_log="sandbox execution log 2",
            created_at=now,
            updated_at=now,
        )
    )

    final = await service.get_run_detail("incident-1", detail.run.id)
    assert final.run.status is AutonomousRunStatus.SUCCEEDED
    assert final.run.phase is AutonomousRunPhase.COMPLETED
    assert final.run.latest_review is not None
    assert final.run.latest_review.verdict is AutonomousSolutionReviewVerdict.APPROVE
    assert len(reviewer.calls) == 2

    event_types = [e.event_type for e in final.events]
    assert AutonomousEventType.REVIEW_COMPLETED in event_types


@pytest.mark.asyncio
async def test_e2e_staging_drill_header_key_corpus_autonomous_runner_fixes(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    _seed_drill_fixture(str(tmp_path), scenario_name="header-key")
    _init_git_repo(tmp_path)

    runner = AutonomousRepairRunner()
    snapshot = await runner.run_until_stop(
        repository_root=str(tmp_path),
        objective="Fix the seeded staging drill bug end-to-end.",
        initializer_summary="Prepare coding session for benchmark header-key scenario.",
        feature_seeds=[
            FeatureSeed(
                feature_name="retry policy handles 429",
                description="HTTP 429 should be retried after the repair.",
                verification_method="Run pytest verification command",
                required_verification=[VerificationKind.INTEGRATION],
                browser_required=False,
            )
        ],
        decision_engine=StagingDrillHeaderKeyDecisionEngine(feature_id="retry-policy-handles-429"),
        max_steps=6,
    )

    assert snapshot.run.status is AutonomousRunStatus.SUCCEEDED
    assert snapshot.run.latest_verification is not None
    assert snapshot.run.latest_verification.passed is True


@pytest.mark.asyncio
async def test_e2e_telemetry_to_autonomous_run_escalates_policy_for_critical_incident(
    tmp_path: Path,
) -> None:
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

    await creation_service.process_telemetry_received(
        {
            "event_type": IncidentEventType.TELEMETRY_RECEIVED.value,
            "telemetry_id": telemetry.id,
            "project_id": telemetry.project_id,
            "fingerprint": telemetry.fingerprint,
            "occurred_at": telemetry.occurred_at.isoformat(),
            "payload": {},
        }
    )

    assert incident_repository.incident is not None

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
            max_steps=20,
        ),
    )

    assert detail.run.policy.max_repair_attempts >= 3
    assert detail.run.policy.max_retry_budget >= 3
    assert detail.run.loop_state.max_steps >= 32
    assert detail.run.policy.require_browser_verification is True
