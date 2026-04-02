from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
import subprocess

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from services.sdk_catalog import SdkFrameworkSpec, get_framework_spec

_MAX_FALLBACK_PATCH_FILES = 6
_MAX_FALLBACK_PATCH_LINES = 320
_ALLOWED_PATCH_EXTENSIONS = {
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".mts",
    ".cts",
    ".py",
    ".json",
    ".toml",
    ".txt",
    ".example",
}
_BLOCKED_PATCH_FILENAMES = {
    "package-lock.json",
    "poetry.lock",
    "Pipfile.lock",
    "yarn.lock",
    "pnpm-lock.yaml",
}
_SUPPORTED_FRAMEWORK_IDS = {
    "javascript-next",
    "javascript-react-scripts",
    "javascript-generic",
    "javascript-vite-react",
    "python-fastapi",
    "python-flask",
    "python-generic",
}
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SdkBootstrapFallbackPlannedFile:
    path: str
    action: str
    reason: str


@dataclass(slots=True)
class SdkBootstrapFallbackProposal:
    framework_id: str
    summary: str
    confidence: str
    confidence_reason: str
    target_subpath: str
    entrypoint: str
    evidence: list[str]
    assumptions: list[str]
    blockers: list[str]
    planned_files: list[SdkBootstrapFallbackPlannedFile]
    preview_snippet: str | None
    patch_diff: str | None
    pr_supported: bool


