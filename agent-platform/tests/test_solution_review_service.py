from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.schemas.autonomous import AutonomousRunDetailResponse
from harness.schemas.autonomous import (
    AutonomousApprovalStatus,
    AutonomousExecutionMode,
    AutonomousLoopState,
    AutonomousPolicyDecision,
    AutonomousPromotionStatus,
    AutonomousRepairRunRecord,
    AutonomousRunOutcome,
    AutonomousRunPhase,
    AutonomousRunStatus,
)
from models.patch import PatchRunRecord, PatchRunStatus, PatchTargetFile
from models.sandbox import SandboxRunRecord, SandboxRunStatus
from services.solution_review import SolutionReviewService


class _FakeCompletions:
    async def create(self, **kwargs):
        _ = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            '{"verdict":"needs_changes","summary":"The patch is close but still broad.",'
                            '"risks":[{"area":"checkout","severity":"medium","reasoning":"The diff touches shared retry code."}],'
                            '"requested_checks":["pytest tests/test_checkout.py"],'
                            '"feedback_for_repair":["Scope the retry logic to the checkout timeout path only."]}'
                        )
                    )
                )
            ]
        )


class _FakeClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions())


@pytest.mark.asyncio
async def test_solution_review_service_parses_structured_json() -> None:
    service = SolutionReviewService(client=_FakeClient(), model="gpt-test")
    run = AutonomousRepairRunRecord(
        id="run-1",
        incident_id="incident-1",
        repository_root="/tmp/repo",
        objective="Repair the timeout bug.",
        status=AutonomousRunStatus.SUCCEEDED,
        phase=AutonomousRunPhase.COMPLETED,
        execution_mode=AutonomousExecutionMode.REPAIR_ONLY,
        approval_status=AutonomousApprovalStatus.NOT_REQUIRED,
        promotion_status=AutonomousPromotionStatus.NOT_REQUESTED,
        policy=AutonomousPolicyDecision(),
        loop_state=AutonomousLoopState(repair_attempt_count=1),
        created_at="2026-03-18T12:00:00Z",
        updated_at="2026-03-18T12:01:00Z",
    )
    detail = AutonomousRunDetailResponse(
        run=run,
        events=[],
        outcome=AutonomousRunOutcome(
            run_id="run-1",
            incident_id="incident-1",
            status=AutonomousRunStatus.SUCCEEDED,
            phase=AutonomousRunPhase.COMPLETED,
            objective="Repair the timeout bug.",
            repository_root="/tmp/repo",
            execution_mode=AutonomousExecutionMode.REPAIR_ONLY,
            approval_status=AutonomousApprovalStatus.NOT_REQUIRED,
            promotion_status=AutonomousPromotionStatus.NOT_REQUESTED,
            policy=AutonomousPolicyDecision(),
            created_at="2026-03-18T12:00:00Z",
            completed_at="2026-03-18T12:01:00Z",
        ),
        artifact_paths={"snapshot_path": "snapshot.json", "events_path": "events.jsonl", "outcome_path": "outcome.json"},
    )
    patch_run = PatchRunRecord(
        id="patch-1",
        incident_id="incident-1",
        repo_profile_id="profile-1",
        status=PatchRunStatus.GENERATED,
        patch_summary="Limit retries to the checkout path.",
        rationale="Avoid global retry behavior.",
        target_files=[PatchTargetFile(path="app.py", reason="Repair logic changed.")],
        unified_diff="diff --git a/app.py b/app.py\n",
        verification_steps=["pytest tests/test_checkout.py"],
        confidence=0.9,
        model_name="autonomous-harness",
        based_on_commit_sha="deadbeef",
        diff_line_count=4,
        file_count=1,
        created_at="2026-03-18T12:00:00Z",
        updated_at="2026-03-18T12:01:00Z",
    )
    sandbox_run = SandboxRunRecord(
        id="sandbox-1",
        incident_id="incident-1",
        patch_run_id="patch-1",
        repo_profile_id="profile-1",
        async_job_id="job-1",
        status=SandboxRunStatus.SUCCEEDED,
        executor_backend="kubernetes",
        external_job_id="sandbox-ext-1",
        install_command="pip install -r requirements.txt",
        reproduce_command="pytest tests/test_checkout.py::test_timeout",
        verify_command="pytest tests/test_checkout.py::test_timeout_fixed",
        reproduction_succeeded=True,
        patch_applied=True,
        verification_succeeded=True,
        summary="Sandbox verified the repair.",
        execution_log="sandbox log",
        created_at="2026-03-18T12:00:00Z",
        updated_at="2026-03-18T12:01:00Z",
    )

    review = await service.review_solution(
        detail=detail,
        patch_run=patch_run,
        sandbox_run=sandbox_run,
    )

    assert review.verdict.value == "needs_changes"
    assert review.summary == "The patch is close but still broad."
    assert review.risks[0].area == "checkout"
    assert review.feedback_for_repair == [
        "Scope the retry logic to the checkout timeout path only."
    ]
