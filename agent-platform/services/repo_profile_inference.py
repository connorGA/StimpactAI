from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import subprocess
import tempfile

from api.core.errors import APIError
from models.control_plane import RuntimeKind

_NODE_LOCKFILES = ("package-lock.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", "yarn.lock", "bun.lock", "bun.lockb")
_PYTHON_MANIFESTS = ("pyproject.toml", "requirements.txt", "poetry.lock", "uv.lock", "setup.py")
_COMMON_SCAN_ROOTS = ("apps", "packages", "frontend", "backend", "client", "server", "services", "workers", "api")
_SCAN_FILENAMES = (
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "poetry.lock",
    "uv.lock",
    "setup.py",
    "manage.py",
    "Makefile",
    "Dockerfile",
)
_IGNORE_PARTS = {"node_modules", ".next", ".git", ".venv", "__pycache__", "dist", "build"}
_VERIFY_SCRIPT_PRIORITY = (
    "test:ci",
    "test",
    "test:unit",
    "test:integration",
    "integration",
    "e2e",
    "test:e2e",
    "verify",
    "check",
    "build",
    "lint",
    "typecheck",
)
_WEAK_VERIFY_SCRIPTS = {"build", "lint", "typecheck"}
_MAKEFILE_PRIORITY = ("test", "verify", "check", "build")
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
    ".github",
    "apps",
    "packages",
    "frontend",
    "backend",
    "client",
    "server",
    "services",
    "workers",
    "api",
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


@dataclass(slots=True)
class _ManifestCandidate:
    directory: Path
    relative_path: str
    package_json: dict[str, object] | None
    pyproject_text: str | None
    requirements_text: str | None
    makefile_text: str | None
    dockerfile_exists: bool
    tests_dir_exists: bool
    manage_py_exists: bool
    package_manager: str


@dataclass(slots=True)
class _CommandInference:
    command: str | None
    source: str | None = None
    warning: str | None = None


def infer_repo_profile_from_clone(
    *,
    clone_url: str,
    default_branch: str,
) -> RepoProfileInferenceResult:
    branch_candidates = _dedupe_preserve_order(
        [default_branch.strip(), "main", "master"] if default_branch.strip() else ["main", "master"]
    )
    last_error: APIError | None = None
    for branch_name in branch_candidates:
        try:
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
                        branch_name,
                        "--no-checkout",
                        clone_url,
                        str(repo_dir),
                    ],
                )
                _git(["sparse-checkout", "init", "--no-cone"], cwd=repo_dir)
                _git(["sparse-checkout", "set", *INFERENCE_ROOT_PATHS], cwd=repo_dir)
                _git(["checkout", branch_name], cwd=repo_dir)
                return infer_repo_profile_from_checkout(repo_dir)
        except APIError as exc:
            last_error = exc
            if exc.code != "repo_profile_inference_git_failed":
                raise
    if last_error is not None:
        raise APIError(
            f"Repository inspection could not checkout any candidate branch ({', '.join(branch_candidates)}). "
            f"{last_error.message}",
            status_code=last_error.status_code,
            code=last_error.code,
        ) from last_error
    raise APIError("Repository inspection failed before checkout could begin.", code="repo_profile_inference_git_failed")


def infer_repo_profile_from_checkout(repository_root: Path) -> RepoProfileInferenceResult:
    candidates = _collect_manifest_candidates(repository_root)
    root_candidate = candidates[0]
    has_node = any(_candidate_has_node_signal(candidate, repository_root=repository_root) for candidate in candidates)
    has_python = any(_candidate_has_python_signal(candidate) for candidate in candidates)
    monorepo = _looks_like_monorepo(repository_root, root_candidate.package_json) or len(candidates) > 1
    runtime_kind = _detect_runtime_kind(
        has_node=has_node,
        has_python=has_python,
        dockerfile_exists=any(candidate.dockerfile_exists for candidate in candidates),
    )

    install_inference = _detect_install_command(
        repository_root=repository_root,
        runtime_kind=runtime_kind,
        candidates=candidates,
    )
    verify_inference = _detect_verify_command(
        repository_root=repository_root,
        runtime_kind=runtime_kind,
        candidates=candidates,
    )

    warnings: list[str] = []
    detected_from: list[str] = []
    if install_inference.command is not None and install_inference.source is not None:
        detected_from.append(install_inference.source)
    else:
        warnings.append("An install command could not be inferred confidently from the repository.")
    if install_inference.warning is not None:
        warnings.append(install_inference.warning)

    if verify_inference.command is not None and verify_inference.source is not None:
        detected_from.append(verify_inference.source)
    else:
        warnings.append("A verify command could not be inferred confidently from the repository.")
    if verify_inference.warning is not None:
        warnings.append(verify_inference.warning)

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
        install_command=install_inference.command,
        reproduce_command=verify_inference.command,
        verify_command=verify_inference.command,
        detected_from=_dedupe_preserve_order(detected_from),
        warnings=_dedupe_preserve_order(warnings),
        monorepo=monorepo,
    )