class SdkBootstrapFallbackPlanner:
    def __init__(self, *, client: OpenAI, model: str) -> None:
        self._client = client
        self._model = model

    def plan(
        self,
        *,
        repo_dir: Path,
        service_name: str,
        environment: str,
        project_id: str,
        base_url: str,
    ) -> SdkBootstrapFallbackProposal | None:
        proposals = self.plan_candidates(
            repo_dir=repo_dir,
            service_name=service_name,
            environment=environment,
            project_id=project_id,
            base_url=base_url,
        )
        return proposals[0] if proposals else None

    def plan_candidates(
        self,
        *,
        repo_dir: Path,
        service_name: str,
        environment: str,
        project_id: str,
        base_url: str,
    ) -> list[SdkBootstrapFallbackProposal]:
        prompt_payload = self._build_prompt_payload(
            repo_dir=repo_dir,
            service_name=service_name,
            environment=environment,
            project_id=project_id,
            base_url=base_url,
        )
        if not prompt_payload["candidate_files"]:
            logger.info("sdk_bootstrap_fallback_rejected reason=no_candidate_files")
            return []

        completion = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are planning a safe SDK bootstrap patch for Stimpact. "
                        "Use only the grounded repo context provided. "
                        "Return raw JSON with a key named proposals containing up to 3 ranked candidate strategies. "
                        "Each proposal must describe one plausible runtime insertion surface. "
                        "Prefer concrete, executable candidates over giving up early. "
                        "Only propose a PR-capable patch when you can identify a concrete runtime entrypoint and keep the diff localized. "
                        "Never touch lockfiles, generated assets, tests, CI, docker, or unrelated files. "
                        "Allowed modified surfaces are existing runtime entrypoints, package/dependency manifests, .env.example, "
                        "and at most one small helper file whose filename contains 'stimpact'. "
                        f"The patch_diff must be a valid unified diff touching no more than {_MAX_FALLBACK_PATCH_FILES} files "
                        f"and {_MAX_FALLBACK_PATCH_LINES} changed lines total. "
                        f"Use framework_id from this allowlist only: {', '.join(sorted(_SUPPORTED_FRAMEWORK_IDS))}. "
                        "If a proposal is ambiguous, keep it reviewable with blockers instead of inventing unrelated edits. "
                        "If confidence is low or the repo is ambiguous, you may set pr_supported to false, explain blockers, and leave patch_diff empty."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt_payload, indent=2, sort_keys=True),
                },
            ],
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content
        if not content:
            return []

        try:
            payload = _FallbackResponse.model_validate(json.loads(_extract_json_object(content)))
        except (ValidationError, ValueError, TypeError) as exc:
            raise ValueError("OpenAI returned an invalid SDK bootstrap fallback response.") from exc

        raw_proposals = list(payload.proposals)
        if payload.proposal is not None:
            raw_proposals.insert(0, payload.proposal)
        validated: list[SdkBootstrapFallbackProposal] = []
        seen_keys: set[tuple[str, str]] = set()
        for proposal in raw_proposals:
            validated_proposal = self._validate_proposal(repo_dir=repo_dir, proposal=proposal)
            if validated_proposal is None:
                continue
            dedupe_key = (validated_proposal.framework_id, validated_proposal.entrypoint)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            validated.append(validated_proposal)
        return validated[:3]

    def _build_prompt_payload(
        self,
        *,
        repo_dir: Path,
        service_name: str,
        environment: str,
        project_id: str,
        base_url: str,
    ) -> dict[str, object]:
        return {
            "service_name": service_name,
            "environment": environment,
            "project_id": project_id,
            "base_url": base_url,
            "constraints": {
                "max_files": _MAX_FALLBACK_PATCH_FILES,
                "max_changed_lines": _MAX_FALLBACK_PATCH_LINES,
                "blocked_filenames": sorted(_BLOCKED_PATCH_FILENAMES),
                "allowed_create_rule": "new files must include 'stimpact' in the filename or be .env.example",
                "supported_framework_ids": sorted(_SUPPORTED_FRAMEWORK_IDS),
            },
            "supported_frameworks": [
                _serialize_framework(get_framework_spec(framework_id))
                for framework_id in sorted(_SUPPORTED_FRAMEWORK_IDS)
            ],
            "repo_topology": _collect_repo_topology(repo_dir),
            "manifests": _collect_manifest_context(repo_dir),
            "package_scripts": _collect_package_scripts(repo_dir),
            "candidate_files": _collect_candidate_files(repo_dir),
        }

    def _validate_proposal(
        self,
        *,
        repo_dir: Path,
        proposal: _FallbackProposal,
    ) -> SdkBootstrapFallbackProposal | None:
        if proposal.framework_id not in _SUPPORTED_FRAMEWORK_IDS:
            logger.info(
                "sdk_bootstrap_fallback_rejected reason=unsupported_framework framework_id=%s entrypoint=%s",
                proposal.framework_id,
                proposal.entrypoint,
            )
            return None

        entrypoint = _normalize_repo_relative_path(proposal.entrypoint)
        if entrypoint is None:
            logger.info(
                "sdk_bootstrap_fallback_rejected reason=invalid_entrypoint_path framework_id=%s raw_entrypoint=%s",
                proposal.framework_id,
                proposal.entrypoint,
            )
            return None
        entrypoint_path = repo_dir / entrypoint
        if not entrypoint_path.exists():
            logger.info(
                "sdk_bootstrap_fallback_rejected reason=missing_entrypoint framework_id=%s entrypoint=%s",
                proposal.framework_id,
                entrypoint,
            )
            return None

        target_subpath = proposal.target_subpath.strip() or "."
        if target_subpath != "." and not (repo_dir / target_subpath).exists():
            target_subpath = str(Path(entrypoint).parent) or "."
        normalized_target_subpath = "." if target_subpath == "." else _normalize_repo_relative_path(target_subpath)
        if normalized_target_subpath is None:
            normalized_target_subpath = "."

        patch_diff = proposal.patch_diff.strip() or None
        pr_supported = bool(proposal.pr_supported and proposal.confidence in {"high", "medium"} and patch_diff)
        blockers = list(proposal.blockers)
        planned_files: list[SdkBootstrapFallbackPlannedFile] = [
            SdkBootstrapFallbackPlannedFile(path=item.path, action=item.action, reason=item.reason)
            for item in proposal.planned_files
        ]

        if pr_supported and patch_diff is not None:
            diff_details = _validate_patch_diff(repo_dir=repo_dir, entrypoint=entrypoint, patch_diff=patch_diff)
            if diff_details is None:
                pr_supported = False
                patch_diff = None
                logger.info(
                    "sdk_bootstrap_fallback_rejected reason=patch_guardrails framework_id=%s entrypoint=%s planned_files=%s",
                    proposal.framework_id,
                    entrypoint,
                    len(proposal.planned_files),
                )
                blockers.append(
                    "Model-assisted patch did not pass Stimpact's path and diff guardrails, so manual setup is safer."
                )
            elif not _patch_applies_cleanly(repo_dir=repo_dir, patch_diff=patch_diff):
                pr_supported = False
                patch_diff = None
                logger.info(
                    "sdk_bootstrap_fallback_rejected reason=patch_apply_check framework_id=%s entrypoint=%s",
                    proposal.framework_id,
                    entrypoint,
                )
                blockers.append(
                    "Model-assisted patch could not be applied cleanly in a temp checkout, so manual setup is safer."
                )
            elif not planned_files:
                planned_files = [
                    SdkBootstrapFallbackPlannedFile(
                        path=path,
                        action="update" if (repo_dir / path).exists() else "create",
                        reason="Model-assisted SDK bootstrap change.",
                    )
                    for path in diff_details.paths
                ]
        else:
            patch_diff = None

        if not planned_files:
            planned_files = [
                SdkBootstrapFallbackPlannedFile(
                    path=entrypoint,
                    action="update",
                    reason="Likely runtime entrypoint for SDK initialization.",
                )
            ]

        return SdkBootstrapFallbackProposal(
            framework_id=proposal.framework_id,
            summary=proposal.summary,
            confidence=proposal.confidence,
            confidence_reason=proposal.confidence_reason,
            target_subpath=normalized_target_subpath,
            entrypoint=entrypoint,
            evidence=list(proposal.evidence),
            assumptions=list(proposal.assumptions),
            blockers=blockers,
            planned_files=planned_files,
            preview_snippet=proposal.preview_snippet,
            patch_diff=patch_diff,
            pr_supported=pr_supported,
        )


