from __future__ import annotations

import json

from api.core.errors import APIError
from models.control_plane import RuntimeKind
from services.repo_profile_inference import RepoProfileInferenceResult, infer_repo_profile_from_checkout, infer_repo_profile_from_clone


def test_infer_repo_profile_defaults_for_node_project(tmp_path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "web-app",
                "packageManager": "pnpm@9.0.0",
                "scripts": {
                    "test": "vitest run",
                    "build": "next build",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / "apps").mkdir()
    (tmp_path / "packages").mkdir()

    inferred = infer_repo_profile_from_checkout(tmp_path)

    assert inferred.runtime_kind is RuntimeKind.NODE
    assert inferred.install_command == "pnpm install --frozen-lockfile"
    assert inferred.verify_command == "pnpm test"
    assert inferred.monorepo is True
    assert any("monorepo" in warning.lower() for warning in inferred.warnings)


def test_infer_repo_profile_defaults_for_python_project(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "api"
dependencies = ["fastapi", "pytest"]
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()

    inferred = infer_repo_profile_from_checkout(tmp_path)

    assert inferred.runtime_kind is RuntimeKind.PYTHON
    assert inferred.install_command == "pip install -e ."
    assert inferred.verify_command == "pytest"
    assert inferred.base_image == "public.ecr.aws/docker/library/python:3.12"


def test_infer_repo_profile_defaults_prefers_nested_test_script_for_monorepo(tmp_path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "workspace",
                "private": True,
                "packageManager": "pnpm@9.0.0",
                "workspaces": ["apps/*"],
                "scripts": {
                    "lint": "pnpm -r lint",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    app_dir = tmp_path / "apps" / "web"
    app_dir.mkdir(parents=True)
    (app_dir / "package.json").write_text(
        json.dumps(
            {
                "name": "web",
                "scripts": {
                    "test": "vitest run",
                },
            }
        ),
        encoding="utf-8",
    )

    inferred = infer_repo_profile_from_checkout(tmp_path)

    assert inferred.runtime_kind is RuntimeKind.NODE
    assert inferred.install_command == "pnpm install --frozen-lockfile"
    assert inferred.verify_command == "pnpm --dir apps/web run test"
    assert "package.json scripts in apps/web" in inferred.detected_from


def test_infer_repo_profile_defaults_adds_warning_for_weak_verify_fallback(tmp_path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "web-app",
                "scripts": {
                    "build": "next build",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{\n}\n", encoding="utf-8")

    inferred = infer_repo_profile_from_checkout(tmp_path)

    assert inferred.install_command == "npm ci"
    assert inferred.verify_command == "npm run build"
    assert any("Using `build` as the verify command" in warning for warning in inferred.warnings)


def test_infer_repo_profile_from_clone_retries_common_default_branches(monkeypatch) -> None:
    calls: list[tuple[str, str | None]] = []
    expected = RepoProfileInferenceResult(
        runtime_kind=RuntimeKind.NODE,
        base_image="public.ecr.aws/docker/library/node:20",
        install_command="npm ci",
        reproduce_command="npm test",
        verify_command="npm test",
        detected_from=["package.json scripts"],
        warnings=[],
        monorepo=False,
    )

    def fake_git(args: list[str], *, cwd=None):
        branch = args[args.index("--branch") + 1] if "--branch" in args else args[-1]
        calls.append((args[0], branch))
        if args[0] == "clone" and branch == "stale-branch":
            raise APIError("Remote branch stale-branch was not found.", status_code=502, code="repo_profile_inference_git_failed")
        return ""

    monkeypatch.setattr("services.repo_profile_inference._git", fake_git)
    monkeypatch.setattr("services.repo_profile_inference.infer_repo_profile_from_checkout", lambda _: expected)

    inferred = infer_repo_profile_from_clone(clone_url="https://example.com/repo.git", default_branch="stale-branch")

    assert inferred == expected
    assert ("clone", "stale-branch") in calls
    assert ("clone", "main") in calls
