from __future__ import annotations

import json

from models.control_plane import RuntimeKind
from services.repo_profile_inference import infer_repo_profile_from_checkout


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