class _FallbackPlannedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=500)
    action: str = Field(min_length=1, max_length=32)
    reason: str = Field(min_length=1, max_length=500)


class _FallbackProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    framework_id: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=500)
    confidence: str = Field(min_length=1, max_length=32)
    confidence_reason: str = Field(min_length=1, max_length=500)
    target_subpath: str = Field(default=".", max_length=300)
    entrypoint: str = Field(min_length=1, max_length=500)
    evidence: list[str] = Field(default_factory=list, max_length=8)
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    blockers: list[str] = Field(default_factory=list, max_length=8)
    planned_files: list[_FallbackPlannedFile] = Field(default_factory=list, max_length=8)
    preview_snippet: str | None = Field(default=None, max_length=6000)
    patch_diff: str = Field(default="", max_length=40000)
    pr_supported: bool = True


class _FallbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal: _FallbackProposal | None = None
    proposals: list[_FallbackProposal] = Field(default_factory=list, max_length=3)


@dataclass(slots=True)
class _DiffDetails:
    paths: list[str]
    changed_line_count: int


def _collect_manifest_context(repo_dir: Path) -> list[dict[str, object]]:
    manifests: list[dict[str, object]] = []
    for relative_path in (
        "package.json",
        "package-lock.json",
        "pyproject.toml",
        "requirements.txt",
        "requirements.in",
        "requirements-dev.txt",
        "Pipfile",
        "setup.py",
    ):
        for path in repo_dir.rglob(relative_path):
            if _should_skip_path(path):
                continue
            manifests.append(
                {
                    "path": path.relative_to(repo_dir).as_posix(),
                    "content": _truncate_text(path.read_text(encoding="utf-8", errors="ignore"), max_chars=5000),
                }
            )
            if len(manifests) >= 12:
                return manifests
    return manifests


