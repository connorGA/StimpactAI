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


def test_react_scripts_repo_gets_deterministic_auto_strategy() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir)
        (repo_dir / "package.json").write_text(
            json.dumps(
                {
                    "dependencies": {
                        "react": "18.0.0",
                        "react-dom": "18.0.0",
                        "react-scripts": "5.0.1",
                    }
                }
            ),
            encoding="utf-8",
        )
        (repo_dir / "src").mkdir(parents=True)
        (repo_dir / "src/index.tsx").write_text(
            "import ReactDOM from 'react-dom/client';\nReactDOM.createRoot(document.getElementById('root')!).render(null);\n",
            encoding="utf-8",
        )

        plan = plan_sdk_bootstrap_from_checkout(
            repo_dir=repo_dir,
            project_id="project-1",
            service_name="web-app",
            environment="production",
            base_url="https://stimpact.example.com",
            fallback_planner=None,
        )

        assert plan.recommended_strategy_id == "javascript-react-scripts:.:src/index.tsx"
        strategy = plan.strategies[0]
        assert strategy.framework == "React SPA"
        assert strategy.pr_supported is True
        assert strategy.entrypoints == ["src/index.tsx"]


def test_react_scripts_monorepo_bootstrap_entrypoint_gets_deterministic_strategy() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir)
        (repo_dir / "apps/web/src").mkdir(parents=True)
        (repo_dir / "apps/web/package.json").write_text(
            json.dumps(
                {
                    "dependencies": {
                        "react": "18.0.0",
                        "react-dom": "18.0.0",
                        "react-scripts": "5.0.1",
                    }
                }
            ),
            encoding="utf-8",
        )
        (repo_dir / "apps/web/src/bootstrap.tsx").write_text(
            "import { createRoot } from 'react-dom/client';\ncreateRoot(document.getElementById('root')!).render(null);\n",
            encoding="utf-8",
        )

        plan = plan_sdk_bootstrap_from_checkout(
            repo_dir=repo_dir,
            project_id="project-1",
            service_name="web-app",
            environment="production",
            base_url="https://stimpact.example.com",
            fallback_planner=None,
        )

        assert plan.recommended_strategy_id == "javascript-react-scripts:apps/web:src/bootstrap.tsx"
        assert plan.strategies[0].entrypoints == ["apps/web/src/bootstrap.tsx"]
        assert plan.strategies[0].pr_supported is True


def test_vite_repo_with_client_root_gets_deterministic_strategy() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir)
        (repo_dir / "client/src").mkdir(parents=True)
        (repo_dir / "package.json").write_text(
            json.dumps(
                {
                    "dependencies": {
                        "react": "18.0.0",
                        "react-dom": "18.0.0",
                        "vite": "5.0.0",
                    }
                }
            ),
            encoding="utf-8",
        )
        (repo_dir / "vite.config.ts").write_text(
            'import path from "path";\nexport default { root: path.resolve(import.meta.dirname, "client") };\n',
            encoding="utf-8",
        )
        (repo_dir / "client/src/main.tsx").write_text(
            'import { createRoot } from "react-dom/client";\ncreateRoot(document.getElementById("root")!).render(null);\n',
            encoding="utf-8",
        )

        plan = plan_sdk_bootstrap_from_checkout(
            repo_dir=repo_dir,
            project_id="project-1",
            service_name="web-app",
            environment="production",
            base_url="https://stimpact.example.com",
            fallback_planner=None,
        )

        assert plan.recommended_strategy_id == "javascript-vite-react:.:client/src/main.tsx"
        strategy = next(item for item in plan.strategies if item.id == "javascript-vite-react:.:client/src/main.tsx")
        assert strategy.pr_supported is True
        assert strategy.entrypoints == ["client/src/main.tsx"]


def test_generic_javascript_repo_gets_process_level_auto_strategy() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir)
        (repo_dir / "package.json").write_text(
            json.dumps(
                {
                    "main": "server.js",
                    "scripts": {"start": "node server.js"},
                }
            ),
            encoding="utf-8",
        )
        (repo_dir / "server.js").write_text(
            "const http = require('http');\nhttp.createServer(() => {}).listen(3000);\n",
            encoding="utf-8",
        )

        plan = plan_sdk_bootstrap_from_checkout(
            repo_dir=repo_dir,
            project_id="project-1",
            service_name="api",
            environment="production",
            base_url="https://stimpact.example.com",
            fallback_planner=None,
        )

        assert plan.recommended_strategy_id == "javascript-generic-auto:.:server.js"
        strategy = next(item for item in plan.strategies if item.id == "javascript-generic-auto:.:server.js")
        assert strategy.pr_supported is True
        assert strategy.framework == "JavaScript application"
        assert strategy.entrypoints == ["server.js"]


def test_fastapi_repo_with_requirements_in_remains_pr_capable() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir)
        (repo_dir / "service").mkdir()
        (repo_dir / "service/requirements.in").write_text("fastapi\nuvicorn\n", encoding="utf-8")
        (repo_dir / "service/main.py").write_text(
            "from fastapi import FastAPI\n\napp = FastAPI()\n",
            encoding="utf-8",
        )

        plan = plan_sdk_bootstrap_from_checkout(
            repo_dir=repo_dir,
            project_id="project-1",
            service_name="billing-api",
            environment="production",
            base_url="https://stimpact.example.com",
            fallback_planner=None,
        )

        assert plan.recommended_strategy_id == "python-fastapi:service:main.py"
        strategy = plan.strategies[0]
        assert strategy.pr_supported is True
        assert any(item.path == "service/requirements.in" for item in strategy.planned_files)


