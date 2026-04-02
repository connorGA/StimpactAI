from __future__ import annotations

import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

from services.sdk_bootstrap import build_sdk_bootstrap_patch_from_clone, plan_sdk_bootstrap_from_checkout
from services.sdk_bootstrap_fallback import (
    SdkBootstrapFallbackPlannedFile,
    SdkBootstrapFallbackPlanner,
    SdkBootstrapFallbackProposal,
)


class StubFallbackPlanner:
    def __init__(self, proposal: SdkBootstrapFallbackProposal | None) -> None:
        self.calls = 0
        self._proposal = proposal

    def plan(self, **_: object) -> SdkBootstrapFallbackProposal | None:
        self.calls += 1
        return self._proposal


class RecordingOpenAIClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.chat = SimpleNamespace(completions=_RecordingCompletions(json.dumps(payload)))


class _RecordingCompletions:
    def __init__(self, content: str) -> None:
        self._content = content

    def create(self, **kwargs: object) -> object:
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


def test_deterministic_strategy_remains_preferred_when_supported_entrypoint_exists() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir)
        (repo_dir / "package.json").write_text(
            json.dumps({"dependencies": {"next": "15.0.0"}}),
            encoding="utf-8",
        )
        (repo_dir / "src/app").mkdir(parents=True)
        (repo_dir / "src/app/layout.tsx").write_text(
            "export default function RootLayout({ children }) { return children; }\n",
            encoding="utf-8",
        )
        fallback = StubFallbackPlanner(
            SdkBootstrapFallbackProposal(
                framework_id="javascript-generic",
                summary="Fallback summary",
                confidence="medium",
                confidence_reason="Fallback should never be used here.",
                target_subpath=".",
                entrypoint="src/main.tsx",
                evidence=["src/main.tsx"],
                assumptions=[],
                blockers=[],
                planned_files=[
                    SdkBootstrapFallbackPlannedFile(
                        path="src/main.tsx",
                        action="update",
                        reason="Bootstrap runtime.",
                    )
                ],
                preview_snippet="import '@stimpact/sdk';",
                patch_diff="diff --git a/src/main.tsx b/src/main.tsx\n--- a/src/main.tsx\n+++ b/src/main.tsx\n@@ -1 +1,2 @@\n+console.log('stimpact')\n",
                pr_supported=True,
            )
        )

        plan = plan_sdk_bootstrap_from_checkout(
            repo_dir=repo_dir,
            project_id="project-1",
            service_name="web-app",
            environment="production",
            base_url="https://stimpact.example.com",
            fallback_planner=fallback,
        )

        assert fallback.calls == 0
        assert plan.recommended_strategy_id == "javascript-next:.:src/app/layout.tsx"
        assert all(item.source == "deterministic" for item in plan.strategies)


def test_fallback_is_used_only_when_deterministic_plan_is_manual_only() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir)
        (repo_dir / "package.json").write_text(
            json.dumps({"dependencies": {"react": "18.0.0"}}),
            encoding="utf-8",
        )
        (repo_dir / "src").mkdir(parents=True)
        (repo_dir / "src/bootstrap.tsx").write_text(
            "import { createRoot } from 'react-dom/client';\ncreateRoot(document.getElementById('root')!).render(null);\n",
            encoding="utf-8",
        )
        fallback = StubFallbackPlanner(
            SdkBootstrapFallbackProposal(
                framework_id="javascript-generic",
                summary="Wire the SDK into src/bootstrap.tsx.",
                confidence="medium",
                confidence_reason="The file mounts the React root.",
                target_subpath=".",
                entrypoint="src/bootstrap.tsx",
                evidence=["src/bootstrap.tsx", "package.json"],
                assumptions=["This is the browser entrypoint."],
                blockers=[],
                planned_files=[
                    SdkBootstrapFallbackPlannedFile(
                        path="src/bootstrap.tsx",
                        action="update",
                        reason="Initialize Stimpact before the app renders.",
                    )
                ],
                preview_snippet="import { StimpactClient } from '@stimpact/sdk';",
                patch_diff="diff --git a/src/bootstrap.tsx b/src/bootstrap.tsx\n--- a/src/bootstrap.tsx\n+++ b/src/bootstrap.tsx\n@@ -1,2 +1,3 @@\n import { createRoot } from 'react-dom/client';\n+console.log('stimpact');\n createRoot(document.getElementById('root')!).render(null);\n",
                pr_supported=True,
            )
        )

        plan = plan_sdk_bootstrap_from_checkout(
            repo_dir=repo_dir,
            project_id="project-1",
            service_name="web-app",
            environment="production",
            base_url="https://stimpact.example.com",
            fallback_planner=fallback,
        )

        assert fallback.calls == 1
        assert any(item.source == "llm" for item in plan.strategies)
        llm_strategy = next(item for item in plan.strategies if item.source == "llm")
        assert llm_strategy.pr_supported is True
        assert llm_strategy.confidence_reason == "The file mounts the React root."
        assert plan.recommended_strategy_id == llm_strategy.id