def _collect_manifest_candidates(repository_root: Path) -> list[_ManifestCandidate]:
    candidate_directories = [repository_root, *_discover_nested_candidate_directories(repository_root)]
    seen: set[str] = set()
    candidates: list[_ManifestCandidate] = []
    for directory in candidate_directories:
        relative_path = _relative_path(directory, repository_root)
        if relative_path in seen:
            continue
        seen.add(relative_path)
        candidate = _build_manifest_candidate(directory=directory, repository_root=repository_root)
        if relative_path == "." or _candidate_has_inference_material(candidate, repository_root=repository_root):
            candidates.append(candidate)
    return candidates or [_build_manifest_candidate(directory=repository_root, repository_root=repository_root)]


def _discover_nested_candidate_directories(repository_root: Path) -> list[Path]:
    discovered: list[Path] = []
    seen: set[str] = set()
    for root_name in _COMMON_SCAN_ROOTS:
        scan_root = repository_root / root_name
        if not scan_root.exists() or not scan_root.is_dir():
            continue
        for filename in _SCAN_FILENAMES:
            for candidate_path in scan_root.rglob(filename):
                if any(part in _IGNORE_PARTS for part in candidate_path.parts):
                    continue
                relative = candidate_path.relative_to(repository_root)
                if len(relative.parts) > 4:
                    continue
                parent = candidate_path.parent
                parent_key = parent.relative_to(repository_root).as_posix()
                if parent_key in seen:
                    continue
                seen.add(parent_key)
                discovered.append(parent)
                if len(discovered) >= 20:
                    return sorted(discovered, key=lambda item: (len(item.relative_to(repository_root).parts), item.as_posix()))
    return sorted(discovered, key=lambda item: (len(item.relative_to(repository_root).parts), item.as_posix()))


def _build_manifest_candidate(*, directory: Path, repository_root: Path) -> _ManifestCandidate:
    package_json = _load_package_json(directory / "package.json")
    return _ManifestCandidate(
        directory=directory,
        relative_path=_relative_path(directory, repository_root),
        package_json=package_json,
        pyproject_text=_read_text(directory / "pyproject.toml"),
        requirements_text=_read_text(directory / "requirements.txt"),
        makefile_text=_read_text(directory / "Makefile"),
        dockerfile_exists=(directory / "Dockerfile").exists(),
        tests_dir_exists=(directory / "tests").is_dir(),
        manage_py_exists=(directory / "manage.py").exists(),
        package_manager=_detect_package_manager(directory=directory, repository_root=repository_root, package_json=package_json),
    )


def _candidate_has_inference_material(candidate: _ManifestCandidate, *, repository_root: Path) -> bool:
    return (
        candidate.package_json is not None
        or candidate.pyproject_text is not None
        or candidate.requirements_text is not None
        or candidate.makefile_text is not None
        or candidate.dockerfile_exists
        or candidate.tests_dir_exists
        or candidate.manage_py_exists
        or _candidate_has_node_signal(candidate, repository_root=repository_root)
        or _candidate_has_python_signal(candidate)
    )


def _candidate_has_node_signal(candidate: _ManifestCandidate, *, repository_root: Path) -> bool:
    return candidate.package_json is not None or any(
        (search_root / filename).exists()
        for search_root in (candidate.directory, repository_root)
        for filename in _NODE_LOCKFILES
    )


