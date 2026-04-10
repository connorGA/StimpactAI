from __future__ import annotations

import json
from pathlib import Path

from services.sdk_bootstrap import SdkBootstrapPlannedFile, SdkBootstrapStrategy, plan_sdk_bootstrap_from_checkout
from services.sdk_bootstrap_harness import (
    SdkBootstrapHarnessTarget,
    compile_safe_change_policy,
    decode_preview_artifact,
    encode_preview_artifact,
)


def test_next_repo_fixture_uses_browser_recipe_with_heartbeat(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "package.json",
        {
            "name": "web-app",
            "dependencies": {
                "next": "15.0.0",
                "react": "19.0.0",
                "react-dom": "19.0.0",
            },
        },
    )
    app_dir = tmp_path / "src" / "app"
    app_dir.mkdir(parents=True)
    (app_dir / "layout.tsx").write_text(
        "export default function RootLayout({ children }) { return <html><body>{children}</body></html>; }\n",
        encoding="utf-8",
    )

    plan = plan_sdk_bootstrap_from_checkout(
        repo_dir=tmp_path,
        project_id="project-1",
        service_name="web-app",
        environment="production",
        base_url="https://stimpact.example.com",
    )

    assert plan.strategies
    strategy = plan.strategies[0]
    assert strategy.id.startswith("javascript-next:")
    assert strategy.framework == "Next.js"
    assert any("heartbeat" in step.content.lower() for step in strategy.manual_steps)
    assert any("pingstimpact" in step.content.lower() for step in strategy.manual_steps)
    assert strategy.preview_snippet is not None
    assert "export async function pingStimpact" in strategy.preview_snippet
    assert "scope.pingStimpact = pingStimpact" in strategy.preview_snippet
    assert any("provider" in item.reason.lower() for item in strategy.planned_files)


def test_fastapi_repo_fixture_uses_python_recipe_with_heartbeat(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("fastapi==0.111.0\nuvicorn==0.30.0\n", encoding="utf-8")
    (tmp_path / "main.py").write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/health')\ndef health():\n    return {'ok': True}\n",
        encoding="utf-8",
    )

    plan = plan_sdk_bootstrap_from_checkout(
        repo_dir=tmp_path,
        project_id="project-1",
        service_name="billing-api",
        environment="production",
        base_url="https://stimpact.example.com",
    )

    assert plan.strategies
    strategy = next(item for item in plan.strategies if item.language == "python")
    assert strategy.id.startswith("python-fastapi:")
    assert strategy.framework == "FastAPI"
    assert any("heartbeat" in step.content.lower() for step in strategy.manual_steps)


def test_unsupported_repo_fixture_stays_manual_only(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Notes only\n", encoding="utf-8")

    plan = plan_sdk_bootstrap_from_checkout(
        repo_dir=tmp_path,
        project_id="project-1",
        service_name="notes",
        environment="production",
        base_url="https://stimpact.example.com",
    )

    assert plan.strategies == []
    assert any("No supported JavaScript or Python" in warning for warning in plan.warnings)


def test_safe_change_policy_blocks_deployment_surface_changes() -> None:
    strategy = SdkBootstrapStrategy(
        id="fixture",
        language="javascript",
        framework="Express",
        summary="Fixture",
        confidence="high",
        pr_supported=True,
        target_subpath=".",
        planned_files=[
            SdkBootstrapPlannedFile(path="Dockerfile", action="update", reason="Rewrite container entrypoint."),
            SdkBootstrapPlannedFile(path="src/index.ts", action="update", reason="Install SDK."),
        ],
    )

    policy = compile_safe_change_policy(strategy=strategy)

    assert "deployment_surface" in policy.prohibited_categories
    assert policy.requires_manual_review is True


def test_preview_artifact_round_trip_preserves_exact_patch_bundle() -> None:
    artifact = encode_preview_artifact(
        secret="test-secret",
        strategy_id="nextjs",
        target=SdkBootstrapHarnessTarget(
            project_id="project-1",
            provider_repository_id="provider-repo-1",
            service="web-app",
            environment="production",
            base_url="https://stimpact.example.com",
        ),
        safe_change_policy=compile_safe_change_policy(
            strategy=SdkBootstrapStrategy(
                id="nextjs",
                language="javascript",
                framework="Next.js",
                summary="Fixture",
                confidence="high",
                pr_supported=True,
                target_subpath=".",
                planned_files=[SdkBootstrapPlannedFile(path="src/app/layout.tsx", action="update", reason="Install SDK.")],
            )
        ),
        patch_diff="diff --git a/file b/file\n+hello\n",
        branch_name="stimpact/sdk-bootstrap-preview",
        credential_kind="api_key",
        framework="Next.js",
        summary="Install SDK",
        entrypoints=["src/app/layout.tsx"],
        attempt={
            "strategy_id": "nextjs",
            "patch_source": "deterministic",
            "patch_generated": True,
            "patch_applied": True,
            "verification": {"status": "passed", "summary": "ok", "command": None, "output": None},
            "preview_available": True,
            "change_request_allowed": True,
            "changed_files": ["src/app/layout.tsx"],
            "warnings": [],
            "failure_stage": None,
            "failure_reason": None,
            "rejection_reason_code": None,
            "attempt_number": 1,
            "candidate_id": "nextjs",
            "generation_duration_ms": 10,
            "apply_duration_ms": 10,
            "verification_duration_ms": 10,
        },
    )

    payload = decode_preview_artifact(secret="test-secret", artifact_id=artifact.artifact_id)

    assert payload["patch_diff"] == "diff --git a/file b/file\n+hello\n"
    assert payload["target"]["service"] == "web-app"
    assert artifact.checksum is not None


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