def test_invalid_model_output_is_rejected_safely() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir)
        (repo_dir / "package.json").write_text(
            json.dumps({"dependencies": {"react": "18.0.0"}}),
            encoding="utf-8",
        )
        (repo_dir / "src").mkdir(parents=True)
        (repo_dir / "src/bootstrap.tsx").write_text(
            "import { createRoot } from 'react-dom/client';\ncreateRoot(document.getElementById('root')!).render(null);\n",
            encoding="utf-8",
        )
        planner = SdkBootstrapFallbackPlanner(
            client=RecordingOpenAIClient(
                {
                    "proposal": {
                        "framework_id": "javascript-generic",
                        "summary": "Try to touch a blocked lockfile.",
                        "confidence": "high",
                        "confidence_reason": "The repo has a package.json entrypoint.",
                        "target_subpath": ".",
                        "entrypoint": "src/bootstrap.tsx",
                        "evidence": ["src/bootstrap.tsx"],
                        "assumptions": [],
                        "blockers": [],
                        "planned_files": [
                            {
                                "path": "package-lock.json",
                                "action": "update",
                                "reason": "This should be blocked.",
                            }
                        ],
                        "preview_snippet": "import { StimpactClient } from '@stimpact/sdk';",
                        "patch_diff": "diff --git a/package-lock.json b/package-lock.json\n--- a/package-lock.json\n+++ b/package-lock.json\n@@ -0,0 +1 @@\n+{}\n",
                        "pr_supported": True,
                    }
                }
            ),
            model="fallback-model",
        )

        proposal = planner.plan(
            repo_dir=repo_dir,
            project_id="project-1",
            service_name="web-app",
            environment="production",
            base_url="https://stimpact.example.com",
        )

        assert proposal is not None
        assert proposal.pr_supported is False
        assert proposal.patch_diff is None
        assert any("guardrails" in blocker for blocker in proposal.blockers)


def test_validated_fallback_patch_flows_through_build_path(monkeypatch: pytest.MonkeyPatch) -> None:
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        import services.sdk_bootstrap as sdk_bootstrap_module

        repo_dir = Path(temp_dir) / "repo"
        repo_dir.mkdir()
        (repo_dir / "package.json").write_text(
            json.dumps({"dependencies": {"react": "18.0.0"}}),
            encoding="utf-8",
        )
        (repo_dir / "src").mkdir(parents=True)
        (repo_dir / "src/bootstrap.tsx").write_text(
            "import { createRoot } from 'react-dom/client';\ncreateRoot(document.getElementById('root')!).render(null);\n",
            encoding="utf-8",
        )

        def fake_git(args: list[str], *, cwd: Path | None = None) -> str:
            if args and args[0] == "clone":
                shutil.copytree(repo_dir, Path(args[-1]))
                return ""
            return ""

        monkeypatch.setattr(sdk_bootstrap_module, "_git", fake_git)

        fallback = StubFallbackPlanner(
            SdkBootstrapFallbackProposal(
                framework_id="javascript-generic",
                summary="Wire the SDK into src/bootstrap.tsx.",
                confidence="medium",
                confidence_reason="The file mounts the React root.",
                target_subpath=".",
                entrypoint="src/bootstrap.tsx",
                evidence=["src/bootstrap.tsx", "package.json"],
                assumptions=[],
                blockers=[],
                planned_files=[
                    SdkBootstrapFallbackPlannedFile(
                        path="src/bootstrap.tsx",
                        action="update",
                        reason="Initialize Stimpact before the app renders.",
                    )
                ],
                preview_snippet="import { StimpactClient } from '@stimpact/sdk';",
                patch_diff="diff --git a/src/bootstrap.tsx b/src/bootstrap.tsx\n--- a/src/bootstrap.tsx\n+++ b/src/bootstrap.tsx\n@@ -1,2 +1,3 @@\n import { createRoot } from 'react-dom/client';\n+console.log('stimpact');\n createRoot(document.getElementById('root')!).render(null);\n",
                pr_supported=True,
            )
        )

        patch = build_sdk_bootstrap_patch_from_clone(
            clone_url="local-repo",
            default_branch="main",
            project_id="project-1",
            service_name="web-app",
            environment="production",
            base_url="https://stimpact.example.com",
            strategy_id="llm:javascript-generic:.:src/bootstrap.tsx",
            fallback_planner=fallback,
        )

        assert fallback.calls >= 1
        assert "src/bootstrap.tsx" in patch.patch_diff