def _candidate_has_python_signal(candidate: _ManifestCandidate) -> bool:
    return (
        candidate.pyproject_text is not None
        or candidate.requirements_text is not None
        or any((candidate.directory / filename).exists() for filename in ("poetry.lock", "uv.lock", "setup.py"))
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


def _detect_package_manager(
    *,
    directory: Path,
    repository_root: Path,
    package_json: dict[str, object] | None,
) -> str:
    package_manager = package_json.get("packageManager") if isinstance(package_json, dict) else None
    if isinstance(package_manager, str):
        normalized = package_manager.lower()
        if normalized.startswith("pnpm"):
            return "pnpm"
        if normalized.startswith("yarn"):
            return "yarn"
        if normalized.startswith("bun"):
            return "bun"
    for search_root in (directory, repository_root):
        if (search_root / "pnpm-lock.yaml").exists() or (search_root / "pnpm-workspace.yaml").exists():
            return "pnpm"
        if (search_root / "yarn.lock").exists():
            return "yarn"
        if (search_root / "bun.lock").exists() or (search_root / "bun.lockb").exists():
            return "bun"
        if (search_root / "package-lock.json").exists():
            return "npm"
    return "npm"


def _detect_install_command(
    *,
    repository_root: Path,
    runtime_kind: RuntimeKind,
    candidates: list[_ManifestCandidate],
) -> _CommandInference:
    if runtime_kind is RuntimeKind.NODE:
        return _detect_node_install_command(repository_root=repository_root, candidates=candidates)
    if runtime_kind is RuntimeKind.PYTHON:
        return _detect_python_install_command(repository_root=repository_root, candidates=candidates)
    if runtime_kind is RuntimeKind.CONTAINER:
        return _detect_container_install_command(candidates=candidates)

    node_inference = _detect_node_install_command(repository_root=repository_root, candidates=candidates)
    if node_inference.command is not None:
        return node_inference
    python_inference = _detect_python_install_command(repository_root=repository_root, candidates=candidates)
    if python_inference.command is not None:
        return python_inference
    return _detect_container_install_command(candidates=candidates)


def _detect_node_install_command(
    *,
    repository_root: Path,
    candidates: list[_ManifestCandidate],
) -> _CommandInference:
    root_candidate = candidates[0]
    has_root_workspace = _root_prefers_workspace_install(root_candidate, repository_root=repository_root)
    nested_candidate = next((candidate for candidate in candidates if candidate.relative_path != "." and candidate.package_json is not None), None)
    install_package_manager = root_candidate.package_manager if has_root_workspace else (nested_candidate.package_manager if nested_candidate else root_candidate.package_manager)
    if has_root_workspace:
        return _CommandInference(
            command=_node_install_command(
                package_manager=install_package_manager,
                working_directory=".",
                has_lockfile=_directory_has_node_lockfile(repository_root),
            ),
            source=_format_detection_source("package.json and lockfile", "."),
            warning=(
                f"Using the root {install_package_manager} workspace install for nested packages."
                if nested_candidate is not None and nested_candidate.relative_path != "."
                else None
            ),
        )
    if nested_candidate is None:
        return _CommandInference(command=None)
    return _CommandInference(
        command=_node_install_command(
            package_manager=nested_candidate.package_manager,
            working_directory=nested_candidate.relative_path,
            has_lockfile=_directory_has_node_lockfile(nested_candidate.directory),
        ),
        source=_format_detection_source("package.json", nested_candidate.relative_path),
    )


def _detect_python_install_command(
    *,
    repository_root: Path,
    candidates: list[_ManifestCandidate],
) -> _CommandInference:
    for candidate in candidates:
        if (candidate.directory / "uv.lock").exists():
            return _CommandInference(
                command=_with_working_directory("uv sync", candidate.relative_path),
                source=_format_detection_source("uv.lock", candidate.relative_path),
            )
        if (candidate.directory / "poetry.lock").exists():
            return _CommandInference(
                command=_with_working_directory("poetry install", candidate.relative_path),
                source=_format_detection_source("poetry.lock", candidate.relative_path),
            )
        if candidate.requirements_text is not None:
            requirements_path = "requirements.txt" if candidate.relative_path == "." else f"{candidate.relative_path}/requirements.txt"
            return _CommandInference(
                command=f"pip install -r {requirements_path}",
                source=_format_detection_source("requirements.txt", candidate.relative_path),
            )
        if candidate.pyproject_text is not None or (candidate.directory / "setup.py").exists():
            editable_target = "." if candidate.relative_path == "." else candidate.relative_path
            return _CommandInference(
                command=f"pip install -e {editable_target}",
                source=_format_detection_source("pyproject.toml", candidate.relative_path),
            )
    return _CommandInference(command=None)


def _detect_container_install_command(*, candidates: list[_ManifestCandidate]) -> _CommandInference:
    candidate = next((item for item in candidates if item.dockerfile_exists), None)
    if candidate is None:
        return _CommandInference(command=None)
    build_target = "." if candidate.relative_path == "." else candidate.relative_path
    return _CommandInference(
        command=f"docker build {build_target}",
        source=_format_detection_source("Dockerfile", candidate.relative_path),
    )


def _detect_verify_command(
    *,
    repository_root: Path,
    runtime_kind: RuntimeKind,
    candidates: list[_ManifestCandidate],
) -> _CommandInference:
    if runtime_kind is RuntimeKind.NODE:
        return _detect_node_verify_command(repository_root=repository_root, candidates=candidates)
    if runtime_kind is RuntimeKind.PYTHON:
        return _detect_python_verify_command(candidates=candidates)
    if runtime_kind is RuntimeKind.CONTAINER:
        return _detect_container_verify_command(candidates=candidates)

    node_inference = _detect_node_verify_command(repository_root=repository_root, candidates=candidates)
    python_inference = _detect_python_verify_command(candidates=candidates)
    if node_inference.command is not None:
        return node_inference
    if python_inference.command is not None:
        return python_inference
    return _detect_container_verify_command(candidates=candidates)


def _detect_node_verify_command(
    *,
    repository_root: Path,
    candidates: list[_ManifestCandidate],
) -> _CommandInference:
    best_script_choice: tuple[int, int, int, _ManifestCandidate, str] | None = None
    for candidate in candidates:
        scripts = candidate.package_json.get("scripts") if isinstance(candidate.package_json, dict) else None
        if not isinstance(scripts, dict):
            continue
        for priority, script_name in enumerate(_VERIFY_SCRIPT_PRIORITY):
            raw_script = scripts.get(script_name)
            if isinstance(raw_script, str) and raw_script.strip():
                sort_key = (
                    priority,
                    0 if candidate.relative_path == "." else 1,
                    len(candidate.relative_path.split("/")) if candidate.relative_path != "." else 0,
                )
                if best_script_choice is None or sort_key < best_script_choice[:3]:
                    best_script_choice = (*sort_key, candidate, script_name)
                break
    if best_script_choice is not None:
        candidate = best_script_choice[3]
        script_name = best_script_choice[4]
        return _CommandInference(
            command=_node_script_command(
                package_manager=candidate.package_manager,
                script_name=script_name,
                working_directory=candidate.relative_path,
            ),
            source=_format_detection_source("package.json scripts", candidate.relative_path),
            warning=(
                f"Using `{script_name}` as the verify command because no dedicated test script was found."
                if script_name in _WEAK_VERIFY_SCRIPTS
                else None
            ),
        )

    for candidate in candidates:
        if candidate.makefile_text is None:
            continue
        for target in _MAKEFILE_PRIORITY:
            if re.search(rf"(?m)^{re.escape(target)}\s*:", candidate.makefile_text):
                warning = (
                    f"Using `make {target}` as the verify command because no dedicated test command was found."
                    if target == "build"
                    else None
                )
                return _CommandInference(
                    command=_make_command(target=target, working_directory=candidate.relative_path),
                    source=_format_detection_source("Makefile targets", candidate.relative_path),
                    warning=warning,
                )

    return _detect_python_verify_command(candidates=candidates) if any(
        _candidate_has_python_signal(candidate) for candidate in candidates
    ) else _CommandInference(command=None)


def _detect_python_verify_command(*, candidates: list[_ManifestCandidate]) -> _CommandInference:
    for candidate in candidates:
        if candidate.manage_py_exists:
            manage_path = "manage.py" if candidate.relative_path == "." else f"{candidate.relative_path}/manage.py"
            return _CommandInference(
                command=f"python {manage_path} test",
                source=_format_detection_source("Django manage.py", candidate.relative_path),
            )
        if candidate.tests_dir_exists or _contains_pytest(candidate.pyproject_text) or _contains_pytest(candidate.requirements_text):
            if candidate.relative_path == ".":
                command = "pytest"
            else:
                command = f"pytest {candidate.relative_path}/tests" if candidate.tests_dir_exists else _with_working_directory("pytest", candidate.relative_path)
            return _CommandInference(
                command=command,
                source=_format_detection_source("python project files", candidate.relative_path),
            )
        if _candidate_has_python_signal(candidate):
            return _CommandInference(
                command="python -m unittest" if candidate.relative_path == "." else f"python -m unittest discover {candidate.relative_path}",
                source=_format_detection_source("python project files", candidate.relative_path),
                warning="Falling back to unittest because no explicit pytest or Django test command was found.",
            )
    return _CommandInference(command=None)


def _detect_container_verify_command(*, candidates: list[_ManifestCandidate]) -> _CommandInference:
    candidate = next((item for item in candidates if item.dockerfile_exists), None)
    if candidate is None:
        return _CommandInference(command=None)
    build_target = "." if candidate.relative_path == "." else candidate.relative_path
    return _CommandInference(
        command=f"docker build {build_target}",
        source=_format_detection_source("Dockerfile", candidate.relative_path),
        warning="Using `docker build` as the verify command because no test runner was detected.",
    )


def _contains_pytest(text: str | None) -> bool:
    return bool(text and "pytest" in text.lower())


def _node_install_command(*, package_manager: str, working_directory: str, has_lockfile: bool) -> str:
    if working_directory == ".":
        if package_manager == "pnpm":
            return "pnpm install --frozen-lockfile"
        if package_manager == "yarn":
            return "yarn install --frozen-lockfile"
        if package_manager == "bun":
            return "bun install"
        return "npm ci" if has_lockfile else "npm install"
    if package_manager == "pnpm":
        return f"pnpm --dir {working_directory} install --frozen-lockfile"
    if package_manager == "yarn":
        return f"yarn --cwd {working_directory} install --frozen-lockfile"
    if package_manager == "bun":
        return f"cd {working_directory} && bun install"
    return f"npm --prefix {working_directory} {'ci' if has_lockfile else 'install'}"


def _node_script_command(*, package_manager: str, script_name: str, working_directory: str) -> str:
    if working_directory == ".":
        if package_manager == "pnpm":
            return f"pnpm {script_name}" if script_name == "test" else f"pnpm run {script_name}"
        if package_manager == "yarn":
            return f"yarn {script_name}" if script_name == "test" else f"yarn run {script_name}"
        if package_manager == "bun":
            return f"bun run {script_name}"
        return "npm test" if script_name == "test" else f"npm run {script_name}"
    if package_manager == "pnpm":
        return f"pnpm --dir {working_directory} run {script_name}"
    if package_manager == "yarn":
        return f"yarn --cwd {working_directory} run {script_name}"
    if package_manager == "bun":
        return f"cd {working_directory} && bun run {script_name}"
    return f"npm --prefix {working_directory} {'test' if script_name == 'test' else f'run {script_name}'}"


def _make_command(*, target: str, working_directory: str) -> str:
    return f"make {target}" if working_directory == "." else f"cd {working_directory} && make {target}"


def _with_working_directory(command: str, working_directory: str) -> str:
    return command if working_directory == "." else f"cd {working_directory} && {command}"


def _directory_has_node_lockfile(directory: Path) -> bool:
    return any((directory / filename).exists() for filename in _NODE_LOCKFILES if filename != "pnpm-workspace.yaml")


def _root_prefers_workspace_install(candidate: _ManifestCandidate, *, repository_root: Path) -> bool:
    if _directory_has_node_lockfile(repository_root) or (repository_root / "pnpm-workspace.yaml").exists():
        return True
    if not isinstance(candidate.package_json, dict):
        return False
    if candidate.package_json.get("workspaces"):
        return True
    return any(candidate.package_json.get(key) for key in ("dependencies", "devDependencies"))


def _default_base_image(runtime_kind: RuntimeKind) -> str | None:
    if runtime_kind is RuntimeKind.NODE:
        return "public.ecr.aws/docker/library/node:20"
    if runtime_kind is RuntimeKind.PYTHON:
        return "public.ecr.aws/docker/library/python:3.12"
    return None


def _format_detection_source(label: str, relative_path: str) -> str:
    return label if relative_path == "." else f"{label} in {relative_path}"


def _looks_like_monorepo(repository_root: Path, package_json: dict[str, object] | None) -> bool:
    if (repository_root / "pnpm-workspace.yaml").exists():
        return True
    if isinstance(package_json, dict) and "workspaces" in package_json:
        return True
    existing = [name for name in _COMMON_SCAN_ROOTS if (repository_root / name).exists()]
    return len(existing) >= 2 or any(name in {"apps", "packages"} for name in existing)


def _relative_path(path: Path, repository_root: Path) -> str:
    relative = path.relative_to(repository_root)
    return relative.as_posix() or "."


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
        if not value or value in seen:
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
            (result.stderr or result.stdout or f"Git command failed while running {' '.join(args[:3])}.").strip(),
            status_code=502,
            code="repo_profile_inference_git_failed",
        )
    return (result.stdout or result.stderr).strip()
