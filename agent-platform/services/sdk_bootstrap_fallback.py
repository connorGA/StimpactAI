from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from services.sdk_catalog import SdkFrameworkSpec, get_framework_spec

_MAX_FALLBACK_PATCH_FILES = 4
_MAX_FALLBACK_PATCH_LINES = 220
_ALLOWED_PATCH_EXTENSIONS = {
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
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
    "javascript-generic",
    "javascript-vite-react",
    "python-fastapi",
    "python-flask",
    "python-generic",
}


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
        prompt_payload = self._build_prompt_payload(
            repo_dir=repo_dir,
            service_name=service_name,
            environment=environment,
            project_id=project_id,
            base_url=base_url,
        )
        if not prompt_payload["candidate_files"]:
            return None

        completion = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are planning a safe SDK bootstrap patch for Stimpact. "
                        "Use only the grounded repo context provided. "
                        "Return raw JSON with a single key named proposal. "
                        "The proposal must describe one best candidate strategy. "
                        "Only propose a PR-capable patch when you can identify a concrete runtime entrypoint and keep the diff small. "
                        "Never touch lockfiles, generated assets, tests, CI, docker, or unrelated files. "
                        "Allowed modified surfaces are existing runtime entrypoints, package/dependency manifests, .env.example, "
                        "and at most one small helper file whose filename contains 'stimpact'. "
                        "The patch_diff must be a valid unified diff touching no more than 4 files and 220 changed lines total. "
                        "Use framework_id from this allowlist only: javascript-generic, javascript-vite-react, python-fastapi, python-flask, python-generic. "
                        "If confidence is low or the repo is ambiguous, set pr_supported to false, explain blockers, and leave patch_diff empty."
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
            return None

        try:
            payload = _FallbackResponse.model_validate(json.loads(_extract_json_object(content)))
        except (ValidationError, ValueError, TypeError) as exc:
            raise ValueError("OpenAI returned an invalid SDK bootstrap fallback response.") from exc

        proposal = payload.proposal
        if proposal is None:
            return None
        return self._validate_proposal(repo_dir=repo_dir, proposal=proposal)

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
            "manifests": _collect_manifest_context(repo_dir),
            "candidate_files": _collect_candidate_files(repo_dir),
        }

    def _validate_proposal(
        self,
        *,
        repo_dir: Path,
        proposal: _FallbackProposal,
    ) -> SdkBootstrapFallbackProposal | None:
        if proposal.framework_id not in _SUPPORTED_FRAMEWORK_IDS:
            return None

        entrypoint = _normalize_repo_relative_path(proposal.entrypoint)
        if entrypoint is None:
            return None
        entrypoint_path = repo_dir / entrypoint
        if not entrypoint_path.exists():
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
                blockers.append(
                    "Model-assisted patch did not pass Stimpact's path and diff guardrails, so manual setup is safer."
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


@dataclass(slots=True)
class _DiffDetails:
    paths: list[str]
    changed_line_count: int


def _collect_manifest_context(repo_dir: Path) -> list[dict[str, object]]:
    manifests: list[dict[str, object]] = []
    for relative_path in (
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
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
            if len(manifests) >= 8:
                return manifests
    return manifests


def _collect_candidate_files(repo_dir: Path) -> list[dict[str, object]]:
    candidates: list[tuple[int, Path, str]] = []
    for path in repo_dir.rglob("*"):
        if _should_skip_path(path) or not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in {".js", ".jsx", ".ts", ".tsx", ".py"}:
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        score, reason = _score_candidate_file(path.relative_to(repo_dir).as_posix(), source)
        if score <= 0:
            continue
        candidates.append((score, path, reason))

    selected: list[dict[str, object]] = []
    for _, path, reason in sorted(candidates, key=lambda item: (-item[0], item[1].as_posix()))[:10]:
        selected.append(
            {
                "path": path.relative_to(repo_dir).as_posix(),
                "reason": reason,
                "excerpt": _truncate_text(path.read_text(encoding="utf-8", errors="ignore"), max_chars=6000),
            }
        )
    return selected


def _score_candidate_file(relative_path: str, source: str) -> tuple[int, str]:
    score = 0
    reasons: list[str] = []
    lower_path = relative_path.lower()
    lower_source = source.lower()
    stem = Path(relative_path).stem.lower()
    if stem in {"main", "app", "index", "server", "client", "bootstrap", "run"}:
        score += 3
        reasons.append("entrypoint-like filename")
    if "reactdom.createRoot" in source or "reactdom.render" in source or "createRoot(" in source:
        score += 4
        reasons.append("react mount detected")
    if "fastapi(" in lower_source:
        score += 4
        reasons.append("fastapi app detected")
    if "flask(" in lower_source:
        score += 4
        reasons.append("flask app detected")
    if "__name__ == \"__main__\"" in source or "__name__ == '__main__'" in source:
        score += 2
        reasons.append("python executable entrypoint")
    if "render(" in source or "mount(" in source or "app =" in lower_source:
        score += 1
        reasons.append("runtime bootstrap signal")
    if lower_path.endswith(("/main.tsx", "/main.jsx", "/main.ts", "/main.js", "/app.py", "/main.py", "/server.py")):
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


def _is_allowed_patch_surface(*, repo_dir: Path, relative_path: str) -> bool:
    path = Path(relative_path)
    suffix = path.suffix.lower()
    if suffix not in _ALLOWED_PATCH_EXTENSIONS and path.name not in {"package.json", "pyproject.toml", ".env.example", "setup.py"}:
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
    if path.name == ".env.example":
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
