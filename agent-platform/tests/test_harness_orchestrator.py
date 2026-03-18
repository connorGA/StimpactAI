from __future__ import annotations

from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import subprocess
import sys

import pytest

from harness.orchestrator.service import HarnessSessionOrchestrator
from harness.schemas.initializer import FeatureSeed
from harness.schemas.orchestrator import (
    GenerateInitializerOutputRequest,
    OrchestratorSessionStartRequest,
    ToolInvocationRequest,
    UpdateObjectiveRequest,
)
from harness.schemas.runtime import HarnessAgentRole
from harness.schemas.verification import VerificationKind, VerificationStatus


def test_orchestrator_initializes_sessions_lists_role_tools_and_restores_state(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    orchestrator = HarnessSessionOrchestrator()

    snapshot = orchestrator.initialize_session(
        OrchestratorSessionStartRequest(
            role=HarnessAgentRole.INITIALIZER,
            repository_root=str(tmp_path),
            objective="Inspect repo",
        )
    )

    tool_names = {tool.name for tool in snapshot.available_tools.tools}
    assert "find_file" in tool_names
    assert "open_file" in tool_names
    assert "edit_file" not in tool_names
    assert "run_command" not in tool_names
    assert "current_branch_info" not in tool_names
    assert snapshot.turn_count == 0

    updated = orchestrator.update_objective(
        snapshot.session.id,
        UpdateObjectiveRequest(objective="Updated repo objective"),
    )
    restored = orchestrator.restore_session(snapshot.session.id)

    assert updated.session.objective == "Updated repo objective"
    assert restored.prompt_context.current_objective == "Updated repo objective"


def test_orchestrator_generates_initializer_output_and_builds_coding_handoff(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    orchestrator = HarnessSessionOrchestrator()

    initializer = orchestrator.initialize_session(
        OrchestratorSessionStartRequest(
            role=HarnessAgentRole.INITIALIZER,
            repository_root=str(tmp_path),
            objective="Prepare initializer output",
        )
    )
    initializer_output = orchestrator.generate_initializer_output(
        initializer.session.id,
        GenerateInitializerOutputRequest(
            summary="Initializer mapped install and verification paths.",
            feature_seeds=[
                FeatureSeed(
                    feature_name="Dashboard loads",
                    description="User can load the dashboard.",
                    verification_method="Browser smoke test",
                    required_verification=[VerificationKind.BROWSER],
                )
            ],
        ),
    )
    persisted_initializer = orchestrator.persist_initializer_output(initializer.session.id, initializer_output)

    coding = orchestrator.initialize_session(
        OrchestratorSessionStartRequest(
            role=HarnessAgentRole.CODING,
            repository_root=str(tmp_path),
            objective="Fix dashboard issue",
            initializer_session_id=initializer.session.id,
        )
    )
    handoff = orchestrator.build_coding_handoff(
        initializer_session_id=initializer.session.id,
        coding_session_id=coding.session.id,
    )

    assert persisted_initializer.feature_catalog is not None
    assert coding.feature_catalog is not None
    assert handoff.coding_input.repository_profile == coding.session.repository_profile
    assert handoff.coding_input.initializer_output.summary.startswith("Initializer mapped")
    assert handoff.coding_session.feature_catalog is not None
    assert handoff.coding_session.feature_catalog.features[0].id == "dashboard-loads"


def test_orchestrator_routes_edit_and_git_tools_and_updates_feature_state(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    target = tmp_path / "app.py"
    target.write_text("print('before')\n", encoding="utf-8")
    _git(tmp_path, "add", "app.py")
    _git(tmp_path, "commit", "-m", "initial commit")

    orchestrator = HarnessSessionOrchestrator()
    initializer = orchestrator.initialize_session(
        OrchestratorSessionStartRequest(
            role=HarnessAgentRole.INITIALIZER,
            repository_root=str(tmp_path),
        )
    )
    initializer_output = orchestrator.generate_initializer_output(
        initializer.session.id,
        GenerateInitializerOutputRequest(
            summary="Initializer mapped repo.",
            feature_seeds=[
                FeatureSeed(
                    feature_name="Fix bug",
                    description="Bug fix feature",
                    verification_method="Unit tests",
                    required_verification=[VerificationKind.UNIT],
                    browser_required=False,
                )
            ],
        ),
    )
    orchestrator.persist_initializer_output(initializer.session.id, initializer_output)
    coding = orchestrator.initialize_session(
        OrchestratorSessionStartRequest(
            role=HarnessAgentRole.CODING,
            repository_root=str(tmp_path),
            initializer_session_id=initializer.session.id,
        )
    )

    edit_result = orchestrator.invoke_tool(
        coding.session.id,
        ToolInvocationRequest(
            tool_name="edit_file",
            arguments={
                "file_path": "app.py",
                "start_line": 1,
                "end_line": 1,
                "replacement_text": "print('after')",
            },
            feature_id="fix-bug",
        ),
    )
    git_result = orchestrator.invoke_tool(
        coding.session.id,
        ToolInvocationRequest(
            tool_name="current_branch_info",
            arguments={},
        ),
    )
    restored = orchestrator.restore_session(coding.session.id)

    assert edit_result.ok is True
    assert edit_result.feature_state is not None
    assert edit_result.feature_state.status is VerificationStatus.CODE_CHANGED
    assert git_result.ok is True
    assert git_result.result["branch_info"]["branch_name"] == "main"
    assert restored.turn_count == 2
    assert restored.feature_catalog is not None
    assert restored.feature_catalog.features[0].verification_state.status is VerificationStatus.CODE_CHANGED

    with pytest.raises(PermissionError):
        orchestrator.invoke_tool(
            initializer.session.id,
            ToolInvocationRequest(tool_name="current_branch_info", arguments={}),
        )


def test_orchestrator_normalizes_relative_path_for_edit_file_whole_file_replacement(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    target = tmp_path / "src" / "buggy_retry.py"
    target.write_text("VALUE = 'old'\n", encoding="utf-8")
    orchestrator = HarnessSessionOrchestrator()
    session = orchestrator.initialize_session(
        OrchestratorSessionStartRequest(
            role=HarnessAgentRole.CODING,
            repository_root=str(tmp_path),
        )
    )

    result = orchestrator.invoke_tool(
        session.session.id,
        ToolInvocationRequest(
            tool_name="edit_file",
            arguments={
                "relative_path": "src/buggy_retry.py",
                "new_content": "VALUE = 'new'\n",
            },
        ),
    )

    assert result.ok is True
    assert target.read_text(encoding="utf-8") == "VALUE = 'new'\n"


def test_orchestrator_normalizes_relative_path_for_search_dir(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "buggy_retry.py").write_text("Retry-After\n", encoding="utf-8")
    orchestrator = HarnessSessionOrchestrator()
    session = orchestrator.initialize_session(
        OrchestratorSessionStartRequest(
            role=HarnessAgentRole.CODING,
            repository_root=str(tmp_path),
        )
    )

    for alias in ("relative_path", "directory", "scope_path"):
        result = orchestrator.invoke_tool(
            session.session.id,
            ToolInvocationRequest(
                tool_name="search_dir",
                arguments={
                    "query": "Retry-After",
                    alias: "src",
                },
            ),
        )

        assert result.ok is True
        assert result.result["result_count"] == 1
        assert result.result["results"][0]["path"] == "buggy_retry.py"


def test_orchestrator_normalizes_relative_path_for_open_file(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    target = tmp_path / "src" / "buggy_retry.py"
    target.write_text("Retry-After\n", encoding="utf-8")
    orchestrator = HarnessSessionOrchestrator()
    session = orchestrator.initialize_session(
        OrchestratorSessionStartRequest(
            role=HarnessAgentRole.CODING,
            repository_root=str(tmp_path),
        )
    )

    for alias in ("relative_path", "path"):
        result = orchestrator.invoke_tool(
            session.session.id,
            ToolInvocationRequest(
                tool_name="open_file",
                arguments={alias: "src/buggy_retry.py"},
            ),
        )

        assert result.ok is True
        assert result.result["file_path"].endswith("src/buggy_retry.py")


def test_orchestrator_runs_command_and_records_integration_verification(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    (tmp_path / "test_target.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    orchestrator = HarnessSessionOrchestrator()
    initializer = orchestrator.initialize_session(
        OrchestratorSessionStartRequest(
            role=HarnessAgentRole.INITIALIZER,
            repository_root=str(tmp_path),
        )
    )
    initializer_output = orchestrator.generate_initializer_output(
        initializer.session.id,
        GenerateInitializerOutputRequest(
            summary="Initializer mapped repo.",
            feature_seeds=[
                FeatureSeed(
                    feature_name="verification command works",
                    description="The repo verification command should succeed.",
                    verification_method="Run integration verification command",
                    verification_command="python -m pytest test_target.py -q",
                    required_verification=[VerificationKind.INTEGRATION],
                    browser_required=False,
                )
            ],
        ),
    )
    orchestrator.persist_initializer_output(initializer.session.id, initializer_output)
    coding = orchestrator.initialize_session(
        OrchestratorSessionStartRequest(
            role=HarnessAgentRole.CODING,
            repository_root=str(tmp_path),
            initializer_session_id=initializer.session.id,
        )
    )

    tool_names = {tool.name for tool in coding.available_tools.tools}
    assert "run_command" in tool_names

    verification = orchestrator.invoke_tool(
        coding.session.id,
        ToolInvocationRequest(
            tool_name="run_command",
            arguments={
                "command": f"{sys.executable} -m pytest test_target.py -q",
            },
            feature_id="verification-command-works",
            verification_kind=VerificationKind.INTEGRATION,
        ),
    )

    restored = orchestrator.restore_session(coding.session.id)
    assert verification.ok is True
    assert verification.result["exit_code"] == 0
    assert "1 passed" in verification.result["stdout"]
    assert verification.feature_state is not None
    assert verification.feature_state.status is VerificationStatus.FULLY_VERIFIED
    assert restored.feature_catalog is not None
    assert restored.feature_catalog.features[0].verification_state.status is VerificationStatus.FULLY_VERIFIED


def test_orchestrator_rejects_masked_verification_commands(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    orchestrator = HarnessSessionOrchestrator()
    initializer = orchestrator.initialize_session(
        OrchestratorSessionStartRequest(
            role=HarnessAgentRole.INITIALIZER,
            repository_root=str(tmp_path),
        )
    )
    initializer_output = orchestrator.generate_initializer_output(
        initializer.session.id,
        GenerateInitializerOutputRequest(
            summary="Initializer mapped repo.",
            feature_seeds=[
                FeatureSeed(
                    feature_name="verification command must fail honestly",
                    description="Masked command failures must not satisfy verification.",
                    verification_method="Run integration verification command",
                    required_verification=[VerificationKind.INTEGRATION],
                    browser_required=False,
                )
            ],
        ),
    )
    orchestrator.persist_initializer_output(initializer.session.id, initializer_output)
    coding = orchestrator.initialize_session(
        OrchestratorSessionStartRequest(
            role=HarnessAgentRole.CODING,
            repository_root=str(tmp_path),
            initializer_session_id=initializer.session.id,
        )
    )

    verification = orchestrator.invoke_tool(
        coding.session.id,
        ToolInvocationRequest(
            tool_name="run_command",
            arguments={
                "command": f"{sys.executable} -c \"import sys; sys.exit(1)\" || true",
            },
            feature_id="verification-command-must-fail-honestly",
            verification_kind=VerificationKind.INTEGRATION,
        ),
    )

    restored = orchestrator.restore_session(coding.session.id)
    assert verification.ok is False
    assert "must not mask failures" in str(verification.result["message"]).lower()
    assert verification.feature_state is not None
    assert verification.feature_state.status is VerificationStatus.FAILED_VERIFICATION
    assert restored.feature_catalog is not None
    assert restored.feature_catalog.features[0].verification_state.status is VerificationStatus.FAILED_VERIFICATION


def test_orchestrator_rejects_diagnostic_commands_as_feature_verification(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    orchestrator = HarnessSessionOrchestrator()
    initializer = orchestrator.initialize_session(
        OrchestratorSessionStartRequest(
            role=HarnessAgentRole.INITIALIZER,
            repository_root=str(tmp_path),
        )
    )
    initializer_output = orchestrator.generate_initializer_output(
        initializer.session.id,
        GenerateInitializerOutputRequest(
            summary="Initializer mapped repo.",
            feature_seeds=[
                FeatureSeed(
                    feature_name="verification command must match target",
                    description="A diagnostic shell command must not count as the feature verification step.",
                    verification_method="Run integration verification command",
                    verification_command="python -m pytest tests/test_target.py -q",
                    required_verification=[VerificationKind.INTEGRATION],
                    browser_required=False,
                )
            ],
        ),
    )
    orchestrator.persist_initializer_output(initializer.session.id, initializer_output)
    coding = orchestrator.initialize_session(
        OrchestratorSessionStartRequest(
            role=HarnessAgentRole.CODING,
            repository_root=str(tmp_path),
            initializer_session_id=initializer.session.id,
        )
    )

    verification = orchestrator.invoke_tool(
        coding.session.id,
        ToolInvocationRequest(
            tool_name="run_command",
            arguments={"command": "which python3"},
            feature_id="verification-command-must-match-target",
            verification_kind=VerificationKind.INTEGRATION,
        ),
    )

    restored = orchestrator.restore_session(coding.session.id)
    assert verification.ok is True
    assert verification.feature_state is not None
    assert verification.feature_state.status is VerificationStatus.FAILED_VERIFICATION
    assert "expected verification target" in verification.feature_state.attempted[-1].summary.lower()
    assert restored.feature_catalog is not None
    assert restored.feature_catalog.features[0].verification_state.status is VerificationStatus.FAILED_VERIFICATION


def test_orchestrator_records_browser_verification_from_tool_output(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    page_root = tmp_path / "site"
    page_root.mkdir()
    (page_root / "index.html").write_text(
        """
<!doctype html>
<html>
  <body>
    <div id="message">Verification Ready</div>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )

    orchestrator = HarnessSessionOrchestrator()
    initializer = orchestrator.initialize_session(
        OrchestratorSessionStartRequest(
            role=HarnessAgentRole.INITIALIZER,
            repository_root=str(tmp_path),
        )
    )
    initializer_output = orchestrator.generate_initializer_output(
        initializer.session.id,
        GenerateInitializerOutputRequest(
            summary="Initializer mapped repo.",
            feature_seeds=[
                FeatureSeed(
                    feature_name="Landing page works",
                    description="User can see the landing page message.",
                    verification_method="Browser assertion",
                    required_verification=[VerificationKind.BROWSER],
                )
            ],
        ),
    )
    orchestrator.persist_initializer_output(initializer.session.id, initializer_output)
    coding = orchestrator.initialize_session(
        OrchestratorSessionStartRequest(
            role=HarnessAgentRole.CODING,
            repository_root=str(tmp_path),
            initializer_session_id=initializer.session.id,
        )
    )

    with serve_directory(page_root) as base_url:
        opened = orchestrator.invoke_tool(
            coding.session.id,
            ToolInvocationRequest(
                tool_name="browser_open",
                arguments={"url": f"{base_url}/index.html", "timeout_ms": 10_000},
            ),
        )
        browser_session_id = opened.result["session_id"]
        verification = orchestrator.invoke_tool(
            coding.session.id,
            ToolInvocationRequest(
                tool_name="browser_assert_text",
                arguments={
                    "session_id": browser_session_id,
                    "text": "Verification Ready",
                    "selector": "#message",
                },
                feature_id="landing-page-works",
                verification_kind=VerificationKind.BROWSER,
            ),
        )
        orchestrator.invoke_tool(
            coding.session.id,
            ToolInvocationRequest(
                tool_name="browser_close",
                arguments={"session_id": browser_session_id},
            ),
        )

    restored = orchestrator.restore_session(coding.session.id)
    assert verification.ok is True
    assert verification.feature_state is not None
    assert verification.feature_state.status is VerificationStatus.FULLY_VERIFIED
    assert restored.feature_catalog is not None
    assert restored.feature_catalog.features[0].verification_state.status is VerificationStatus.FULLY_VERIFIED
    assert "verification" in restored.prompt_context.rendered_context.lower()


def test_orchestrator_reuses_last_browser_session_for_page_state(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    page_root = tmp_path / "site"
    page_root.mkdir()
    (page_root / "index.html").write_text(
        """
<!doctype html>
<html>
  <body>
    <div id="message">Verification Ready</div>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )

    orchestrator = HarnessSessionOrchestrator()
    coding = orchestrator.initialize_session(
        OrchestratorSessionStartRequest(
            role=HarnessAgentRole.CODING,
            repository_root=str(tmp_path),
        )
    )

    with serve_directory(page_root) as base_url:
        opened = orchestrator.invoke_tool(
            coding.session.id,
            ToolInvocationRequest(
                tool_name="browser_open",
                arguments={"url": f"{base_url}/index.html", "timeout_ms": 10_000},
            ),
        )
        assert opened.ok is True

        page_state = orchestrator.invoke_tool(
            coding.session.id,
            ToolInvocationRequest(
                tool_name="current_page_state",
                arguments={},
            ),
        )
        assert page_state.ok is True
        assert page_state.result["page_state"]["ready_state"] == "complete"

        closed = orchestrator.invoke_tool(
            coding.session.id,
            ToolInvocationRequest(
                tool_name="browser_close",
                arguments={},
            ),
        )
        assert closed.ok is True


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


def _git(repository_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or result.stderr.strip()
