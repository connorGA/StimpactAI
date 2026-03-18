from __future__ import annotations

from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import subprocess

import pytest

from harness.autonomous.events import InMemoryAutonomousRunEventStream
from harness.autonomous.runner import AutonomousRepairRunner
from harness.schemas.autonomous import (
    AutonomousDecision,
    AutonomousDecisionAction,
    AutonomousEventType,
    AutonomousRunPhase,
    AutonomousRunStatus,
)
from harness.schemas.initializer import FeatureSeed
from harness.schemas.verification import VerificationKind


def test_autonomous_repair_runner_bootstraps_coding_ready_run_and_persists_initializer_artifacts(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")

    event_stream = InMemoryAutonomousRunEventStream()
    runner = AutonomousRepairRunner(event_stream=event_stream)

    snapshot = runner.bootstrap_run(
        repository_root=str(tmp_path),
        objective="Fix the seeded bug autonomously.",
        initializer_summary="Bootstrap the repo and prepare a coding-ready repair session.",
        feature_seeds=[
            FeatureSeed(
                feature_name="User can load dashboard",
                description="Dashboard route renders successfully.",
                verification_method="Browser smoke test",
                required_verification=[VerificationKind.BROWSER],
            )
        ],
    )

    run_id = snapshot.run.id
    later_snapshot = runner.get_snapshot(run_id)

    assert snapshot.run.status is AutonomousRunStatus.RUNNING
    assert snapshot.run.phase is AutonomousRunPhase.CODING
    assert snapshot.run.initializer_session_id is not None
    assert snapshot.run.coding_session_id is not None
    assert Path(tmp_path / "init.sh").exists()
    assert Path(tmp_path / ".stimpactai" / "features.json").exists()
    assert later_snapshot.run.id == run_id

    event_types = [event.event_type for event in snapshot.events]
    assert event_types == [
        AutonomousEventType.RUN_STARTED,
        AutonomousEventType.SESSION_INITIALIZED,
        AutonomousEventType.INITIALIZER_OUTPUT_GENERATED,
        AutonomousEventType.INITIALIZER_OUTPUT_PERSISTED,
        AutonomousEventType.PHASE_CHANGED,
        AutonomousEventType.CODING_SESSION_READY,
    ]
    assert snapshot.events[-1].payload["available_tools"]
    assert "user-can-load-dashboard" in snapshot.events[-1].payload["feature_ids"]


def test_autonomous_event_stream_notifies_subscribers_for_appended_events(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    stream = InMemoryAutonomousRunEventStream()
    runner = AutonomousRepairRunner(event_stream=stream)
    received: list[AutonomousEventType] = []

    snapshot = runner.bootstrap_run(
        repository_root=str(tmp_path),
        objective="Bootstrap only.",
        initializer_summary="Generate default initializer output.",
    )
    run_id = snapshot.run.id

    def subscriber(event) -> None:
        received.append(event.event_type)

    stream.subscribe(run_id, subscriber)
    stream.append_event(
        snapshot.events[-1].model_copy(
            update={
                "id": "manual-event",
                "event_type": AutonomousEventType.DECISION_MADE,
                "summary": "Manual decision event",
            }
        )
    )

    assert received == [AutonomousEventType.DECISION_MADE]


@pytest.mark.asyncio
async def test_autonomous_repair_runner_executes_decision_loop_until_verified_completion(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    site_root = tmp_path / "site"
    site_root.mkdir()
    (site_root / "index.html").write_text(
        """
<!doctype html>
<html>
  <body>
    <div id="result">Before Edit</div>
    <script src="./app.js"></script>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )
    (site_root / "app.js").write_text(
        """
const result = document.getElementById("result");
if (result) {
  result.innerText = "Before Edit";
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    _init_git_repo(tmp_path)

    runner = AutonomousRepairRunner()
    feature_id = "browser-greeting-updates"
    with serve_directory(site_root) as base_url:
        decision_engine = FakeDecisionEngine(
            base_url=base_url,
            feature_id=feature_id,
        )
        snapshot = await runner.run_until_stop(
            repository_root=str(tmp_path),
            objective="Update the browser greeting autonomously.",
            initializer_summary="Prepare coding and browser verification.",
            feature_seeds=[
                FeatureSeed(
                    feature_name="browser greeting updates",
                    description="The browser page should show the edited greeting.",
                    verification_method="Browser assertion",
                    required_verification=[VerificationKind.BROWSER],
                )
            ],
            decision_engine=decision_engine,
            max_steps=8,
        )

    assert snapshot.run.status is AutonomousRunStatus.SUCCEEDED
    assert snapshot.run.phase is AutonomousRunPhase.COMPLETED
    assert snapshot.run.loop_state.step_index >= 4
    assert snapshot.run.loop_state.checkpoint_ref is not None
    event_types = [event.event_type for event in snapshot.events]
    assert AutonomousEventType.GIT_CHECKPOINT_CREATED in event_types
    assert AutonomousEventType.DECISION_MADE in event_types
    assert AutonomousEventType.TOOL_CALL_STARTED in event_types
    assert AutonomousEventType.TOOL_CALL_COMPLETED in event_types
    assert AutonomousEventType.VERIFICATION_STATE_UPDATED in event_types
    assert AutonomousEventType.RUN_COMPLETED in event_types
    assert "After Autonomous Run" in (site_root / "app.js").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_autonomous_repair_runner_fails_when_engine_completes_before_verification(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    _init_git_repo(tmp_path)
    runner = AutonomousRepairRunner()

    snapshot = await runner.run_until_stop(
        repository_root=str(tmp_path),
        objective="Attempt premature completion.",
        initializer_summary="Prepare coding session.",
        feature_seeds=[
            FeatureSeed(
                feature_name="premature completion feature",
                description="Feature still requires verification.",
                verification_method="Browser assertion",
                required_verification=[VerificationKind.BROWSER],
            )
        ],
        decision_engine=PrematureCompleteDecisionEngine(),
        max_steps=2,
    )

    assert snapshot.run.status is AutonomousRunStatus.FAILED
    assert snapshot.run.phase is AutonomousRunPhase.FAILED
    assert snapshot.run.last_error is not None
    assert "before verification" in snapshot.run.last_error.lower()
    assert snapshot.events[-1].event_type is AutonomousEventType.RUN_FAILED


@pytest.mark.asyncio
async def test_autonomous_repair_runner_recovers_from_tool_execution_exception(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    _init_git_repo(tmp_path)
    runner = AutonomousRepairRunner()

    snapshot = await runner.run_until_stop(
        repository_root=str(tmp_path),
        objective="Exercise autonomous recovery.",
        initializer_summary="Prepare coding session with checkpoint recovery.",
        feature_seeds=[
            FeatureSeed(
                feature_name="recovery exercised",
                description="The runner should recover from a tool execution exception.",
                verification_method="N/A",
                required_verification=[],
            )
        ],
        decision_engine=RecoveryDecisionEngine(),
        max_steps=3,
    )

    assert snapshot.run.status is AutonomousRunStatus.FAILED
    assert snapshot.run.last_error == "Stop after recovery was exercised."
    assert snapshot.run.loop_state.recovery_attempts == 1
    assert snapshot.run.loop_state.last_tool_result["recovered"] is True
    event_types = [event.event_type for event in snapshot.events]
    assert AutonomousEventType.GIT_CHECKPOINT_CREATED in event_types
    assert AutonomousEventType.RECOVERY_INVOKED in event_types


class FakeDecisionEngine:
    def __init__(self, *, base_url: str, feature_id: str) -> None:
        self._base_url = base_url
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
                summary="Edit the browser script to update the greeting.",
                rationale="The runner already created a baseline checkpoint, so the target file can now be changed safely.",
                action=AutonomousDecisionAction.INVOKE_TOOL,
                selected_tool="edit_file",
                arguments={
                    "file_path": "site/app.js",
                    "start_line": 3,
                    "end_line": 3,
                    "replacement_text": '  result.innerText = "After Autonomous Run";',
                },
                arguments_summary="edit site/app.js line 3",
                feature_id=self._feature_id,
            )
        if step_index == 1:
            return AutonomousDecision(
                summary="Open the page in the browser.",
                rationale="Browser verification requires the rendered page.",
                action=AutonomousDecisionAction.INVOKE_TOOL,
                selected_tool="browser_open",
                arguments={"url": f"{self._base_url}/index.html", "timeout_ms": 10000},
                arguments_summary="open fixture page",
            )
        if step_index == 2:
            browser_session_id = str((last_tool_result or {}).get("session_id"))
            return AutonomousDecision(
                summary="Assert the updated text in the browser.",
                rationale="The feature requires browser-level verification.",
                action=AutonomousDecisionAction.INVOKE_TOOL,
                selected_tool="browser_assert_text",
                arguments={
                    "session_id": browser_session_id,
                    "text": "After Autonomous Run",
                    "selector": "#result",
                },
                arguments_summary="assert #result text",
                feature_id=self._feature_id,
                verification_kind=VerificationKind.BROWSER.value,
            )
        if step_index == 3:
            browser_session_id = str((last_tool_result or {}).get("result", {}).get("session_id") or (last_tool_result or {}).get("session_id") or "")
            if browser_session_id:
                return AutonomousDecision(
                    summary="Close the browser session.",
                    rationale="Cleanup before completing the run.",
                    action=AutonomousDecisionAction.INVOKE_TOOL,
                    selected_tool="browser_close",
                    arguments={"session_id": browser_session_id},
                    arguments_summary="close browser session",
                )
        return AutonomousDecision(
            summary="All required verification is complete.",
            rationale="The feature verification state is fully verified.",
            action=AutonomousDecisionAction.COMPLETE,
        )


class PrematureCompleteDecisionEngine:
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
            summary="Stop now.",
            rationale="Intentional failure for validation.",
            action=AutonomousDecisionAction.COMPLETE,
        )


class RecoveryDecisionEngine:
    async def decide(
        self,
        *,
        run,
        coding_session,
        available_tools,
        last_tool_result=None,
        recent_events=None,
    ) -> AutonomousDecision:
        if run.loop_state.recovery_attempts == 0:
            return AutonomousDecision(
                summary="Trigger an execution failure to exercise recovery.",
                rationale="The runner should recover to the baseline checkpoint when tool execution raises unexpectedly.",
                action=AutonomousDecisionAction.INVOKE_TOOL,
                selected_tool="missing_tool",
                arguments={},
                arguments_summary="invoke missing tool",
            )
        return AutonomousDecision(
            summary="Stop after recovery was exercised.",
            rationale="The test only needs to prove the runner recovered and continued.",
            action=AutonomousDecisionAction.FAIL,
        )


@contextmanager
def serve_directory(root: Path):
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _init_git_repo(repository_root: Path) -> None:
    _git(repository_root, "init", "-b", "main")
    _git(repository_root, "config", "user.email", "test@example.com")
    _git(repository_root, "config", "user.name", "Test User")
    _git(repository_root, "add", ".")
    _git(repository_root, "commit", "-m", "initial autonomous fixture")


def _git(repository_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or result.stderr.strip()