def _collect_package_scripts(repo_dir: Path) -> list[dict[str, object]]:
    scripts: list[dict[str, object]] = []
    for path in repo_dir.rglob("package.json"):
        if _should_skip_path(path):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except json.JSONDecodeError:
            continue
        package_scripts = payload.get("scripts")
        if not isinstance(package_scripts, dict):
            continue
        scripts.append(
            {
                "path": path.relative_to(repo_dir).as_posix(),
                "scripts": {str(key): str(value) for key, value in package_scripts.items()},
            }
        )
        if len(scripts) >= 12:
            break
    return scripts


def _collect_repo_topology(repo_dir: Path) -> dict[str, object]:
    package_roots: list[str] = []
    python_roots: list[str] = []
    notable_dirs: list[str] = []
    package_managers: set[str] = set()
    for path in repo_dir.rglob("*"):
        if _should_skip_path(path):
            continue
        if path.is_dir():
            relative_dir = path.relative_to(repo_dir).as_posix()
            if Path(relative_dir).name.lower() in {
                "app",
                "apps",
                "src",
                "pages",
                "frontend",
                "backend",
                "client",
                "server",
                "web",
                "ui",
                "api",
                "services",
                "packages",
            }:
                notable_dirs.append(relative_dir)
            continue
        relative_path = path.relative_to(repo_dir).as_posix()
        if path.name == "package.json":
            package_roots.append(str(Path(relative_path).parent).replace("\\", "/") or ".")
        if path.name in {"pyproject.toml", "requirements.txt", "requirements.in", "setup.py", "Pipfile"}:
            python_roots.append(str(Path(relative_path).parent).replace("\\", "/") or ".")
        if path.name == "pnpm-lock.yaml":
            package_managers.add("pnpm")
        elif path.name == "yarn.lock":
            package_managers.add("yarn")
        elif path.name == "package-lock.json":
            package_managers.add("npm")
        elif path.name == "bun.lockb":
            package_managers.add("bun")
    return {
        "package_roots": sorted(dict.fromkeys(package_roots))[:12],
        "python_roots": sorted(dict.fromkeys(python_roots))[:12],
        "notable_directories": sorted(dict.fromkeys(notable_dirs))[:20],
        "package_managers": sorted(package_managers),
    }


def _collect_candidate_files(repo_dir: Path) -> list[dict[str, object]]:
    script_path_hints = _collect_script_path_hints(repo_dir)
    candidates: list[tuple[int, Path, str]] = []
    for path in repo_dir.rglob("*"):
        if _should_skip_path(path) or not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts", ".py"}:
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        score, reason = _score_candidate_file(
            path.relative_to(repo_dir).as_posix(),
            source,
            script_path_hints=script_path_hints,
        )
        if score <= 0:
            continue
        candidates.append((score, path, reason))

    selected: list[dict[str, object]] = []
    for _, path, reason in sorted(candidates, key=lambda item: (-item[0], item[1].as_posix()))[:16]:
        selected.append(
            {
                "path": path.relative_to(repo_dir).as_posix(),
                "reason": reason,
                "excerpt": _truncate_text(path.read_text(encoding="utf-8", errors="ignore"), max_chars=6000),
            }
        )
    return selected


