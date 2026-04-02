from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import subprocess
import tempfile

from api.core.errors import APIError
from models.control_plane import RuntimeKind

INFERENCE_ROOT_PATHS = (
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "yarn.lock",
    "bun.lock",
    "bun.lockb",
    "pyproject.toml",
    "requirements.txt",
    "poetry.lock",
    "uv.lock",
    "setup.py",
    "Makefile",
    "Dockerfile",
    "manage.py",
    "tests",
    "apps",
    "packages",
    "frontend",
    "backend",
    "client",
    "server",
    "services",
)


@dataclass(slots=True)
class RepoProfileInferenceResult:
    runtime_kind: RuntimeKind
    base_image: str | None
    install_command: str | None
    reproduce_command: str | None
    verify_command: str | None
    detected_from: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    monorepo: bool = False


def infer_repo_profile_from_clone(
    *,
    clone_url: str,
    default_branch: str,
) -> RepoProfileInferenceResult:
    with tempfile.TemporaryDirectory(prefix="stimpact-repo-inference-") as temp_dir:
        repo_dir = Path(temp_dir) / "repo"
        _git(
            [
                "clone",
                "--quiet",
                "--depth",
                "1",
                "--filter=blob:none",
                "--single-branch",
                "--branch",
                default_branch,
                "--no-checkout",
                clone_url,
                str(repo_dir),
            ],
        )
        _git(["sparse-checkout", "init", "--no-cone"], cwd=repo_dir)
        _git(["sparse-checkout", "set", *INFERENCE_ROOT_PATHS], cwd=repo_dir)
        _git(["checkout", default_branch], cwd=repo_dir)
        return infer_repo_profile_from_checkout(repo_dir)


def infer_repo_profile_from_checkout(repository_root: Path) -> RepoProfileInferenceResult:
    package_json = _load_package_json(repository_root / "package.json")
    pyproject_text = _read_text(repository_root / "pyproject.toml")
    requirements_text = _read_text(repository_root / "requirements.txt")
    makefile_text = _read_text(repository_root / "Makefile")
    dockerfile_exists = (repository_root / "Dockerfile").exists()
    tests_dir_exists = (repository_root / "tests").is_dir()
    manage_py_exists = (repository_root / "manage.py").exists()

    has_node = package_json is not None or any(
        (repository_root / filename).exists()
        for filename in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb")
    )
    has_python = any(
        (repository_root / filename).exists()
        for filename in ("pyproject.toml", "requirements.txt", "poetry.lock", "uv.lock", "setup.py")
    )

    monorepo = _looks_like_monorepo(repository_root, package_json)
    runtime_kind = _detect_runtime_kind(
        has_node=has_node,
        has_python=has_python,
        dockerfile_exists=dockerfile_exists,
    )
    package_manager = _detect_package_manager(repository_root, package_json)

    detected_from: list[str] = []
    warnings: list[str] = []

    install_command = _detect_install_command(
        repository_root=repository_root,
        runtime_kind=runtime_kind,
        package_manager=package_manager,
        package_json=package_json,
        pyproject_text=pyproject_text,
        requirements_text=requirements_text,
    )
    if install_command is not None:
        detected_from.append(_describe_install_source(runtime_kind, package_manager, repository_root, package_json))

    verify_command = _detect_verify_command(
        repository_root=repository_root,
        runtime_kind=runtime_kind,
        package_manager=package_manager,
        package_json=package_json,
        pyproject_text=pyproject_text,
        requirements_text=requirements_text,
        makefile_text=makefile_text,
        tests_dir_exists=tests_dir_exists,
        manage_py_exists=manage_py_exists,
        dockerfile_exists=dockerfile_exists,
    )
    if verify_command is not None:
        detected_from.append(_describe_verify_source(runtime_kind, package_json, makefile_text, dockerfile_exists))
    else:
        warnings.append("A verify command could not be inferred confidently from the repository.")

    if has_node and has_python:
        warnings.append(
            "Multiple runtime ecosystems were detected in this repository. Review the suggested commands carefully.",
        )
    if monorepo:
        warnings.append(
            "This repository looks like a monorepo. If frontend and backend deploy separately, map them as separate services.",
        )

    return RepoProfileInferenceResult(
        runtime_kind=runtime_kind,
        base_image=_default_base_image(runtime_kind),
        install_command=install_command,
        reproduce_command=verify_command,
        verify_command=verify_command,
        detected_from=_dedupe_preserve_order(detected_from),
        warnings=warnings,
        monorepo=monorepo,
    )


