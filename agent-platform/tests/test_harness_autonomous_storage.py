from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import subprocess

import pytest

from harness.autonomous.events import PersistentAutonomousRunEventStream
from harness.autonomous.runner import AutonomousRepairRunner
from harness.autonomous.storage import AutonomousRunArtifactStore
from harness.schemas.autonomous import AutonomousDecision, AutonomousDecisionAction, AutonomousRunStatus
from harness.schemas.initializer import FeatureSeed
from harness.schemas.verification import VerificationKind


@pytest.mark.asyncio
async def test_persistent_autonomous_event_stream_writes_snapshot_transcript_and_outcome(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    _init_git_repo(tmp_path)

    artifact_store = AutonomousRunArtifactStore(base_directory=tmp_path / "autonomous-artifacts")
    event_stream = PersistentAutonomousRunEventStream(artifact_store=artifact_store)
    runner = AutonomousRepairRunner(event_stream=event_stream)

    snapshot = await runner.run_until_stop(
        incident_id="incident-1",
        repository_root=str(tmp_path),
        objective="Persist the autonomous run transcript.",
        initializer_summary="Prepare the repo and fail cleanly for transcript persistence.",
        feature_seeds=[
            FeatureSeed(
                feature_name="persistence exercised",
                description="The run should persist snapshot, events, and an outcome record.",
                verification_method="Browser assertion",
                required_verification=[VerificationKind.BROWSER],
            )
        ],
        decision_engine=ImmediateFailDecisionEngine(),
        max_steps=2,
    )

    assert snapshot.run.status is AutonomousRunStatus.FAILED

    persisted_snapshot = artifact_store.get_snapshot("incident-1", snapshot.run.id)
    persisted_outcome = artifact_store.get_outcome("incident-1", snapshot.run.id)
    artifact_paths = artifact_store.get_artifact_paths("incident-1", snapshot.run.id)

    assert persisted_snapshot.run.id == snapshot.run.id
    assert len(persisted_snapshot.events) >= 1
    assert persisted_outcome is not None
    assert persisted_outcome.total_events == len(persisted_snapshot.events)
    assert Path(artifact_paths.snapshot_path).exists()
    assert Path(artifact_paths.events_path).exists()
    assert Path(artifact_paths.outcome_path or "").exists()


class ImmediateFailDecisionEngine:
    async def decide(
        self,
        *,
        run,
        coding_session,
        available_tools,
        last_tool_result=None,
        recent_events=None,
    ) -> AutonomousDecision:
        return AutonomousDecision(
            summary="Stop after persistence is exercised.",
            rationale="This test validates the durable transcript and outcome artifacts.",
            action=AutonomousDecisionAction.FAIL,
        )


def _init_git_repo(repository_root: Path) -> None:
    _git(repository_root, "init", "-b", "main")
    _git(repository_root, "config", "user.email", "test@example.com")
    _git(repository_root, "config", "user.name", "Test User")
    _git(repository_root, "add", ".")
    _git(repository_root, "commit", "-m", "initial autonomous storage fixture")


def _git(repository_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or result.stderr.strip()
