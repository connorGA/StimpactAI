from __future__ import annotations

from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import subprocess

from harness.orchestrator.service import HarnessSessionOrchestrator
from harness.schemas.initializer import FeatureSeed
from harness.schemas.orchestrator import GenerateInitializerOutputRequest, OrchestratorSessionStartRequest, ToolInvocationRequest
from harness.schemas.runtime import HarnessAgentRole
from harness.schemas.self_test import HarnessSelfTestResult, HarnessSelfTestStepResult
from harness.schemas.verification import VerificationKind, VerificationStatus


class HarnessSelfTestRunner:
    FEATURE_NAME = "browser greeting updates after guarded edit"
    FEATURE_ID = "browser-greeting-updates-after-guarded-edit"

    def __init__(self, *, orchestrator: HarnessSessionOrchestrator | None = None) -> None:
        self._orchestrator = orchestrator or HarnessSessionOrchestrator()

    def run(self, *, working_directory: str) -> HarnessSelfTestResult:
        repo_root = self._create_fixture_repo(Path(working_directory).resolve())
        step_results: list[HarnessSelfTestStepResult] = []

        initializer = self._orchestrator.initialize_session(
            OrchestratorSessionStartRequest(
                role=HarnessAgentRole.INITIALIZER,
                repository_root=str(repo_root),
                objective="Run the harness self-test initializer flow.",
            )
        )
        initializer_output = self._orchestrator.generate_initializer_output(
            initializer.session.id,
            GenerateInitializerOutputRequest(
                summary="Self-test initializer mapped setup, edit, git, and browser verification flows.",
                feature_seeds=[
                    FeatureSeed(
                        feature_name=self.FEATURE_NAME,
                        description="The greeting shown in the browser updates after a guarded code edit.",
                        verification_method="Open the sample page in a browser and assert the updated text.",
                        required_verification=[VerificationKind.BROWSER],
                    )
                ],
                environment_notes=["Self-test fixture repo created for end-to-end validation."],
            ),
        )
        persisted_initializer = self._orchestrator.persist_initializer_output(initializer.session.id, initializer_output)
        init_script_path = repo_root / "init.sh"
        features_path = repo_root / ".stimpactai" / "features.json"
        step_results.append(
            HarnessSelfTestStepResult(
                name="initializer_phase",
                ok=init_script_path.exists() and features_path.exists(),
                details="Initializer output persisted init.sh and features.json to the fixture repository.",
            )
        )

        coding = self._orchestrator.initialize_session(
            OrchestratorSessionStartRequest(
                role=HarnessAgentRole.CODING,
                repository_root=str(repo_root),
                objective="Run self-test repair and verification flow.",
                initializer_session_id=initializer.session.id,
            )
        )

        self._orchestrator.invoke_tool(
            coding.session.id,
            ToolInvocationRequest(
                tool_name="open_file",
                arguments={"file_path": "site/app.js"},
                summary="Inspected the sample browser script before editing.",
            ),
        )

        checkpoint_result = self._orchestrator.invoke_tool(
            coding.session.id,
            ToolInvocationRequest(
                tool_name="checkpoint",
                arguments={"label": "self-test-baseline"},
                summary="Created a baseline checkpoint before editing.",
            ),
        )
        checkpoint_ref = str(checkpoint_result.result["checkpoint"]["tag_name"])
        step_results.append(
            HarnessSelfTestStepResult(
                name="git_checkpoint",
                ok=checkpoint_result.ok,
                details=f"Created git checkpoint {checkpoint_ref}.",
            )
        )

        edit_result = self._orchestrator.invoke_tool(
            coding.session.id,
            ToolInvocationRequest(
                tool_name="edit_file",
                arguments={
                    "file_path": "site/app.js",
                    "start_line": 3,
                    "end_line": 3,
                    "replacement_text": '  result.innerText = "After Self Test";',
                },
                feature_id=self.FEATURE_ID,
                summary="Updated the browser greeting through a guarded edit.",
            ),
        )
        validation_ok = bool(edit_result.result.get("validation", {}).get("ok"))
        step_results.append(
            HarnessSelfTestStepResult(
                name="guarded_edit",
                ok=edit_result.ok and validation_ok,
                details="Guarded editing succeeded and syntax validation passed for site/app.js.",
            )
        )

        diff_result = self._orchestrator.invoke_tool(
            coding.session.id,
            ToolInvocationRequest(
                tool_name="diff_since_checkpoint",
                arguments={"checkpoint_ref": checkpoint_ref},
                summary="Inspected the diff from the self-test checkpoint.",
            ),
        )
        diff_file_paths = [item["path"] for item in diff_result.result.get("diff", {}).get("changed_files", [])]
        step_results.append(
            HarnessSelfTestStepResult(
                name="git_diff",
                ok=diff_result.ok and "site/app.js" in diff_file_paths,
                details="Diff inspection shows the guarded edit relative to the checkpoint.",
            )
        )

        with serve_directory(repo_root / "site") as base_url:
            opened = self._orchestrator.invoke_tool(
                coding.session.id,
                ToolInvocationRequest(
                    tool_name="browser_open",
                    arguments={"url": f"{base_url}/index.html", "timeout_ms": 10_000},
                    summary="Opened the fixture page in the browser.",
                ),
            )
            browser_session_id = str(opened.result["session_id"])
            verification = self._orchestrator.invoke_tool(
                coding.session.id,
                ToolInvocationRequest(
                    tool_name="browser_assert_text",
                    arguments={
                        "session_id": browser_session_id,
                        "text": "After Self Test",
                        "selector": "#result",
                    },
                    feature_id=self.FEATURE_ID,
                    verification_kind=VerificationKind.BROWSER,
                    summary="Verified the updated greeting in the browser.",
                ),
            )
            self._orchestrator.invoke_tool(
                coding.session.id,
                ToolInvocationRequest(
                    tool_name="browser_close",
                    arguments={"session_id": browser_session_id},
                    summary="Closed the browser self-test session.",
                ),
            )

        step_results.append(
            HarnessSelfTestStepResult(
                name="browser_verification",
                ok=verification.ok,
                details="Browser verification confirmed the updated greeting in the rendered page.",
            )
        )

        restored = self._orchestrator.restore_session(coding.session.id)
        feature = restored.feature_catalog.features[0] if restored.feature_catalog else None
        context_preview = restored.prompt_context.rendered_context
        context_ok = (
            restored.turn_count >= 5
            and "Updated the browser greeting through a guarded edit." in context_preview
            and "Verified the updated greeting in the browser." in context_preview
        )
        step_results.append(
            HarnessSelfTestStepResult(
                name="context_manager",
                ok=context_ok,
                details="Prompt-ready context retained edit and verification history from the self-test flow.",
            )
        )

        overall_ok = all(step.ok for step in step_results) and feature is not None
        return HarnessSelfTestResult(
            ok=overall_ok and feature.verification_state.status is VerificationStatus.FULLY_VERIFIED,
            repository_root=str(repo_root),
            init_script_path=str(init_script_path),
            features_path=str(features_path),
            checkpoint_ref=checkpoint_ref,
            diff_file_paths=diff_file_paths,
            feature_id=self.FEATURE_ID,
            feature_verification_status=feature.verification_state.status if feature is not None else VerificationStatus.FAILED_VERIFICATION,
            context_preview=context_preview,
            step_results=step_results,
        )

    def _create_fixture_repo(self, working_directory: Path) -> Path:
        repo_root = working_directory / "harness-self-test-repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        (repo_root / "pyproject.toml").write_text(
            "[project]\nname = 'harness-self-test'\nversion = '0.1.0'\n",
            encoding="utf-8",
        )
        stimpact_dir = repo_root / ".stimpactai"
        stimpact_dir.mkdir(exist_ok=True)
        (stimpact_dir / "profile.yml").write_text(
            """
install_command: python -m pip install -r requirements-dev.txt
test_command: python -m pytest
start_command: python -m http.server 8000
environment_assumptions:
  - Python is installed locally.
ignored_directories:
  - .git
  - .venv
language_hints:
  ".js": javascript
  ".py": python
""".strip(),
            encoding="utf-8",
        )
        (repo_root / "requirements-dev.txt").write_text("pytest\n", encoding="utf-8")
        site_root = repo_root / "site"
        site_root.mkdir(exist_ok=True)
        (site_root / "index.html").write_text(
            """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Harness Self Test</title>
  </head>
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
        self._init_git_repo(repo_root)
        return repo_root

    def _init_git_repo(self, repository_root: Path) -> None:
        self._git(repository_root, "init", "-b", "main")
        self._git(repository_root, "config", "user.email", "test@example.com")
        self._git(repository_root, "config", "user.name", "Test User")
        self._git(repository_root, "add", ".")
        self._git(repository_root, "commit", "-m", "initial self-test fixture")

    def _git(self, repository_root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or result.stderr.strip()


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
