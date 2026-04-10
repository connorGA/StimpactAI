from __future__ import annotations

from services.sdk_bootstrap_harness.models import (
    SAFE_CHANGE_CATEGORY_DEPENDENCY,
    SAFE_CHANGE_CATEGORY_DEPLOYMENT,
    SAFE_CHANGE_CATEGORY_DOCS,
    SAFE_CHANGE_CATEGORY_ENV,
    SAFE_CHANGE_CATEGORY_OTHER,
    SAFE_CHANGE_CATEGORY_RUNTIME,
    SAFE_CHANGE_CATEGORY_RUNTIME_COMMAND,
    SAFE_CHANGE_CATEGORY_TOKEN_ROUTE,
    SdkBootstrapSafeChangePolicy,
)

_PROHIBITED_PATH_PREFIXES = (
    ".github/",
    ".gitlab/",
    "k8s/",
    "helm/",
    "terraform/",
)
_PROHIBITED_PATH_NAMES = {
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "render.yaml",
    "railway.json",
    "fly.toml",
    "vercel.json",
    "netlify.toml",
    "firebase.json",
    "cloudbuild.yaml",
    "cloudbuild.yml",
    "procfile",
}


def compile_safe_change_policy(*, strategy) -> SdkBootstrapSafeChangePolicy:
    allowed: list[str] = []
    prohibited: list[str] = []
    warnings: list[str] = []

    for planned_file in list(getattr(strategy, "planned_files", []) or []):
        category = _classify_planned_file(str(planned_file.path))
        if category in {SAFE_CHANGE_CATEGORY_DEPLOYMENT, SAFE_CHANGE_CATEGORY_RUNTIME_COMMAND}:
            prohibited.append(category)
        else:
            allowed.append(category)

    for blocker in list(getattr(strategy, "blockers", []) or []):
        normalized = blocker.lower()
        if "build command" in normalized or "start command" in normalized:
            prohibited.append(SAFE_CHANGE_CATEGORY_RUNTIME_COMMAND)
        if "deploy" in normalized or "runtime" in normalized:
            warnings.append(blocker)

    if prohibited:
        warnings.append(
            "Automatic mode was limited to code and configuration wiring. Deployment or runtime command changes require manual review."
        )

    return SdkBootstrapSafeChangePolicy(
        allowed_categories=_dedupe(allowed),
        prohibited_categories=_dedupe(prohibited),
        warnings=_dedupe(warnings),
    )


def _classify_planned_file(path: str) -> str:
    normalized = path.strip().lower().replace("\\", "/")
    if not normalized:
        return SAFE_CHANGE_CATEGORY_OTHER
    if normalized.startswith(_PROHIBITED_PATH_PREFIXES) or normalized in _PROHIBITED_PATH_NAMES:
        return SAFE_CHANGE_CATEGORY_DEPLOYMENT
    if normalized.endswith("/dockerfile"):
        return SAFE_CHANGE_CATEGORY_DEPLOYMENT
    if normalized.endswith("package.json") or normalized.endswith("package-lock.json"):
        return SAFE_CHANGE_CATEGORY_DEPENDENCY
    if normalized.endswith("pnpm-lock.yaml") or normalized.endswith("yarn.lock"):
        return SAFE_CHANGE_CATEGORY_DEPENDENCY
    if normalized.endswith("requirements.txt") or normalized.endswith("pyproject.toml"):
        return SAFE_CHANGE_CATEGORY_DEPENDENCY
    if normalized.endswith(".env.example") or normalized.endswith(".env.sample") or normalized.endswith(".env"):
        return SAFE_CHANGE_CATEGORY_ENV
    if normalized.endswith("readme.md"):
        return SAFE_CHANGE_CATEGORY_DOCS
    if "stimpact-token" in normalized or "/api/" in normalized:
        return SAFE_CHANGE_CATEGORY_TOKEN_ROUTE
    if normalized.endswith((".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py")):
        return SAFE_CHANGE_CATEGORY_RUNTIME
    return SAFE_CHANGE_CATEGORY_OTHER


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