def _collect_script_path_hints(repo_dir: Path) -> set[str]:
    hints: set[str] = set()
    path_pattern = re.compile(r"(?P<path>(?:\.?/)?(?:src|app|apps|packages|services|server|client|web|api)[\w./-]*\.(?:js|jsx|ts|tsx|mjs|cjs|mts|cts|py))")
    for path in repo_dir.rglob("package.json"):
        if _should_skip_path(path):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except json.JSONDecodeError:
            continue
        scripts = payload.get("scripts")
        if not isinstance(scripts, dict):
            continue
        package_dir = path.parent
        for command in scripts.values():
            if not isinstance(command, str):
                continue
            for match in path_pattern.finditer(command):
                candidate = match.group("path").lstrip("./")
                resolved_candidates = [
                    (repo_dir / candidate).resolve(),
                    (package_dir / candidate).resolve(),
                ]
                for absolute in resolved_candidates:
                    try:
                        relative = absolute.relative_to(repo_dir.resolve()).as_posix()
                    except ValueError:
                        continue
                    if absolute.exists():
                        hints.add(relative)
                        break
    return hints


def _score_candidate_file(relative_path: str, source: str, *, script_path_hints: set[str]) -> tuple[int, str]:
    score = 0
    reasons: list[str] = []
    lower_path = relative_path.lower()
    lower_source = source.lower()
    stem = Path(relative_path).stem.lower()
    if stem in {"main", "app", "index", "server", "client", "bootstrap", "run", "layout", "_app", "root", "entry"}:
        score += 3
        reasons.append("entrypoint-like filename")
    if lower_path.endswith(
        (
            "/layout.tsx",
            "/layout.jsx",
            "/layout.js",
            "/layout.ts",
            "/pages/_app.tsx",
            "/pages/_app.jsx",
            "/pages/_app.js",
            "/src/pages/_app.tsx",
            "/src/pages/_app.jsx",
            "/src/pages/_app.js",
            "/root.tsx",
            "/root.jsx",
            "/root.ts",
            "/root.js",
        )
    ):
        score += 4
        reasons.append("next root shell detected")
    if (
        "reactdom.createroot" in lower_source
        or "reactdom.render" in lower_source
        or "createroot(" in lower_source
        or "hydrateRoot(".lower() in lower_source
    ):
        score += 4
        reasons.append("react mount detected")
    if "document.getelementbyid(" in lower_source or "root.render(" in lower_source:
        score += 2
        reasons.append("browser root bootstrap detected")
    if "export default function rootlayout" in lower_source or "<body" in lower_source:
        score += 3
        reasons.append("app shell layout detected")
    if "fastapi(" in lower_source:
        score += 4
        reasons.append("fastapi app detected")
    if "flask(" in lower_source:
        score += 4
        reasons.append("flask app detected")
    if "app = fastapi(" in lower_source or "app = flask(" in lower_source or "application = flask(" in lower_source:
        score += 2
        reasons.append("python app object detected")
    if "__name__ == \"__main__\"" in source or "__name__ == '__main__'" in source:
        score += 2
        reasons.append("python executable entrypoint")
    if "uvicorn.run(" in lower_source or "gunicorn" in lower_source:
        score += 2
        reasons.append("python server startup detected")
    if "render(" in source or "mount(" in source or "app =" in lower_source:
        score += 1
        reasons.append("runtime bootstrap signal")
    if relative_path in script_path_hints:
        score += 4
        reasons.append("referenced by package scripts")
    if lower_path.endswith(
        (
            "/main.tsx",
            "/main.jsx",
            "/main.ts",
            "/main.js",
            "/bootstrap.tsx",
            "/bootstrap.jsx",
            "/bootstrap.ts",
            "/bootstrap.js",
            "/client.tsx",
            "/client.jsx",
            "/client.ts",
            "/client.js",
            "/entry.client.tsx",
            "/entry.client.jsx",
            "/app.py",
            "/main.py",
            "/server.py",
            "/run.py",
        )
    ):
        score += 2
    return score, ", ".join(dict.fromkeys(reasons))