def _detect_runtime_kind(
    *,
    has_node: bool,
    has_python: bool,
    dockerfile_exists: bool,
) -> RuntimeKind:
    if has_node and not has_python:
        return RuntimeKind.NODE
    if has_python and not has_node:
        return RuntimeKind.PYTHON
    if has_node and has_python:
        return RuntimeKind.GENERIC
    if dockerfile_exists:
        return RuntimeKind.CONTAINER
    return RuntimeKind.GENERIC


def _detect_package_manager(repository_root: Path, package_json: dict[str, object] | None) -> str:
    package_manager = package_json.get("packageManager") if isinstance(package_json, dict) else None
    if isinstance(package_manager, str):
        normalized = package_manager.lower()
        if normalized.startswith("pnpm"):
            return "pnpm"
        if normalized.startswith("yarn"):
            return "yarn"
        if normalized.startswith("bun"):
            return "bun"
    if (repository_root / "pnpm-lock.yaml").exists() or (repository_root / "pnpm-workspace.yaml").exists():
        return "pnpm"
    if (repository_root / "yarn.lock").exists():
        return "yarn"
    if (repository_root / "bun.lock").exists() or (repository_root / "bun.lockb").exists():
        return "bun"
    if (repository_root / "package-lock.json").exists():
        return "npm"
    return "npm"


def _detect_install_command(
    *,
    repository_root: Path,
    runtime_kind: RuntimeKind,
    package_manager: str,
    package_json: dict[str, object] | None,
    pyproject_text: str | None,
    requirements_text: str | None,
) -> str | None:
    if runtime_kind is RuntimeKind.NODE:
        if package_manager == "pnpm":
            return "pnpm install --frozen-lockfile"
        if package_manager == "yarn":
            return "yarn install --frozen-lockfile"
        if package_manager == "bun":
            return "bun install"
        if (repository_root / "package-lock.json").exists():
            return "npm ci"
        return "npm install"

    if runtime_kind is RuntimeKind.PYTHON:
        if (repository_root / "uv.lock").exists():
            return "uv sync"
        if (repository_root / "poetry.lock").exists():
            return "poetry install"
        if requirements_text is not None:
            return "pip install -r requirements.txt"
        if pyproject_text is not None or (repository_root / "setup.py").exists():
            return "pip install -e ."
        return None

    if runtime_kind is RuntimeKind.CONTAINER and (repository_root / "Dockerfile").exists():
        return "docker build ."

    if package_json is not None:
        return _detect_install_command(
            repository_root=repository_root,
            runtime_kind=RuntimeKind.NODE,
            package_manager=package_manager,
            package_json=package_json,
            pyproject_text=pyproject_text,
            requirements_text=requirements_text,
        )
    if pyproject_text is not None or requirements_text is not None:
        return _detect_install_command(
            repository_root=repository_root,
            runtime_kind=RuntimeKind.PYTHON,
            package_manager=package_manager,
            package_json=package_json,
            pyproject_text=pyproject_text,
            requirements_text=requirements_text,
        )
    return None