def test_fallback_prompt_payload_includes_repo_topology_and_bootstrap_candidates() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir)
        (repo_dir / "apps/web/src").mkdir(parents=True)
        (repo_dir / "apps/web/package.json").write_text(
            json.dumps({"dependencies": {"react": "18.0.0", "react-dom": "18.0.0"}}),
            encoding="utf-8",
        )
        (repo_dir / "package-lock.json").write_text("{}", encoding="utf-8")
        (repo_dir / "apps/web/src/bootstrap.tsx").write_text(
            "import { createRoot } from 'react-dom/client';\ncreateRoot(document.getElementById('root')!).render(null);\n",
            encoding="utf-8",
        )
        planner = SdkBootstrapFallbackPlanner(
            client=RecordingOpenAIClient({"proposal": None}),
            model="fallback-model",
        )

        payload = planner._build_prompt_payload(
            repo_dir=repo_dir,
            project_id="project-1",
            service_name="web-app",
            environment="production",
            base_url="https://stimpact.example.com",
        )

        repo_topology = payload["repo_topology"]
        assert repo_topology["package_roots"] == ["apps/web"]
        assert "npm" in repo_topology["package_managers"]
        assert any(item["path"] == "apps/web/src/bootstrap.tsx" for item in payload["candidate_files"])


def test_package_script_hints_raise_candidate_file_priority() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir)
        (repo_dir / "apps/web/src").mkdir(parents=True)
        (repo_dir / "apps/web/package.json").write_text(
            json.dumps(
                {
                    "scripts": {
                        "dev": "node apps/web/src/entry-server.js",
                    }
                }
            ),
            encoding="utf-8",
        )
        (repo_dir / "apps/web/src/entry-server.js").write_text(
            "console.log('boot');\n",
            encoding="utf-8",
        )

        payload = SdkBootstrapFallbackPlanner(
            client=RecordingOpenAIClient({"proposal": None}),
            model="fallback-model",
        )._build_prompt_payload(
            repo_dir=repo_dir,
            project_id="project-1",
            service_name="web-app",
            environment="production",
            base_url="https://stimpact.example.com",
        )

        assert any(
            item["path"] == "apps/web/src/entry-server.js" and "package scripts" in item["reason"]
            for item in payload["candidate_files"]
        )


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


def test_fallback_accepts_requirements_in_and_env_example_patch_surfaces() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir)
        (repo_dir / "service").mkdir()
        (repo_dir / "service/requirements.in").write_text("fastapi\n", encoding="utf-8")
        (repo_dir / "service/main.py").write_text(
            "from fastapi import FastAPI\n\napp = FastAPI()\n",
            encoding="utf-8",
        )
        planner = SdkBootstrapFallbackPlanner(
            client=RecordingOpenAIClient(
                {
                    "proposal": {
                        "framework_id": "python-fastapi",
                        "summary": "Wire Stimpact into the FastAPI entrypoint.",
                        "confidence": "high",
                        "confidence_reason": "main.py owns the ASGI app and requirements.in manages dependencies.",
                        "target_subpath": "service",
                        "entrypoint": "service/main.py",
                        "evidence": ["service/main.py", "service/requirements.in"],
                        "assumptions": [],
                        "blockers": [],
                        "planned_files": [
                            {
                                "path": "service/main.py",
                                "action": "update",
                                "reason": "Install middleware hook.",
                            },
                            {
                                "path": "service/requirements.in",
                                "action": "update",
                                "reason": "Add stimpact-sdk dependency.",
                            },
                            {
                                "path": "service/.env.production.example",
                                "action": "create",
                                "reason": "Document example runtime configuration.",
                            },
                            {
                                "path": "service/stimpact_bootstrap.py",
                                "action": "create",
                                "reason": "Add helper bootstrap module.",
                            },
                        ],
                        "preview_snippet": "from stimpact_sdk import StimpactClient",
                        "patch_diff": "\n".join(
                            [
                                "diff --git a/service/main.py b/service/main.py",
                                "--- a/service/main.py",
                                "+++ b/service/main.py",
                                "@@ -1,3 +1,4 @@",
                                " from fastapi import FastAPI",
                                "+from .stimpact_bootstrap import configure_stimpact",
                                " ",
                                " app = FastAPI()",
                                "+configure_stimpact(app)",
                                "diff --git a/service/requirements.in b/service/requirements.in",
                                "--- a/service/requirements.in",
                                "+++ b/service/requirements.in",
                                "@@ -1 +1,2 @@",
                                " fastapi",
                                "+stimpact-sdk",
                                "diff --git a/service/.env.production.example b/service/.env.production.example",
                                "--- /dev/null",
                                "+++ b/service/.env.production.example",
                                "@@ -0,0 +1,2 @@",
                                "+STIMPACT_BASE_URL=https://stimpact.example.com",
                                "+STIMPACT_PROJECT_ID=project-1",
                                "diff --git a/service/stimpact_bootstrap.py b/service/stimpact_bootstrap.py",
                                "--- /dev/null",
                                "+++ b/service/stimpact_bootstrap.py",
                                "@@ -0,0 +1,2 @@",
                                "+def configure_stimpact(app):",
                                "+    return app",
                            ]
                        ),
                        "pr_supported": True,
                    }
                }
            ),
            model="fallback-model",
        )

        proposal = planner.plan(
            repo_dir=repo_dir,
            project_id="project-1",
            service_name="billing-api",
            environment="production",
            base_url="https://stimpact.example.com",
        )

        assert proposal is not None
        assert proposal.pr_supported is True
        assert "service/.env.production.example" in [item.path for item in proposal.planned_files]


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