def _validate_patch_diff(*, repo_dir: Path, entrypoint: str, patch_diff: str) -> _DiffDetails | None:
    paths: list[str] = []
    changed_line_count = 0
    diff_matches_entrypoint = False
    for line in patch_diff.splitlines():
        if line.startswith("diff --git "):
            match = re.match(r"diff --git a/(.+?) b/(.+)", line)
            if not match:
                return None
            normalized_path = _normalize_repo_relative_path(match.group(2))
            if normalized_path is None:
                return None
            paths.append(normalized_path)
            if normalized_path == entrypoint:
                diff_matches_entrypoint = True
            continue
        if line.startswith("+++ b/"):
            normalized_path = _normalize_repo_relative_path(line.removeprefix("+++ b/").strip())
            if normalized_path is None:
                return None
            if normalized_path not in paths:
                paths.append(normalized_path)
            if normalized_path == entrypoint:
                diff_matches_entrypoint = True
            continue
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("+") or line.startswith("-"):
            changed_line_count += 1

    unique_paths = list(dict.fromkeys(paths))
    if not unique_paths or len(unique_paths) > _MAX_FALLBACK_PATCH_FILES:
        return None
    if changed_line_count > _MAX_FALLBACK_PATCH_LINES:
        return None
    if not diff_matches_entrypoint:
        return None

    for relative_path in unique_paths:
        if Path(relative_path).name in _BLOCKED_PATCH_FILENAMES:
            return None
        if not _is_allowed_patch_surface(repo_dir=repo_dir, relative_path=relative_path):
            return None
    return _DiffDetails(paths=unique_paths, changed_line_count=changed_line_count)


def _patch_applies_cleanly(*, repo_dir: Path, patch_diff: str) -> bool:
    if not (repo_dir / ".git").exists():
        return True
    try:
        result = subprocess.run(
            ["git", "apply", "--check", "--whitespace=nowarn", "-"],
            cwd=repo_dir,
            check=False,
            capture_output=True,
            text=True,
            input=patch_diff,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def _is_allowed_patch_surface(*, repo_dir: Path, relative_path: str) -> bool:
    path = Path(relative_path)
    suffix = path.suffix.lower()
    if suffix not in _ALLOWED_PATCH_EXTENSIONS and path.name not in {
        "package.json",
        "pyproject.toml",
        ".env.example",
        "setup.py",
        "requirements.txt",
        "requirements.in",
        "Pipfile",
    }:
        return False
    if path.name in _BLOCKED_PATCH_FILENAMES:
        return False
    absolute = (repo_dir / path).resolve()
    try:
        absolute.relative_to(repo_dir.resolve())
    except ValueError:
        return False
    if absolute.exists():
        return True
    if path.name == ".env.example" or (
        path.name.startswith(".env.") and any(token in path.name for token in ("example", "sample", "template"))
    ):
        return True
    return "stimpact" in path.name.lower()


def _normalize_repo_relative_path(raw_path: str) -> str | None:
    value = raw_path.strip()
    if not value or value == "/dev/null":
        return None
    normalized = Path(value).as_posix().lstrip("./")
    if normalized.startswith("/") or normalized.startswith("..") or "/../" in normalized:
        return None
    return normalized or "."


def _serialize_framework(spec: SdkFrameworkSpec) -> dict[str, object]:
    return {
        "id": spec.id,
        "label": spec.label,
        "language": spec.language,
        "package_name": spec.package_name,
        "install_command": spec.install_command,
        "env_vars": [
            {
                "name": item.name,
                "example_value": item.example_value,
                "description": item.description,
            }
            for item in spec.env_vars
        ],
    }


def _should_skip_path(path: Path) -> bool:
    skip_parts = {"node_modules", ".git", ".next", "dist", "build", "__pycache__", ".venv", "venv"}
    return any(part in skip_parts for part in path.parts)


def _truncate_text(value: str, *, max_chars: int) -> str:
    normalized = value.strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars] + "\n# ... truncated ..."


def _extract_json_object(content: str) -> str:
    normalized = content.strip()
    if normalized.startswith("{") and normalized.endswith("}"):
        return normalized
    start = normalized.find("{")
    end = normalized.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response.")
    return normalized[start : end + 1]