def _detect_verify_command(
    *,
    repository_root: Path,
    runtime_kind: RuntimeKind,
    package_manager: str,
    package_json: dict[str, object] | None,
    pyproject_text: str | None,
    requirements_text: str | None,
    makefile_text: str | None,
    tests_dir_exists: bool,
    manage_py_exists: bool,
    dockerfile_exists: bool,
) -> str | None:
    if package_json is not None:
        scripts = package_json.get("scripts")
        if isinstance(scripts, dict):
            for script_name in ("test:ci", "test", "verify", "check", "build", "lint", "typecheck"):
                raw_script = scripts.get(script_name)
                if isinstance(raw_script, str) and raw_script.strip():
                    return _script_command(package_manager, script_name)

    if makefile_text is not None:
        for target in ("test", "verify", "check", "build"):
            if re.search(rf"(?m)^{re.escape(target)}\s*:", makefile_text):
                return f"make {target}"

    if runtime_kind is RuntimeKind.PYTHON or pyproject_text is not None or requirements_text is not None:
        if manage_py_exists:
            return "python manage.py test"
        if tests_dir_exists or _contains_pytest(pyproject_text) or _contains_pytest(requirements_text):
            return "pytest"
        return "python -m unittest"

    if runtime_kind is RuntimeKind.CONTAINER and dockerfile_exists:
        return "docker build ."

    return None


def _contains_pytest(text: str | None) -> bool:
    return bool(text and "pytest" in text.lower())


def _script_command(package_manager: str, script_name: str) -> str:
    if package_manager == "pnpm":
        return f"pnpm {script_name}"
    if package_manager == "yarn":
        return f"yarn {script_name}"
    if package_manager == "bun":
        return f"bun run {script_name}"
    if script_name == "test":
        return "npm test"
    return f"npm run {script_name}"


def _default_base_image(runtime_kind: RuntimeKind) -> str | None:
    if runtime_kind is RuntimeKind.NODE:
        return "public.ecr.aws/docker/library/node:20"
    if runtime_kind is RuntimeKind.PYTHON:
        return "public.ecr.aws/docker/library/python:3.12"
    return None


def _describe_install_source(
    runtime_kind: RuntimeKind,
    package_manager: str,
    repository_root: Path,
    package_json: dict[str, object] | None,
) -> str:
    if runtime_kind is RuntimeKind.NODE:
        if package_json is not None:
            return "package.json and lockfile"
        return f"{package_manager} lockfile"
    if runtime_kind is RuntimeKind.PYTHON:
        if (repository_root / "uv.lock").exists():
            return "uv.lock"
        if (repository_root / "poetry.lock").exists():
            return "poetry.lock"
        if (repository_root / "requirements.txt").exists():
            return "requirements.txt"
        return "pyproject.toml"
    if runtime_kind is RuntimeKind.CONTAINER:
        return "Dockerfile"
    return "repository structure"


def _describe_verify_source(
    runtime_kind: RuntimeKind,
    package_json: dict[str, object] | None,
    makefile_text: str | None,
    dockerfile_exists: bool,
) -> str:
    if package_json is not None:
        return "package.json scripts"
    if makefile_text is not None:
        return "Makefile targets"
    if runtime_kind is RuntimeKind.PYTHON:
        return "python project files"
    if dockerfile_exists:
        return "Dockerfile"
    return "repository structure"


def _looks_like_monorepo(repository_root: Path, package_json: dict[str, object] | None) -> bool:
    if (repository_root / "pnpm-workspace.yaml").exists():
        return True
    if isinstance(package_json, dict) and "workspaces" in package_json:
        return True
    common_monorepo_dirs = ("apps", "packages", "frontend", "backend", "client", "server", "services")
    existing = [name for name in common_monorepo_dirs if (repository_root / name).exists()]
    return len(existing) >= 2 or any(name in {"apps", "packages"} for name in existing)


def _load_package_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _git(args: list[str], *, cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise APIError(
            f"Repository inspection timed out while running git {' '.join(args[:3])}.",
            status_code=504,
            code="repo_profile_inference_timeout",
        ) from exc
    if result.returncode != 0:
        raise APIError(
            (result.stderr or result.stdout or "Git command failed.").strip(),
            status_code=502,
            code="repo_profile_inference_git_failed",
        )
    return (result.stdout or result.stderr).strip()
