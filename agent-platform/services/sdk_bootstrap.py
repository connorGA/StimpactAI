from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

from api.core.errors import APIError
from services.sdk_catalog import SdkEnvVarSpec, get_framework_spec
from services.sdk_bootstrap_fallback import SdkBootstrapFallbackPlanner, SdkBootstrapFallbackProposal

SDK_BOOTSTRAP_API_KEY_PLACEHOLDER = "stimp_live_replace_me"
SDK_BOOTSTRAP_BROWSER_KEY_PLACEHOLDER = "stimp_browser_replace_me"
logger = logging.getLogger(__name__)
_ROOT_MANIFEST_DIR_NAMES = (
    "frontend",
    "backend",
    "client",
    "server",
    "web",
    "ui",
    "site",
    "sites",
    "app",
    "apps",
    "dashboard",
    "portal",
    "admin",
    "api",
    "worker",
    "workers",
    "service",
    "services",
)
_NESTED_MANIFEST_PARENT_DIR_NAMES = ("apps", "packages", "services", "sites", "projects")


@dataclass(slots=True)
class SdkBootstrapPlannedFile:
    path: str
    action: str
    reason: str


@dataclass(slots=True)
class SdkBootstrapManualStep:
    title: str
    content: str


@dataclass(slots=True)
class SdkBootstrapStrategy:
    id: str
    language: str
    framework: str
    summary: str
    confidence: str
    pr_supported: bool
    target_subpath: str
    entrypoints: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    planned_files: list[SdkBootstrapPlannedFile] = field(default_factory=list)
    env_vars: list[SdkEnvVarSpec] = field(default_factory=list)
    install_command: str | None = None
    package_name: str | None = None
    manual_steps: list[SdkBootstrapManualStep] = field(default_factory=list)
    preview_snippet: str | None = None
    source: str = "deterministic"
    evidence: list[str] = field(default_factory=list)
    confidence_reason: str | None = None
    patch_diff: str | None = None


@dataclass(slots=True)
class SdkBootstrapPlan:
    runtime: str | None
    warnings: list[str]
    strategies: list[SdkBootstrapStrategy]
    recommended_strategy_id: str | None
    requires_confirmation: bool


@dataclass(slots=True)
class SdkBootstrapPatch:
    patch_diff: str | None
    attempt: "SdkBootstrapPatchAttempt" | None = None


@dataclass(slots=True)
class SdkBootstrapVerification:
    status: str
    command: str | None = None
    summary: str | None = None
    output: str | None = None


@dataclass(slots=True)
class SdkBootstrapPatchAttempt:
    strategy_id: str
    patch_source: str
    patch_generated: bool
    patch_applied: bool
    verification: SdkBootstrapVerification
    preview_available: bool
    change_request_allowed: bool
    changed_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failure_stage: str | None = None
    failure_reason: str | None = None
    rejection_reason_code: str | None = None
    attempt_number: int | None = None
    candidate_id: str | None = None
    generation_duration_ms: int | None = None
    apply_duration_ms: int | None = None
    verification_duration_ms: int | None = None


@dataclass(slots=True)
class SdkBootstrapRun:
    run_id: str
    attempts: list[SdkBootstrapPatchAttempt] = field(default_factory=list)
    selected_strategy_id: str | None = None
    selected_attempt_number: int | None = None
    final_outcome: str | None = None


@dataclass(slots=True)
class SdkBootstrapPreparedPreview:
    plan: SdkBootstrapPlan
    selected_strategy_id: str
    strategy: SdkBootstrapStrategy
    patch: SdkBootstrapPatch
    run: SdkBootstrapRun = field(default_factory=lambda: SdkBootstrapRun(run_id=uuid4().hex))


def plan_sdk_bootstrap_from_clone(
    *,
    clone_url: str,
    default_branch: str,
    project_id: str,
    service_name: str,
    environment: str,
    base_url: str,
    fallback_planner: SdkBootstrapFallbackPlanner | None = None,
) -> SdkBootstrapPlan:
    with tempfile.TemporaryDirectory(prefix="stimpact-sdk-bootstrap-plan-") as temp_dir:
        repo_dir = Path(temp_dir) / "repo"
        _clone_sdk_bootstrap_repo(
            clone_url=clone_url,
            default_branch=default_branch,
            repo_dir=repo_dir,
        )
        return plan_sdk_bootstrap_from_checkout(
            repo_dir=repo_dir,
            project_id=project_id,
            service_name=service_name,
            environment=environment,
            base_url=base_url,
            fallback_planner=fallback_planner,
        )


def build_sdk_bootstrap_patch_from_clone(
    *,
    clone_url: str,
    default_branch: str,
    project_id: str,
    service_name: str,
    environment: str,
    base_url: str,
    strategy_id: str,
    api_key: str = SDK_BOOTSTRAP_API_KEY_PLACEHOLDER,
    fallback_planner: SdkBootstrapFallbackPlanner | None = None,
) -> SdkBootstrapPatch:
    with tempfile.TemporaryDirectory(prefix="stimpact-sdk-bootstrap-") as temp_dir:
        repo_dir = Path(temp_dir) / "repo"
        _clone_sdk_bootstrap_repo(
            clone_url=clone_url,
            default_branch=default_branch,
            repo_dir=repo_dir,
        )
        plan = plan_sdk_bootstrap_from_checkout(
            repo_dir=repo_dir,
            project_id=project_id,
            service_name=service_name,
            environment=environment,
            base_url=base_url,
            fallback_planner=fallback_planner,
        )
        strategy = _require_strategy(plan, strategy_id)
        return _build_sdk_bootstrap_patch_from_checkout(
            repo_dir=repo_dir,
            strategy=strategy,
            project_id=project_id,
            service_name=service_name,
            environment=environment,
            base_url=base_url,
            api_key=api_key,
        )


def prepare_sdk_bootstrap_preview_from_clone(
    *,
    clone_url: str,
    default_branch: str,
    project_id: str,
    service_name: str,
    environment: str,
    base_url: str,
    strategy_id: str | None,
    api_key: str = SDK_BOOTSTRAP_API_KEY_PLACEHOLDER,
    fallback_planner: SdkBootstrapFallbackPlanner | None = None,
) -> SdkBootstrapPreparedPreview:
    with tempfile.TemporaryDirectory(prefix="stimpact-sdk-bootstrap-preview-") as temp_dir:
        repo_dir = Path(temp_dir) / "repo"
        _clone_sdk_bootstrap_repo(
            clone_url=clone_url,
            default_branch=default_branch,
            repo_dir=repo_dir,
        )
        plan = plan_sdk_bootstrap_from_checkout(
            repo_dir=repo_dir,
            project_id=project_id,
            service_name=service_name,
            environment=environment,
            base_url=base_url,
            fallback_planner=fallback_planner,
        )
        selected_strategy_id = strategy_id or plan.recommended_strategy_id
        if selected_strategy_id is None:
            raise APIError(
                "No SDK bootstrap strategy could be recommended for this repository.",
                status_code=400,
                code="sdk_bootstrap_plan_unavailable",
            )
        candidate_strategies = _rank_preview_candidate_strategies(
            plan=plan,
            explicit_strategy_id=strategy_id,
        )
        if not candidate_strategies:
            strategy = _require_strategy(plan, selected_strategy_id)
            run = SdkBootstrapRun(
                run_id=uuid4().hex,
                selected_strategy_id=strategy.id,
                final_outcome="manual_fallback",
            )
            patch = _build_detection_failure_patch(strategy=strategy)
            patch.attempt.attempt_number = 1
            patch.attempt.candidate_id = strategy.id
            run.attempts.append(patch.attempt)
            run.selected_attempt_number = 1
            return SdkBootstrapPreparedPreview(
                plan=plan,
                selected_strategy_id=strategy.id,
                strategy=strategy,
                patch=patch,
                run=run,
            )
        strategy, patch, run = _run_sdk_bootstrap_attempts(
            repo_dir=repo_dir,
            candidate_strategies=candidate_strategies,
            project_id=project_id,
            service_name=service_name,
            environment=environment,
            base_url=base_url,
            api_key=api_key,
        )
        return SdkBootstrapPreparedPreview(
            plan=plan,
            selected_strategy_id=strategy.id,
            strategy=strategy,
            patch=patch,
            run=run,
        )


def plan_sdk_bootstrap_from_checkout(
    *,
    repo_dir: Path,
    project_id: str,
    service_name: str,
    environment: str,
    base_url: str,
    fallback_planner: SdkBootstrapFallbackPlanner | None = None,
) -> SdkBootstrapPlan:
    strategies = [
        *_detect_javascript_strategies(
            repo_dir=repo_dir,
            project_id=project_id,
            service_name=service_name,
            environment=environment,
            base_url=base_url,
        ),
        *_detect_python_strategies(
            repo_dir=repo_dir,
            project_id=project_id,
            service_name=service_name,
            environment=environment,
            base_url=base_url,
        ),
    ]
    warnings: list[str] = []
    fallback_used = False
    if fallback_planner is not None and _should_request_fallback_candidates(strategies):
        try:
            if hasattr(fallback_planner, "plan_candidates"):
                fallback_proposals = fallback_planner.plan_candidates(
                    repo_dir=repo_dir,
                    service_name=service_name,
                    environment=environment,
                    project_id=project_id,
                    base_url=base_url,
                )
            else:
                fallback_proposal = fallback_planner.plan(
                    repo_dir=repo_dir,
                    service_name=service_name,
                    environment=environment,
                    project_id=project_id,
                    base_url=base_url,
                )
                fallback_proposals = [fallback_proposal] if fallback_proposal is not None else []
        except Exception:  # noqa: BLE001
            fallback_proposals = []
            warnings.append(
                "Model-assisted SDK bootstrap was unavailable for this repository, so the planner kept the safer manual path."
            )
        if fallback_proposals:
            fallback_used = True
            strategies.extend(
                _build_llm_strategy(
                    proposal=fallback_proposal,
                    service_name=service_name,
                    environment=environment,
                )
                for fallback_proposal in fallback_proposals
            )
        else:
            warnings.append(
                "Model-assisted SDK bootstrap did not find a review-safe automatic patch for this repository, so the planner kept the safer manual path."
            )
    languages = {strategy.language for strategy in strategies}
    runtime = None
    if len(languages) == 1:
        runtime = next(iter(languages))
    elif len(languages) > 1:
        runtime = "mixed"
        warnings.append(
            "Multiple supported runtime families were detected. Confirm the intended surface before generating a bootstrap PR."
        )
    if not strategies:
        warnings.append(
            "No supported JavaScript or Python application surface was detected confidently enough for SDK bootstrap."
        )
    logger.info(
        "sdk_bootstrap_candidate_discovery runtime=%s deterministic=%s total=%s fallback_used=%s pr_supported=%s",
        runtime,
        len([item for item in strategies if item.source == "deterministic"]),
        len(strategies),
        fallback_used,
        len([item for item in strategies if item.pr_supported]),
    )
    recommended_strategy_id = _pick_recommended_strategy_id(strategies)
    requires_confirmation = (
        len([item for item in strategies if item.pr_supported and item.confidence in {"high", "medium"}]) > 1
        or any(item.confidence != "high" for item in strategies if item.id == recommended_strategy_id)
    )
    return SdkBootstrapPlan(
        runtime=runtime,
        warnings=warnings,
        strategies=strategies,
        recommended_strategy_id=recommended_strategy_id,
        requires_confirmation=requires_confirmation,
    )


def _detect_javascript_strategies(
    *,
    repo_dir: Path,
    project_id: str,
    service_name: str,
    environment: str,
    base_url: str,
) -> list[SdkBootstrapStrategy]:
    strategies: list[SdkBootstrapStrategy] = []
    for package_dir in _candidate_manifest_dirs(repo_dir, "package.json"):
        package_json = _read_json(package_dir / "package.json")
        dependency_names = _package_dependency_names(package_json)
        display_subpath = _relative_display_path(repo_dir, package_dir)
        if "next" in dependency_names:
            strategy = _build_next_strategy(
                repo_dir=repo_dir,
                package_dir=package_dir,
                service_name=service_name,
                environment=environment,
                project_id=project_id,
                base_url=base_url,
            )
            if strategy is not None:
                strategies.append(strategy)
                continue
        if "vite" in dependency_names and "react" in dependency_names:
            strategy = _build_vite_react_strategy(
                repo_dir=repo_dir,
                package_dir=package_dir,
                service_name=service_name,
                environment=environment,
                project_id=project_id,
                base_url=base_url,
            )
            if strategy is not None:
                strategies.append(strategy)
                continue
        if "react" in dependency_names and "react-dom" in dependency_names and _uses_react_scripts(package_json):
            strategy = _build_react_scripts_strategy(
                repo_dir=repo_dir,
                package_dir=package_dir,
                package_json=package_json,
                service_name=service_name,
                environment=environment,
                project_id=project_id,
                base_url=base_url,
            )
            if strategy is not None:
                strategies.append(strategy)
                continue
        strategy = _build_generic_javascript_strategy(
            repo_dir=repo_dir,
            package_dir=package_dir,
            package_json=package_json,
            service_name=service_name,
            environment=environment,
        )
        if strategy is not None:
            strategies.append(strategy)
            continue
        strategies.append(
            _build_manual_strategy(
                framework_id="javascript-generic",
                strategy_id=f"javascript-generic:{display_subpath}",
                summary=f"JavaScript app detected in {display_subpath}. Manual setup is safer because no supported auto-injection entrypoint was found.",
                confidence="medium",
                target_subpath=display_subpath,
                entrypoints=[],
                assumptions=["This repository uses JavaScript tooling but not a currently supported bootstrap target."],
                blockers=["Automatic PR generation is only enabled for supported JavaScript entrypoints."],
                manual_steps=[
                    SdkBootstrapManualStep(
                        title="Install the SDK",
                        content="Add `@stimpact/sdk` with your package manager, then initialize it in the runtime entrypoint that handles user requests or browser rendering.",
                    ),
                    SdkBootstrapManualStep(
                        title="Configure telemetry",
                        content="Pass a server `apiKey` for backend runtimes, or a browser `browserKey` / token provider for frontend runtimes, alongside the project id, service name, environment, and public Stimpact base URL when constructing `StimpactClient`.",
                    ),
                ],
                preview_snippet=_build_generic_javascript_snippet(service_name=service_name, environment=environment),
            )
        )
    return strategies


def _detect_python_strategies(
    *,
    repo_dir: Path,
    project_id: str,
    service_name: str,
    environment: str,
    base_url: str,
) -> list[SdkBootstrapStrategy]:
    strategies: list[SdkBootstrapStrategy] = []
    for project_dir in _candidate_python_project_dirs(repo_dir):
        entrypoint = _find_python_entrypoint(project_dir)
        display_subpath = _relative_display_path(repo_dir, project_dir)
        if entrypoint is None:
            strategies.append(
                _build_manual_strategy(
                    framework_id="python-generic",
                    strategy_id=f"python-generic:{display_subpath}",
                    summary=f"Python project detected in {display_subpath}. Manual setup is safer because no supported FastAPI or Flask entrypoint was found.",
                    confidence="medium",
                    target_subpath=display_subpath,
                    entrypoints=[],
                    assumptions=["This repository contains Python application code."],
                    blockers=["Automatic PR generation is currently enabled for FastAPI and Flask entrypoints only."],
                    manual_steps=[
                        SdkBootstrapManualStep(
                            title="Install the SDK",
                            content="Add `stimpact-sdk` to your dependency manager, then create a client using the Stimpact environment variables before sending errors to `/telemetry/error`.",
                        ),
                    ],
                    preview_snippet=_build_python_generic_snippet(service_name=service_name, environment=environment),
                )
            )
            continue
        framework, entrypoint_path = entrypoint
        if framework == "fastapi":
            strategies.append(
                _build_fastapi_strategy(
                    repo_dir=repo_dir,
                    project_dir=project_dir,
                    entrypoint_path=entrypoint_path,
                    service_name=service_name,
                    environment=environment,
                    project_id=project_id,
                    base_url=base_url,
                )
            )
        elif framework == "flask":
            strategies.append(
                _build_flask_strategy(
                    repo_dir=repo_dir,
                    project_dir=project_dir,
                    entrypoint_path=entrypoint_path,
                    service_name=service_name,
                    environment=environment,
                    project_id=project_id,
                    base_url=base_url,
                )
            )
    return strategies


def _build_next_strategy(
    *,
    repo_dir: Path,
    package_dir: Path,
    service_name: str,
    environment: str,
    project_id: str,
    base_url: str,
) -> SdkBootstrapStrategy | None:
    framework_spec = get_framework_spec("javascript-next")
    for relative_path in ("src/app/layout.tsx", "src/app/layout.jsx", "app/layout.tsx", "app/layout.jsx"):
        target_path = package_dir / relative_path
        if target_path.exists():
            component_path = target_path.parents[1] / "components" / f"stimpact-provider{target_path.suffix}"
            display_subpath = _relative_display_path(repo_dir, package_dir)
            return SdkBootstrapStrategy(
                id=f"javascript-next:{display_subpath}:{relative_path}",
                language="javascript",
                framework=framework_spec.label,
                summary=f"Inject browser auto-capture into the Next.js app shell at {relative_path}.",
                confidence="high",
                pr_supported=True,
                target_subpath=display_subpath,
                entrypoints=[_relative_display_path(repo_dir, target_path)],
                assumptions=["The detected layout wraps the browser surface for this Next.js app."],
                planned_files=[
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, package_dir / "package.json"),
                        action="update",
                        reason="Add @stimpact/sdk to runtime dependencies.",
                    ),
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, component_path),
                        action="create",
                        reason="Add a small browser telemetry provider component.",
                    ),
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, target_path),
                        action="update",
                        reason="Mount the browser telemetry provider in the Next.js root shell.",
                    ),
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, package_dir / ".env.example"),
                        action="update",
                        reason="Document the Stimpact public runtime variables for this app.",
                    ),
                ],
                env_vars=framework_spec.env_vars,
                install_command=framework_spec.install_command,
                package_name=framework_spec.package_name,
                manual_steps=_javascript_manual_steps(framework_spec.label),
                preview_snippet=_build_next_provider_source(service_name=service_name, environment=environment),
            )
    for relative_path in ("src/pages/_app.tsx", "src/pages/_app.jsx", "pages/_app.tsx", "pages/_app.jsx"):
        target_path = package_dir / relative_path
        if target_path.exists():
            component_path = target_path.parents[1] / "components" / f"stimpact-provider{target_path.suffix}"
            display_subpath = _relative_display_path(repo_dir, package_dir)
            return SdkBootstrapStrategy(
                id=f"javascript-next:{display_subpath}:{relative_path}",
                language="javascript",
                framework=framework_spec.label,
                summary=f"Inject browser auto-capture into the Next.js pages app shell at {relative_path}.",
                confidence="high",
                pr_supported=True,
                target_subpath=display_subpath,
                entrypoints=[_relative_display_path(repo_dir, target_path)],
                assumptions=["The detected pages app file is the browser entrypoint for this Next.js app."],
                planned_files=[
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, package_dir / "package.json"),
                        action="update",
                        reason="Add @stimpact/sdk to runtime dependencies.",
                    ),
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, component_path),
                        action="create",
                        reason="Add a small browser telemetry provider component.",
                    ),
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, target_path),
                        action="update",
                        reason="Mount the browser telemetry provider in the pages root app.",
                    ),
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, package_dir / ".env.example"),
                        action="update",
                        reason="Document the Stimpact public runtime variables for this app.",
                    ),
                ],
                env_vars=framework_spec.env_vars,
                install_command=framework_spec.install_command,
                package_name=framework_spec.package_name,
                manual_steps=_javascript_manual_steps(framework_spec.label),
                preview_snippet=_build_next_provider_source(service_name=service_name, environment=environment),
            )
    return None


def _build_vite_react_strategy(
    *,
    repo_dir: Path,
    package_dir: Path,
    service_name: str,
    environment: str,
    project_id: str,
    base_url: str,
) -> SdkBootstrapStrategy | None:
    framework_spec = get_framework_spec("javascript-vite-react")
    for relative_path in _vite_react_entrypoint_candidates(package_dir):
        target_path = package_dir / relative_path
        if target_path.exists():
            helper_suffix = ".ts" if target_path.suffix in {".ts", ".tsx"} else ".js"
            helper_path = target_path.parent / f"stimpact{helper_suffix}"
            display_subpath = _relative_display_path(repo_dir, package_dir)
            return SdkBootstrapStrategy(
                id=f"javascript-vite-react:{display_subpath}:{relative_path}",
                language="javascript",
                framework=framework_spec.label,
                summary=f"Inject browser auto-capture into the Vite React entrypoint at {relative_path}.",
                confidence="high",
                pr_supported=True,
                target_subpath=display_subpath,
                entrypoints=[_relative_display_path(repo_dir, target_path)],
                assumptions=["The detected Vite entrypoint mounts the primary browser application surface."],
                planned_files=[
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, package_dir / "package.json"),
                        action="update",
                        reason="Add @stimpact/sdk to runtime dependencies.",
                    ),
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, helper_path),
                        action="create",
                        reason="Add a browser bootstrap helper for Vite.",
                    ),
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, target_path),
                        action="update",
                        reason="Install the Stimpact bootstrap helper before React renders.",
                    ),
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, package_dir / ".env.example"),
                        action="update",
                        reason="Document the Stimpact Vite environment variables for this app.",
                    ),
                ],
                env_vars=framework_spec.env_vars,
                install_command=framework_spec.install_command,
                package_name=framework_spec.package_name,
                manual_steps=_javascript_manual_steps(framework_spec.label),
                preview_snippet=_build_vite_helper_source(service_name=service_name, environment=environment),
            )
    return None


def _build_react_scripts_strategy(
    *,
    repo_dir: Path,
    package_dir: Path,
    package_json: dict[str, object],
    service_name: str,
    environment: str,
    project_id: str,
    base_url: str,
) -> SdkBootstrapStrategy | None:
    framework_spec = get_framework_spec("javascript-react-scripts")
    for relative_path in (
        "src/index.tsx",
        "src/index.jsx",
        "src/index.ts",
        "src/index.js",
        "src/main.tsx",
        "src/main.jsx",
        "src/main.ts",
        "src/main.js",
        "src/bootstrap.tsx",
        "src/bootstrap.jsx",
        "src/bootstrap.ts",
        "src/bootstrap.js",
        "src/client.tsx",
        "src/client.jsx",
        "src/client.ts",
        "src/client.js",
    ):
        target_path = package_dir / relative_path
        if target_path.exists():
            helper_suffix = ".ts" if target_path.suffix in {".ts", ".tsx"} else ".js"
            helper_path = package_dir / "src" / f"stimpact{helper_suffix}"
            display_subpath = _relative_display_path(repo_dir, package_dir)
            return SdkBootstrapStrategy(
                id=f"javascript-react-scripts:{display_subpath}:{relative_path}",
                language="javascript",
                framework=framework_spec.label,
                summary=f"Inject browser auto-capture into the React entrypoint at {relative_path}.",
                confidence="high",
                pr_supported=True,
                target_subpath=display_subpath,
                entrypoints=[_relative_display_path(repo_dir, target_path)],
                assumptions=["The detected index file mounts the primary browser application surface."],
                planned_files=[
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, package_dir / "package.json"),
                        action="update",
                        reason="Add @stimpact/sdk to runtime dependencies.",
                    ),
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, helper_path),
                        action="create",
                        reason="Add a browser bootstrap helper for the React app.",
                    ),
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, target_path),
                        action="update",
                        reason="Install the Stimpact bootstrap helper before React renders.",
                    ),
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, package_dir / ".env.example"),
                        action="update",
                        reason="Document the Stimpact browser environment variables for this app.",
                    ),
                ],
                env_vars=framework_spec.env_vars,
                install_command=framework_spec.install_command,
                package_name=framework_spec.package_name,
                manual_steps=_javascript_manual_steps(framework_spec.label),
                preview_snippet=_build_react_scripts_helper_source(service_name=service_name, environment=environment),
            )
    return None


def _build_generic_javascript_strategy(
    *,
    repo_dir: Path,
    package_dir: Path,
    package_json: dict[str, object],
    service_name: str,
    environment: str,
) -> SdkBootstrapStrategy | None:
    framework_spec = get_framework_spec("javascript-generic")
    entrypoint_relative = _find_generic_javascript_entrypoint(package_dir, package_json)
    if entrypoint_relative is None:
        return None
    entrypoint_path = package_dir / entrypoint_relative
    helper_suffix = ".ts" if entrypoint_path.suffix in {".ts", ".tsx", ".mts", ".cts"} else ".js"
    helper_path = entrypoint_path.parent / f"stimpact{helper_suffix}"
    display_subpath = _relative_display_path(repo_dir, package_dir)
    return SdkBootstrapStrategy(
        id=f"javascript-generic-auto:{display_subpath}:{entrypoint_relative}",
        language="javascript",
        framework=framework_spec.label,
        summary=f"Install process-level Stimpact telemetry in the JavaScript entrypoint at {entrypoint_relative}.",
        confidence="medium",
        pr_supported=True,
        target_subpath=display_subpath,
        entrypoints=[_relative_display_path(repo_dir, entrypoint_path)],
        assumptions=["The detected JavaScript entrypoint starts the main server or worker process for this service."],
        blockers=[],
        planned_files=[
            SdkBootstrapPlannedFile(
                path=_relative_display_path(repo_dir, package_dir / "package.json"),
                action="update",
                reason="Add @stimpact/sdk to runtime dependencies.",
            ),
            SdkBootstrapPlannedFile(
                path=_relative_display_path(repo_dir, helper_path),
                action="create",
                reason="Add a small process-level telemetry bootstrap helper.",
            ),
            SdkBootstrapPlannedFile(
                path=_relative_display_path(repo_dir, entrypoint_path),
                action="update",
                reason="Install the Stimpact bootstrap helper before the service starts.",
            ),
            SdkBootstrapPlannedFile(
                path=_relative_display_path(repo_dir, package_dir / ".env.example"),
                action="update",
                reason="Document the Stimpact runtime variables for this service.",
            ),
        ],
        env_vars=framework_spec.env_vars,
        install_command=framework_spec.install_command,
        package_name=framework_spec.package_name,
        manual_steps=_javascript_manual_steps(framework_spec.label),
        preview_snippet=_build_generic_node_helper_source(service_name=service_name, environment=environment, module_style="esm"),
        confidence_reason="The entrypoint was inferred from package.json scripts or common server bootstrap filenames.",
    )


def _build_fastapi_strategy(
    *,
    repo_dir: Path,
    project_dir: Path,
    entrypoint_path: Path,
    service_name: str,
    environment: str,
    project_id: str,
    base_url: str,
) -> SdkBootstrapStrategy:
    framework_spec = get_framework_spec("python-fastapi")
    dependency_target = _detect_python_dependency_target(project_dir)
    helper_path = project_dir / "stimpact_bootstrap.py"
    display_subpath = _relative_display_path(repo_dir, project_dir)
    return SdkBootstrapStrategy(
        id=f"python-fastapi:{display_subpath}:{_relative_display_path(project_dir, entrypoint_path)}",
        language="python",
        framework=framework_spec.label,
        summary=f"Inject request-scoped telemetry capture into the FastAPI app at {_relative_display_path(repo_dir, entrypoint_path)}.",
        confidence="high" if dependency_target is not None else "medium",
        pr_supported=dependency_target is not None,
        target_subpath=display_subpath,
        entrypoints=[_relative_display_path(repo_dir, entrypoint_path)],
        assumptions=["The detected FastAPI application object serves the primary request path for this service."],
        blockers=[]
        if dependency_target is not None
        else ["No supported Python dependency file was found for automatic SDK installation."],
        planned_files=[
            SdkBootstrapPlannedFile(
                path=_relative_display_path(repo_dir, entrypoint_path),
                action="update",
                reason="Install the Stimpact FastAPI middleware hook.",
            ),
            SdkBootstrapPlannedFile(
                path=_relative_display_path(repo_dir, helper_path),
                action="create",
                reason="Add a small FastAPI bootstrap helper.",
            ),
            *(
                [
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, dependency_target),
                        action="update",
                        reason="Add the Python Stimpact SDK dependency.",
                    ),
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, project_dir / ".env.example"),
                        action="update",
                        reason="Document the Stimpact runtime variables for this service.",
                    ),
                ]
                if dependency_target is not None
                else []
            ),
        ],
        env_vars=framework_spec.env_vars,
        install_command=framework_spec.install_command,
        package_name=framework_spec.package_name,
        manual_steps=_python_manual_steps(framework_spec.label),
        preview_snippet=_build_fastapi_helper_source(service_name=service_name, environment=environment),
    )


def _build_flask_strategy(
    *,
    repo_dir: Path,
    project_dir: Path,
    entrypoint_path: Path,
    service_name: str,
    environment: str,
    project_id: str,
    base_url: str,
) -> SdkBootstrapStrategy:
    framework_spec = get_framework_spec("python-flask")
    dependency_target = _detect_python_dependency_target(project_dir)
    helper_path = project_dir / "stimpact_bootstrap.py"
    display_subpath = _relative_display_path(repo_dir, project_dir)
    return SdkBootstrapStrategy(
        id=f"python-flask:{display_subpath}:{_relative_display_path(project_dir, entrypoint_path)}",
        language="python",
        framework=framework_spec.label,
        summary=f"Attach Stimpact exception capture to the Flask app at {_relative_display_path(repo_dir, entrypoint_path)}.",
        confidence="high" if dependency_target is not None else "medium",
        pr_supported=dependency_target is not None,
        target_subpath=display_subpath,
        entrypoints=[_relative_display_path(repo_dir, entrypoint_path)],
        assumptions=["The detected Flask application object handles the main request lifecycle for this service."],
        blockers=[]
        if dependency_target is not None
        else ["No supported Python dependency file was found for automatic SDK installation."],
        planned_files=[
            SdkBootstrapPlannedFile(
                path=_relative_display_path(repo_dir, entrypoint_path),
                action="update",
                reason="Attach Stimpact exception capture to the Flask app.",
            ),
            SdkBootstrapPlannedFile(
                path=_relative_display_path(repo_dir, helper_path),
                action="create",
                reason="Add a small Flask bootstrap helper.",
            ),
            *(
                [
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, dependency_target),
                        action="update",
                        reason="Add the Python Stimpact SDK dependency.",
                    ),
                    SdkBootstrapPlannedFile(
                        path=_relative_display_path(repo_dir, project_dir / ".env.example"),
                        action="update",
                        reason="Document the Stimpact runtime variables for this service.",
                    ),
                ]
                if dependency_target is not None
                else []
            ),
        ],
        env_vars=framework_spec.env_vars,
        install_command=framework_spec.install_command,
        package_name=framework_spec.package_name,
        manual_steps=_python_manual_steps(framework_spec.label),
        preview_snippet=_build_flask_helper_source(service_name=service_name, environment=environment),
    )


def _build_manual_strategy(
    *,
    framework_id: str,
    strategy_id: str,
    summary: str,
    confidence: str,
    target_subpath: str,
    entrypoints: list[str],
    assumptions: list[str],
    blockers: list[str],
    manual_steps: list[SdkBootstrapManualStep],
    preview_snippet: str,
) -> SdkBootstrapStrategy:
    framework_spec = get_framework_spec(framework_id)
    return SdkBootstrapStrategy(
        id=strategy_id,
        language=framework_spec.language,
        framework=framework_spec.label,
        summary=summary,
        confidence=confidence,
        pr_supported=False,
        target_subpath=target_subpath,
        entrypoints=entrypoints,
        assumptions=assumptions,
        blockers=blockers,
        env_vars=framework_spec.env_vars,
        install_command=framework_spec.install_command,
        package_name=framework_spec.package_name,
        manual_steps=manual_steps,
        preview_snippet=preview_snippet,
    )


def _build_llm_strategy(
    *,
    proposal: SdkBootstrapFallbackProposal,
    service_name: str,
    environment: str,
) -> SdkBootstrapStrategy:
    framework_spec = get_framework_spec(proposal.framework_id)
    preview_snippet = proposal.preview_snippet
    if preview_snippet is None:
        preview_snippet = (
            _build_generic_javascript_snippet(service_name=service_name, environment=environment)
            if framework_spec.language == "javascript"
            else _build_python_generic_snippet(service_name=service_name, environment=environment)
        )
    manual_steps = (
        _javascript_manual_steps(framework_spec.label)
        if framework_spec.language == "javascript"
        else _python_manual_steps(framework_spec.label)
    )
    return SdkBootstrapStrategy(
        id=f"llm:{proposal.framework_id}:{proposal.target_subpath}:{proposal.entrypoint}",
        language=framework_spec.language,
        framework=framework_spec.label,
        summary=proposal.summary,
        confidence=proposal.confidence,
        pr_supported=proposal.pr_supported,
        target_subpath=proposal.target_subpath,
        entrypoints=[proposal.entrypoint],
        assumptions=list(proposal.assumptions),
        blockers=list(proposal.blockers),
        planned_files=[
            SdkBootstrapPlannedFile(path=item.path, action=item.action, reason=item.reason)
            for item in proposal.planned_files
        ],
        env_vars=framework_spec.env_vars,
        install_command=framework_spec.install_command,
        package_name=framework_spec.package_name,
        manual_steps=manual_steps,
        preview_snippet=preview_snippet,
        source="llm",
        evidence=list(proposal.evidence),
        confidence_reason=proposal.confidence_reason,
        patch_diff=proposal.patch_diff,
    )


def _should_request_fallback_candidates(strategies: list[SdkBootstrapStrategy]) -> bool:
    if not strategies:
        return True
    if not any(item.pr_supported for item in strategies):
        return True
    return not any(
        item.pr_supported and item.source == "deterministic" and item.confidence == "high" for item in strategies
    )


def _rank_preview_candidate_strategies(
    *,
    plan: SdkBootstrapPlan,
    explicit_strategy_id: str | None,
) -> list[SdkBootstrapStrategy]:
    if explicit_strategy_id is not None:
        strategy = _require_strategy(plan, explicit_strategy_id)
        return [strategy]
    ranked = sorted(
        [item for item in plan.strategies if item.pr_supported],
        key=lambda item: (
            3 if item.confidence == "high" else 2 if item.confidence == "medium" else 1,
            1 if item.source == "deterministic" else 0,
        ),
        reverse=True,
    )
    return ranked


def _build_detection_failure_patch(strategy: SdkBootstrapStrategy) -> SdkBootstrapPatch:
    failure_reason = strategy.blockers[0] if strategy.blockers else "No reviewable SDK bootstrap candidate was found."
    attempt = SdkBootstrapPatchAttempt(
        strategy_id=strategy.id,
        patch_source=strategy.source,
        patch_generated=False,
        patch_applied=False,
        verification=SdkBootstrapVerification(status="skipped"),
        preview_available=False,
        change_request_allowed=False,
        failure_stage="detection",
        failure_reason=failure_reason,
        rejection_reason_code="no_reviewable_candidate",
        warnings=list(strategy.blockers[:3]) if strategy.blockers else [failure_reason],
    )
    return SdkBootstrapPatch(patch_diff=None, attempt=attempt)


def _run_sdk_bootstrap_attempts(
    *,
    repo_dir: Path,
    candidate_strategies: list[SdkBootstrapStrategy],
    project_id: str,
    service_name: str,
    environment: str,
    base_url: str,
    api_key: str,
) -> tuple[SdkBootstrapStrategy, SdkBootstrapPatch, SdkBootstrapRun]:
    run = SdkBootstrapRun(run_id=uuid4().hex)
    best_patch: SdkBootstrapPatch | None = None
    best_strategy: SdkBootstrapStrategy | None = None
    for attempt_number, strategy in enumerate(candidate_strategies, start=1):
        _reset_sdk_bootstrap_checkout(repo_dir)
        patch = _build_sdk_bootstrap_patch_from_checkout(
            repo_dir=repo_dir,
            strategy=strategy,
            project_id=project_id,
            service_name=service_name,
            environment=environment,
            base_url=base_url,
            api_key=_resolve_strategy_credential_value(strategy=strategy, credential_value=api_key),
        )
        if patch.attempt is None:
            continue
        patch.attempt.attempt_number = attempt_number
        patch.attempt.candidate_id = strategy.id
        run.attempts.append(patch.attempt)
        if best_patch is None:
            best_patch = patch
            best_strategy = strategy
        if patch.attempt.change_request_allowed:
            run.selected_strategy_id = strategy.id
            run.selected_attempt_number = attempt_number
            run.final_outcome = "preview_ready"
            return strategy, patch, run
        if patch.attempt.preview_available:
            best_patch = patch
            best_strategy = strategy
    if best_patch is None or best_strategy is None:
        best_strategy = candidate_strategies[0]
        best_patch = _build_detection_failure_patch(best_strategy)
        best_patch.attempt.attempt_number = 1
        best_patch.attempt.candidate_id = best_strategy.id
        run.attempts.append(best_patch.attempt)
    run.selected_strategy_id = best_strategy.id
    run.selected_attempt_number = best_patch.attempt.attempt_number
    run.final_outcome = "manual_fallback" if not best_patch.attempt.preview_available else "preview_with_warnings"
    return best_strategy, best_patch, run


def _build_sdk_bootstrap_patch_from_checkout(
    *,
    repo_dir: Path,
    strategy: SdkBootstrapStrategy,
    project_id: str,
    service_name: str,
    environment: str,
    base_url: str,
    api_key: str,
) -> SdkBootstrapPatch:
    attempt = SdkBootstrapPatchAttempt(
        strategy_id=strategy.id,
        patch_source=strategy.source,
        patch_generated=False,
        patch_applied=False,
        verification=SdkBootstrapVerification(status="skipped"),
        preview_available=False,
        change_request_allowed=False,
    )
    generation_started = time.monotonic()
    patch_diff: str | None = None
    if strategy.patch_diff is not None:
        patch_diff = strategy.patch_diff.strip() or None
        if patch_diff:
            attempt.patch_generated = True
    else:
        try:
            _apply_strategy(
                repo_dir=repo_dir,
                strategy=strategy,
                project_id=project_id,
                service_name=service_name,
                environment=environment,
                base_url=base_url,
                api_key=api_key,
            )
            _git(["add", "-A"], cwd=repo_dir)
            patch_diff = _git(["diff", "--cached", "--binary"], cwd=repo_dir)
            patch_diff = patch_diff.strip() or None
            attempt.patch_generated = patch_diff is not None
        except APIError as exc:
            attempt.generation_duration_ms = int((time.monotonic() - generation_started) * 1000)
            attempt.failure_stage = "generation"
            attempt.failure_reason = exc.message
            attempt.rejection_reason_code = exc.code
            attempt.warnings.append(exc.message)
            return SdkBootstrapPatch(patch_diff=None, attempt=attempt)
    attempt.generation_duration_ms = int((time.monotonic() - generation_started) * 1000)
    if patch_diff is None:
        attempt.failure_stage = "generation"
        attempt.failure_reason = "SDK bootstrap patch did not produce any file changes."
        attempt.rejection_reason_code = "empty_patch"
        attempt.warnings.append(attempt.failure_reason)
        return SdkBootstrapPatch(patch_diff=None, attempt=attempt)

    apply_started = time.monotonic()
    try:
        if strategy.patch_diff is not None:
            if (repo_dir / ".git").exists():
                _git(["reset", "--hard"], cwd=repo_dir)
                _git_apply(patch_diff=patch_diff, cwd=repo_dir)
        attempt.patch_applied = True
        if (repo_dir / ".git").exists():
            staged_patch_diff = _git(["diff", "--cached", "--binary"], cwd=repo_dir).strip() or None
            if staged_patch_diff is not None:
                patch_diff = staged_patch_diff
    except APIError as exc:
        attempt.apply_duration_ms = int((time.monotonic() - apply_started) * 1000)
        attempt.failure_stage = "apply"
        attempt.failure_reason = exc.message
        attempt.rejection_reason_code = exc.code
        attempt.warnings.append(exc.message)
        return SdkBootstrapPatch(patch_diff=None, attempt=attempt)
    attempt.apply_duration_ms = int((time.monotonic() - apply_started) * 1000)

    attempt.changed_files = _git(["diff", "--cached", "--name-only"], cwd=repo_dir).splitlines()
    if not attempt.changed_files and patch_diff is not None:
        attempt.changed_files = _extract_patch_paths(patch_diff)
    verification_started = time.monotonic()
    attempt.verification = _verify_sdk_bootstrap_patch(
        repo_dir=repo_dir,
        strategy=strategy,
        changed_files=attempt.changed_files,
    )
    attempt.verification_duration_ms = int((time.monotonic() - verification_started) * 1000)
    attempt.preview_available = True
    attempt.change_request_allowed = attempt.verification.status in {"passed", "needs_review", "skipped"}
    if attempt.verification.status == "failed":
        attempt.failure_stage = "verification"
        attempt.failure_reason = attempt.verification.summary or "SDK bootstrap verification failed."
        attempt.rejection_reason_code = "verification_failed"
        attempt.warnings.append(attempt.failure_reason)
    elif attempt.verification.summary and attempt.verification.status == "needs_review":
        attempt.warnings.append(attempt.verification.summary)
    logger.info(
        "sdk_bootstrap_patch_attempt strategy_id=%s attempt_number=%s patch_source=%s patch_generated=%s patch_applied=%s verification_status=%s change_request_allowed=%s failure_stage=%s rejection_reason_code=%s generation_ms=%s apply_ms=%s verification_ms=%s",
        attempt.strategy_id,
        attempt.attempt_number,
        attempt.patch_source,
        attempt.patch_generated,
        attempt.patch_applied,
        attempt.verification.status,
        attempt.change_request_allowed,
        attempt.failure_stage,
        attempt.rejection_reason_code,
        attempt.generation_duration_ms,
        attempt.apply_duration_ms,
        attempt.verification_duration_ms,
    )
    return SdkBootstrapPatch(patch_diff=patch_diff, attempt=attempt)


def _verify_sdk_bootstrap_patch(
    *,
    repo_dir: Path,
    strategy: SdkBootstrapStrategy,
    changed_files: list[str],
) -> SdkBootstrapVerification:
    if not changed_files:
        return SdkBootstrapVerification(
            status="needs_review",
            summary="Patch was generated but no staged file list was available for focused verification.",
        )
    python_files = [item for item in changed_files if item.endswith(".py")]
    js_checkable_files = [item for item in changed_files if Path(item).suffix.lower() in {".js", ".mjs", ".cjs"}]
    ts_like_files = [
        item for item in changed_files if Path(item).suffix.lower() in {".ts", ".tsx", ".jsx", ".mts", ".cts"}
    ]
    if python_files:
        command = f"{sys.executable} -m py_compile " + " ".join(python_files)
        result = _run_command(
            [sys.executable, "-m", "py_compile", *python_files],
            cwd=repo_dir,
            timeout_seconds=60,
        )
        if result.returncode == 0:
            return SdkBootstrapVerification(
                status="passed",
                command=command,
                summary="Python bootstrap files compiled successfully.",
            )
        return SdkBootstrapVerification(
            status="failed",
            command=command,
            summary="Python bootstrap verification failed.",
            output=(result.stderr or result.stdout).strip() or None,
        )
    if js_checkable_files and not ts_like_files:
        command = f"node --check {js_checkable_files[0]}"
        result = _run_command(
            ["node", "--check", *js_checkable_files],
            cwd=repo_dir,
            timeout_seconds=60,
        )
        if result.returncode == 0:
            return SdkBootstrapVerification(
                status="passed",
                command=command,
                summary="JavaScript bootstrap files passed a syntax check.",
            )
        return SdkBootstrapVerification(
            status="failed",
            command=command,
            summary="JavaScript bootstrap verification failed.",
            output=(result.stderr or result.stdout).strip() or None,
        )
    return SdkBootstrapVerification(
        status="needs_review",
        summary=(
            "Patch applied successfully, but this repository uses frontend file types that need human review "
            "or project-specific tooling before Stimpact can assert a full verification pass."
        ),
    )


def _extract_patch_paths(patch_diff: str) -> list[str]:
    paths: list[str] = []
    for line in patch_diff.splitlines():
        if line.startswith("+++ b/"):
            value = line.removeprefix("+++ b/").strip()
            if value and value != "/dev/null":
                paths.append(value)
    return list(dict.fromkeys(paths))


def _apply_strategy(
    *,
    repo_dir: Path,
    strategy: SdkBootstrapStrategy,
    project_id: str,
    service_name: str,
    environment: str,
    base_url: str,
    api_key: str,
) -> None:
    if strategy.id.startswith("javascript-next:"):
        _apply_next_strategy(
            repo_dir=repo_dir,
            strategy=strategy,
            project_id=project_id,
            service_name=service_name,
            environment=environment,
            base_url=base_url,
            api_key=api_key,
        )
        return
    if strategy.id.startswith("javascript-vite-react:"):
        _apply_vite_react_strategy(
            repo_dir=repo_dir,
            strategy=strategy,
            project_id=project_id,
            service_name=service_name,
            environment=environment,
            base_url=base_url,
            api_key=api_key,
        )
        return
    if strategy.id.startswith("javascript-react-scripts:"):
        _apply_react_scripts_strategy(
            repo_dir=repo_dir,
            strategy=strategy,
            project_id=project_id,
            service_name=service_name,
            environment=environment,
            base_url=base_url,
            api_key=api_key,
        )
        return
    if strategy.id.startswith("javascript-generic-auto:"):
        _apply_generic_javascript_strategy(
            repo_dir=repo_dir,
            strategy=strategy,
            project_id=project_id,
            service_name=service_name,
            environment=environment,
            base_url=base_url,
            api_key=api_key,
        )
        return
    if strategy.id.startswith("python-fastapi:"):
        _apply_python_strategy(
            repo_dir=repo_dir,
            strategy=strategy,
            framework="fastapi",
            project_id=project_id,
            service_name=service_name,
            environment=environment,
            base_url=base_url,
            api_key=api_key,
        )
        return
    if strategy.id.startswith("python-flask:"):
        _apply_python_strategy(
            repo_dir=repo_dir,
            strategy=strategy,
            framework="flask",
            project_id=project_id,
            service_name=service_name,
            environment=environment,
            base_url=base_url,
            api_key=api_key,
        )
        return
    raise APIError(
        f"Strategy {strategy.id} is not supported for automatic PR generation.",
        status_code=400,
        code="sdk_bootstrap_strategy_requires_manual_setup",
    )


def _apply_next_strategy(
    *,
    repo_dir: Path,
    strategy: SdkBootstrapStrategy,
    project_id: str,
    service_name: str,
    environment: str,
    base_url: str,
    api_key: str,
) -> None:
    package_dir = _resolve_subpath(repo_dir, strategy.target_subpath)
    package_data = _read_json(package_dir / "package.json")
    _ensure_package_dependency(package_dir / "package.json", package_data, "@stimpact/sdk", "^0.1.0")
    entrypoint_relative = _entrypoint_relative_to_subpath(strategy)
    target_path = package_dir / entrypoint_relative
    component_path = target_path.parents[1] / "components" / f"stimpact-provider{target_path.suffix}"
    import_path = "../components/stimpact-provider"
    _write_file(component_path, _build_next_provider_source(service_name=service_name, environment=environment))
    target_source = target_path.read_text(encoding="utf-8")
    if "StimpactProvider" not in target_source:
        target_source = _inject_import(
            target_source,
            f'import {{ StimpactProvider }} from "{import_path}";\n',
        )
    if "<StimpactProvider />" not in target_source:
        if "<body" in target_source:
            target_source = re.sub(r"(<body[^>]*>)", r"\1\n        <StimpactProvider />", target_source, count=1)
        elif "<Component" in target_source:
            target_source = target_source.replace(
                "<Component {...pageProps} />",
                "<>\n      <StimpactProvider />\n      <Component {...pageProps} />\n    </>",
                1,
            )
        else:
            raise APIError(
                f"Could not inject StimpactProvider into {target_path.relative_to(repo_dir)}.",
                status_code=400,
                code="sdk_bootstrap_injection_failed",
            )
    target_path.write_text(target_source, encoding="utf-8")
    _ensure_env_file(
        package_dir / ".env.example",
        [
            ("NEXT_PUBLIC_STIMPACT_BASE_URL", base_url),
            ("NEXT_PUBLIC_STIMPACT_PROJECT_ID", project_id),
            ("NEXT_PUBLIC_STIMPACT_BROWSER_KEY", api_key),
        ],
    )


def _apply_vite_react_strategy(
    *,
    repo_dir: Path,
    strategy: SdkBootstrapStrategy,
    project_id: str,
    service_name: str,
    environment: str,
    base_url: str,
    api_key: str,
) -> None:
    package_dir = _resolve_subpath(repo_dir, strategy.target_subpath)
    package_data = _read_json(package_dir / "package.json")
    _ensure_package_dependency(package_dir / "package.json", package_data, "@stimpact/sdk", "^0.1.0")
    entrypoint_relative = _entrypoint_relative_to_subpath(strategy)
    entrypoint_path = package_dir / entrypoint_relative
    helper_suffix = ".ts" if entrypoint_path.suffix in {".ts", ".tsx"} else ".js"
    helper_path = entrypoint_path.parent / f"stimpact{helper_suffix}"
    _write_file(helper_path, _build_vite_helper_source(service_name=service_name, environment=environment))
    source = entrypoint_path.read_text(encoding="utf-8")
    if 'installStimpact' not in source:
        source = _inject_import(source, 'import { installStimpact } from "./stimpact";\n')
    if "installStimpact();" not in source:
        insertion_pattern = r"(ReactDOM\.createRoot|createRoot\()"
        match = re.search(insertion_pattern, source)
        if match:
            source = f"{source[:match.start()]}installStimpact();\n\n{source[match.start():]}"
        else:
            source = f"{source.rstrip()}\n\ninstallStimpact();\n"
    entrypoint_path.write_text(source, encoding="utf-8")
    _ensure_env_file(
        package_dir / ".env.example",
        [
            ("VITE_STIMPACT_BASE_URL", base_url),
            ("VITE_STIMPACT_PROJECT_ID", project_id),
            ("VITE_STIMPACT_BROWSER_KEY", api_key),
        ],
    )


def _apply_react_scripts_strategy(
    *,
    repo_dir: Path,
    strategy: SdkBootstrapStrategy,
    project_id: str,
    service_name: str,
    environment: str,
    base_url: str,
    api_key: str,
) -> None:
    package_dir = _resolve_subpath(repo_dir, strategy.target_subpath)
    package_data = _read_json(package_dir / "package.json")
    _ensure_package_dependency(package_dir / "package.json", package_data, "@stimpact/sdk", "^0.1.0")
    entrypoint_relative = _entrypoint_relative_to_subpath(strategy)
    entrypoint_path = package_dir / entrypoint_relative
    helper_suffix = ".ts" if entrypoint_path.suffix in {".ts", ".tsx"} else ".js"
    helper_filename = f"stimpact{helper_suffix}"
    helper_path = entrypoint_path.parent / helper_filename
    _write_file(helper_path, _build_react_scripts_helper_source(service_name=service_name, environment=environment))
    source = entrypoint_path.read_text(encoding="utf-8")
    if "installStimpact" not in source:
        source = _inject_import(source, f'import {{ installStimpact }} from "./{helper_filename.removesuffix(helper_suffix)}";\n')
    if "installStimpact();" not in source:
        insertion_pattern = r"(ReactDOM\.createRoot|createRoot\(|ReactDOM\.render\(|render\()"
        match = re.search(insertion_pattern, source)
        if match:
            source = f"{source[:match.start()]}installStimpact();\n\n{source[match.start():]}"
        else:
            source = f"{source.rstrip()}\n\ninstallStimpact();\n"
    entrypoint_path.write_text(source, encoding="utf-8")
    _ensure_env_file(
        package_dir / ".env.example",
        [
            ("REACT_APP_STIMPACT_BASE_URL", base_url),
            ("REACT_APP_STIMPACT_PROJECT_ID", project_id),
            ("REACT_APP_STIMPACT_BROWSER_KEY", api_key),
        ],
    )


def _apply_python_strategy(
    *,
    repo_dir: Path,
    strategy: SdkBootstrapStrategy,
    framework: str,
    project_id: str,
    service_name: str,
    environment: str,
    base_url: str,
    api_key: str,
) -> None:
    project_dir = _resolve_subpath(repo_dir, strategy.target_subpath)
    dependency_target = _detect_python_dependency_target(project_dir)
    if dependency_target is None:
        raise APIError(
            "A supported Python dependency manifest was not found for automatic SDK installation.",
            status_code=400,
            code="sdk_bootstrap_invalid_python_manifest",
        )
    _ensure_python_dependency(dependency_target, "stimpact-sdk")
    helper_path = project_dir / "stimpact_bootstrap.py"
    helper_source = (
        _build_fastapi_helper_source(service_name=service_name, environment=environment)
        if framework == "fastapi"
        else _build_flask_helper_source(service_name=service_name, environment=environment)
    )
    _write_file(helper_path, helper_source)
    entrypoint_relative = _entrypoint_relative_to_subpath(strategy)
    entrypoint_path = project_dir / entrypoint_relative
    entrypoint_source = entrypoint_path.read_text(encoding="utf-8")
    app_variable = _detect_python_app_variable(entrypoint_source, framework)
    import_name = "install_fastapi_stimpact" if framework == "fastapi" else "install_flask_stimpact"
    if import_name not in entrypoint_source:
        entrypoint_source = _inject_import(
            entrypoint_source,
            f"from stimpact_bootstrap import {import_name}\n",
        )
    if f"{import_name}({app_variable})" not in entrypoint_source:
        assignment_pattern = rf"(?m)^(\s*{re.escape(app_variable)}\s*=\s*.*)$"
        match = re.search(assignment_pattern, entrypoint_source)
        if not match:
            raise APIError(
                f"Could not identify a supported {framework} app assignment in {entrypoint_path.relative_to(repo_dir)}.",
                status_code=400,
                code="sdk_bootstrap_entrypoint_not_found",
            )
        insertion = f"{match.group(1)}\n{import_name}({app_variable})"
        entrypoint_source = (
            f"{entrypoint_source[:match.start()]}{insertion}{entrypoint_source[match.end():]}"
        )
    entrypoint_path.write_text(entrypoint_source, encoding="utf-8")
    _ensure_env_file(
        project_dir / ".env.example",
        [
            ("STIMPACT_BASE_URL", base_url),
            ("STIMPACT_PROJECT_ID", project_id),
            ("STIMPACT_API_KEY", api_key),
        ],
    )


def _apply_generic_javascript_strategy(
    *,
    repo_dir: Path,
    strategy: SdkBootstrapStrategy,
    project_id: str,
    service_name: str,
    environment: str,
    base_url: str,
    api_key: str,
) -> None:
    package_dir = _resolve_subpath(repo_dir, strategy.target_subpath)
    package_data = _read_json(package_dir / "package.json")
    _ensure_package_dependency(package_dir / "package.json", package_data, "@stimpact/sdk", "^0.1.0")
    entrypoint_relative = _entrypoint_relative_to_subpath(strategy)
    entrypoint_path = package_dir / entrypoint_relative
    source = entrypoint_path.read_text(encoding="utf-8")
    helper_suffix = ".ts" if entrypoint_path.suffix in {".ts", ".tsx", ".mts", ".cts"} else ".js"
    helper_stem = "stimpact"
    helper_path = entrypoint_path.parent / f"{helper_stem}{helper_suffix}"
    module_style = "cjs" if "require(" in source and "import " not in source else "esm"
    _write_file(
        helper_path,
        _build_generic_node_helper_source(
            service_name=service_name,
            environment=environment,
            module_style=module_style,
        ),
    )
    relative_import = f"./{helper_stem}"
    if module_style == "cjs":
        if 'const { installStimpact } = require("./stimpact");' not in source:
            source = f'const {{ installStimpact }} = require("{relative_import}");\n{source}'
    else:
        if 'import { installStimpact } from "./stimpact";' not in source:
            source = _inject_import(source, f'import {{ installStimpact }} from "{relative_import}";\n')
    if "installStimpact();" not in source:
        source = f"installStimpact();\n{source}"
    entrypoint_path.write_text(source, encoding="utf-8")
    _ensure_env_file(
        package_dir / ".env.example",
        [
            ("STIMPACT_BASE_URL", base_url),
            ("STIMPACT_PROJECT_ID", project_id),
            ("STIMPACT_API_KEY", api_key),
        ],
    )


def _candidate_manifest_dirs(repo_dir: Path, manifest_name: str) -> list[Path]:
    candidates: list[Path] = []
    for path in [repo_dir, *(repo_dir / name for name in _ROOT_MANIFEST_DIR_NAMES)]:
        manifest_path = path / manifest_name
        if manifest_path.exists():
            candidates.append(path)
    for parent in _NESTED_MANIFEST_PARENT_DIR_NAMES:
        parent_dir = repo_dir / parent
        if not parent_dir.is_dir():
            continue
        for child in sorted(parent_dir.iterdir()):
            manifest_path = child / manifest_name
            if child.is_dir() and manifest_path.exists():
                candidates.append(child)
            if not child.is_dir():
                continue
            for grandchild in sorted(child.iterdir()):
                manifest_path = grandchild / manifest_name
                if grandchild.is_dir() and manifest_path.exists():
                    candidates.append(grandchild)
    return _dedupe_paths(candidates)


def _candidate_python_project_dirs(repo_dir: Path) -> list[Path]:
    candidates = _candidate_manifest_dirs(repo_dir, "requirements.txt")
    candidates.extend(_candidate_manifest_dirs(repo_dir, "requirements.in"))
    candidates.extend(_candidate_manifest_dirs(repo_dir, "pyproject.toml"))
    candidates.extend(_candidate_manifest_dirs(repo_dir, "Pipfile"))
    candidates.extend(_candidate_manifest_dirs(repo_dir, "setup.py"))
    return _dedupe_paths(candidates)


def _find_python_entrypoint(project_dir: Path) -> tuple[str, Path] | None:
    preferred = [
        project_dir / "main.py",
        project_dir / "app.py",
        project_dir / "server.py",
        project_dir / "src" / "main.py",
        project_dir / "src" / "app.py",
        project_dir / "src" / "server.py",
    ]
    for path in preferred:
        if not path.exists():
            continue
        framework = _detect_python_framework(path.read_text(encoding="utf-8"))
        if framework is not None:
            return framework, path
    for path in sorted(project_dir.rglob("*.py")):
        if any(part.startswith(".") or part in {"node_modules", "__pycache__", "venv", ".venv"} for part in path.parts):
            continue
        framework = _detect_python_framework(path.read_text(encoding="utf-8"))
        if framework is not None:
            return framework, path
    return None


def _detect_python_framework(source: str) -> str | None:
    if "FastAPI(" in source or "from fastapi import FastAPI" in source:
        return "fastapi"
    if "Flask(" in source or "from flask import Flask" in source:
        return "flask"
    return None


def _detect_python_dependency_target(project_dir: Path) -> Path | None:
    requirements_path = project_dir / "requirements.txt"
    if requirements_path.exists():
        return requirements_path
    requirements_in_path = project_dir / "requirements.in"
    if requirements_in_path.exists():
        return requirements_in_path
    pyproject_path = project_dir / "pyproject.toml"
    if pyproject_path.exists():
        text = pyproject_path.read_text(encoding="utf-8")
        if "[project]" in text or "[tool.poetry.dependencies]" in text:
            return pyproject_path
    pipfile_path = project_dir / "Pipfile"
    if pipfile_path.exists():
        return pipfile_path
    return None


def _ensure_python_dependency(path: Path, dependency_name: str) -> None:
    if path.name in {"requirements.txt", "requirements.in"}:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if dependency_name not in text:
            suffix = "" if not text or text.endswith("\n") else "\n"
            path.write_text(f"{text}{suffix}{dependency_name}\n", encoding="utf-8")
        return
    text = path.read_text(encoding="utf-8")
    if dependency_name in text:
        return
    if "[project]" in text and "dependencies = [" in text:
        updated = re.sub(
            r"dependencies\s*=\s*\[(.*?)\]",
            lambda match: f'dependencies = [{match.group(1).rstrip()}\n    "{dependency_name}",\n]',
            text,
            count=1,
            flags=re.DOTALL,
        )
        path.write_text(updated, encoding="utf-8")
        return
    if "[tool.poetry.dependencies]" in text:
        updated = re.sub(
            r"(\[tool\.poetry\.dependencies\]\n)",
            rf"\1{dependency_name} = \"*\"\n",
            text,
            count=1,
        )
        path.write_text(updated, encoding="utf-8")
        return
    if "[packages]" in text:
        updated = re.sub(
            r"(\[packages\]\n)",
            rf"\1{dependency_name} = \"*\"\n",
            text,
            count=1,
        )
        path.write_text(updated, encoding="utf-8")
        return
    raise APIError(
        f"Could not add {dependency_name} to {path.name}.",
        status_code=400,
        code="sdk_bootstrap_invalid_python_manifest",
    )


def _ensure_package_dependency(path: Path, package_data: dict[str, object], dependency_name: str, version: str) -> None:
    dependencies = package_data.setdefault("dependencies", {})
    if not isinstance(dependencies, dict):
        raise APIError(
            "package.json dependencies must be a JSON object for SDK bootstrap.",
            status_code=400,
            code="sdk_bootstrap_invalid_package_json",
        )
    if dependency_name not in dependencies:
        dependencies[dependency_name] = version
    path.write_text(f"{json.dumps(package_data, indent=2)}\n", encoding="utf-8")


def _package_dependency_names(package_json: dict[str, object]) -> set[str]:
    names: set[str] = set()
    for key in ("dependencies", "devDependencies"):
        value = package_json.get(key)
        if isinstance(value, dict):
            names.update(str(item) for item in value)
    return names


def _uses_react_scripts(package_json: dict[str, object]) -> bool:
    if "react-scripts" in _package_dependency_names(package_json):
        return True
    scripts = package_json.get("scripts")
    if not isinstance(scripts, dict):
        return False
    return any("react-scripts" in str(value) for value in scripts.values())


def _find_generic_javascript_entrypoint(package_dir: Path, package_json: dict[str, object]) -> str | None:
    path_candidates: list[str] = []
    for key in ("main", "module"):
        value = package_json.get(key)
        if isinstance(value, str) and value.strip():
            path_candidates.append(value.strip().lstrip("./"))
    scripts = package_json.get("scripts")
    if isinstance(scripts, dict):
        pattern = re.compile(
            r"(?P<path>(?:\.?/)?(?:src|app|apps|packages|services|server|client|web|api|workers?)[\\w./-]*\\.(?:js|mjs|cjs|ts|mts|cts))"
        )
        for command in scripts.values():
            if not isinstance(command, str):
                continue
            for match in pattern.finditer(command):
                path_candidates.append(match.group("path").lstrip("./"))
    path_candidates.extend(
        [
            "src/index.ts",
            "src/index.js",
            "src/server.ts",
            "src/server.js",
            "src/main.ts",
            "src/main.js",
            "server.ts",
            "server.js",
            "main.ts",
            "main.js",
            "index.ts",
            "index.js",
            "src/worker.ts",
            "src/worker.js",
            "worker.ts",
            "worker.js",
        ]
    )
    seen: set[str] = set()
    for candidate in path_candidates:
        normalized = candidate.strip().lstrip("./")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        target = package_dir / normalized
        if target.exists():
            return normalized
    return None


def _vite_react_entrypoint_candidates(package_dir: Path) -> list[str]:
    candidates = [
        "src/main.tsx",
        "src/main.jsx",
        "src/main.ts",
        "src/main.js",
        "src/index.tsx",
        "src/index.jsx",
        "src/index.ts",
        "src/index.js",
        "src/bootstrap.tsx",
        "src/bootstrap.jsx",
        "src/bootstrap.ts",
        "src/bootstrap.js",
        "src/client.tsx",
        "src/client.jsx",
        "src/client.ts",
        "src/client.js",
    ]
    vite_root = _detect_vite_client_root(package_dir)
    if vite_root is not None:
        for relative in list(candidates):
            nested_candidate = f"{vite_root}/{relative}"
            if nested_candidate not in candidates:
                candidates.append(nested_candidate)
    return candidates


def _detect_vite_client_root(package_dir: Path) -> str | None:
    vite_config_names = ("vite.config.ts", "vite.config.js", "vite.config.mts", "vite.config.mjs")
    root_pattern = re.compile(r'root:\s*path\.resolve\(import\.meta\.dirname,\s*["\']([^"\']+)["\']\)')
    for config_name in vite_config_names:
        config_path = package_dir / config_name
        if not config_path.exists():
            continue
        source = config_path.read_text(encoding="utf-8", errors="ignore")
        match = root_pattern.search(source)
        if not match:
            continue
        candidate = match.group(1).strip().strip("/")
        if candidate and (package_dir / candidate).is_dir():
            return candidate
    return None


def _pick_recommended_strategy_id(strategies: list[SdkBootstrapStrategy]) -> str | None:
    if not strategies:
        return None
    ranking = {"high": 3, "medium": 2, "low": 1}
    sorted_strategies = sorted(
        strategies,
        key=lambda item: (
            1 if item.pr_supported else 0,
            ranking.get(item.confidence, 0),
            1 if item.source == "deterministic" else 0,
        ),
        reverse=True,
    )
    return sorted_strategies[0].id


def _require_strategy(plan: SdkBootstrapPlan, strategy_id: str) -> SdkBootstrapStrategy:
    for strategy in plan.strategies:
        if strategy.id == strategy_id:
            return strategy
    raise APIError(
        f"SDK bootstrap strategy {strategy_id} was not found.",
        status_code=404,
        code="sdk_bootstrap_strategy_not_found",
    )


def _entrypoint_relative_to_subpath(strategy: SdkBootstrapStrategy) -> Path:
    if not strategy.entrypoints:
        raise APIError(
            f"Strategy {strategy.id} has no entrypoint configured.",
            status_code=400,
            code="sdk_bootstrap_entrypoint_not_found",
        )
    entrypoint = strategy.entrypoints[0]
    if strategy.target_subpath == ".":
        return Path(entrypoint)
    return Path(entrypoint.removeprefix(f"{strategy.target_subpath}/"))


def _resolve_strategy_credential_value(*, strategy: SdkBootstrapStrategy, credential_value: str) -> str:
    if credential_value != SDK_BOOTSTRAP_API_KEY_PLACEHOLDER:
        return credential_value
    if any(
        item.name.startswith("NEXT_PUBLIC_")
        or item.name.startswith("VITE_")
        or item.name.startswith("REACT_APP_")
        for item in strategy.env_vars
    ):
        return SDK_BOOTSTRAP_BROWSER_KEY_PLACEHOLDER
    return credential_value


def _resolve_subpath(repo_dir: Path, subpath: str) -> Path:
    return repo_dir if subpath == "." else repo_dir / subpath


def _relative_display_path(base: Path, target: Path) -> str:
    try:
        relative = target.relative_to(base)
    except ValueError:
        return str(target)
    return "." if str(relative) == "." else relative.as_posix()


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    ordered: list[Path] = []
    for path in paths:
        normalized = str(path.resolve())
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(path)
    return ordered


def _inject_import(source: str, import_statement: str) -> str:
    if import_statement.strip() in source:
        return source
    import_matches = list(re.finditer(r"^(?:from .+ import .+|import .+)\n", source, flags=re.MULTILINE))
    if import_matches:
        last_import = import_matches[-1]
        insert_at = last_import.end()
        return f"{source[:insert_at]}{import_statement}{source[insert_at:]}"
    return f"{import_statement}\n{source}"


def _write_file(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents if contents.endswith("\n") else f"{contents}\n", encoding="utf-8")


def _ensure_env_file(path: Path, entries: list[tuple[str, str]]) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = existing.splitlines()
    if "# Stimpact telemetry" not in lines:
        lines.extend(["", "# Stimpact telemetry"])
    for key, value in entries:
        line = f"{key}={value}"
        if line not in lines and not any(item.startswith(f"{key}=") for item in lines):
            lines.append(line)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _build_next_provider_source(*, service_name: str, environment: str) -> str:
    return f'''"use client";

import {{ useEffect }} from "react";
import {{ StimpactClient }} from "@stimpact/sdk";

let stimpactClient: StimpactClient | null = null;

export function getStimpactClient(): StimpactClient | null {{
  return stimpactClient;
}}

export async function pingStimpact(): Promise<void> {{
  if (!stimpactClient) {{
    return;
  }}
  await stimpactClient.ping();
}}

function syncWindowStimpactControls() {{
  if (typeof window === "undefined") {{
    return;
  }}
  const scope = window as Window & {{
    __stimpact?: {{
      ping: typeof pingStimpact;
      getClient: typeof getStimpactClient;
    }};
    pingStimpact?: typeof pingStimpact;
  }};
  if (stimpactClient) {{
    scope.pingStimpact = pingStimpact;
    scope.__stimpact = {{
      ping: pingStimpact,
      getClient: getStimpactClient,
    }};
    return;
  }}
  if (scope.pingStimpact === pingStimpact) {{
    delete scope.pingStimpact;
  }}
  if (scope.__stimpact?.ping === pingStimpact) {{
    delete scope.__stimpact;
  }}
}}

export function StimpactProvider() {{
  useEffect(() => {{
    const baseUrl = process.env.NEXT_PUBLIC_STIMPACT_BASE_URL;
    const projectId = process.env.NEXT_PUBLIC_STIMPACT_PROJECT_ID;
    const browserKey = process.env.NEXT_PUBLIC_STIMPACT_BROWSER_KEY;
    const service = "{service_name}";
    const runtimeEnvironment = "{environment}";

    if (!baseUrl || !projectId || !browserKey || !service) {{
      return;
    }}

    const client = new StimpactClient({{
      baseUrl,
      projectId,
      browserKey,
      service,
      environment: runtimeEnvironment,
    }});
    stimpactClient = client;
    syncWindowStimpactControls();

    const heartbeat = client.startHeartbeat();
    const subscription = client.registerBrowserAutoCapture();
    return () => {{
      heartbeat.dispose();
      subscription.dispose();
      if (stimpactClient === client) {{
        stimpactClient = null;
        syncWindowStimpactControls();
      }}
    }};
  }}, []);

  return null;
}}
'''


def _build_vite_helper_source(*, service_name: str, environment: str) -> str:
    return f'''import {{ StimpactClient }} from "@stimpact/sdk";

let installed = false;
let stimpactClient: StimpactClient | null = null;

export function getStimpactClient(): StimpactClient | null {{
  return stimpactClient;
}}

export async function pingStimpact(): Promise<void> {{
  if (!stimpactClient) {{
    return;
  }}
  await stimpactClient.ping();
}}

function syncWindowStimpactControls() {{
  if (typeof window === "undefined") {{
    return;
  }}
  const scope = window as Window & {{
    __stimpact?: {{
      ping: typeof pingStimpact;
      getClient: typeof getStimpactClient;
    }};
    pingStimpact?: typeof pingStimpact;
  }};
  if (stimpactClient) {{
    scope.pingStimpact = pingStimpact;
    scope.__stimpact = {{
      ping: pingStimpact,
      getClient: getStimpactClient,
    }};
    return;
  }}
  if (scope.pingStimpact === pingStimpact) {{
    delete scope.pingStimpact;
  }}
  if (scope.__stimpact?.ping === pingStimpact) {{
    delete scope.__stimpact;
  }}
}}

export function installStimpact() {{
  if (installed) {{
    return;
  }}
  installed = true;

  const baseUrl = import.meta.env.VITE_STIMPACT_BASE_URL;
  const projectId = import.meta.env.VITE_STIMPACT_PROJECT_ID;
  const browserKey = import.meta.env.VITE_STIMPACT_BROWSER_KEY;
  const service = "{service_name}";
  const runtimeEnvironment = "{environment}";

  if (!baseUrl || !projectId || !browserKey || !service) {{
    return;
  }}

  const client = new StimpactClient({{
    baseUrl,
    projectId,
    browserKey,
    service,
    environment: runtimeEnvironment,
  }});
  stimpactClient = client;
  syncWindowStimpactControls();

  client.startHeartbeat();
  client.registerBrowserAutoCapture();
}}
'''


def _build_react_scripts_helper_source(*, service_name: str, environment: str) -> str:
    return f'''import {{ StimpactClient }} from "@stimpact/sdk";

let installed = false;
let stimpactClient: StimpactClient | null = null;

export function getStimpactClient(): StimpactClient | null {{
  return stimpactClient;
}}

export async function pingStimpact(): Promise<void> {{
  if (!stimpactClient) {{
    return;
  }}
  await stimpactClient.ping();
}}

function syncWindowStimpactControls() {{
  if (typeof window === "undefined") {{
    return;
  }}
  const scope = window as Window & {{
    __stimpact?: {{
      ping: typeof pingStimpact;
      getClient: typeof getStimpactClient;
    }};
    pingStimpact?: typeof pingStimpact;
  }};
  if (stimpactClient) {{
    scope.pingStimpact = pingStimpact;
    scope.__stimpact = {{
      ping: pingStimpact,
      getClient: getStimpactClient,
    }};
    return;
  }}
  if (scope.pingStimpact === pingStimpact) {{
    delete scope.pingStimpact;
  }}
  if (scope.__stimpact?.ping === pingStimpact) {{
    delete scope.__stimpact;
  }}
}}

export function installStimpact() {{
  if (installed) {{
    return;
  }}
  installed = true;

  const baseUrl = process.env.REACT_APP_STIMPACT_BASE_URL;
  const projectId = process.env.REACT_APP_STIMPACT_PROJECT_ID;
  const browserKey = process.env.REACT_APP_STIMPACT_BROWSER_KEY;
  const service = "{service_name}";
  const runtimeEnvironment = "{environment}";

  if (!baseUrl || !projectId || !browserKey || !service) {{
    return;
  }}

  const client = new StimpactClient({{
    baseUrl,
    projectId,
    browserKey,
    service,
    environment: runtimeEnvironment,
  }});
  stimpactClient = client;
  syncWindowStimpactControls();

  client.startHeartbeat();
  client.registerBrowserAutoCapture();
}}
'''


def _build_fastapi_helper_source(*, service_name: str, environment: str) -> str:
    return f'''from stimpact_sdk import StimpactClient


def install_fastapi_stimpact(app) -> None:
    client = StimpactClient.from_env(
        service="{service_name}",
        environment="{environment}",
    )

    app.state.stimpact_heartbeat = client.start_heartbeat()

    @app.middleware("http")
    async def stimpact_capture_middleware(request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            client.capture_exception(
                exc,
                request={{
                    "method": request.method,
                    "url": str(request.url),
                }},
            )
            raise
'''


def _build_flask_helper_source(*, service_name: str, environment: str) -> str:
    return f'''from flask import got_request_exception, request

from stimpact_sdk import StimpactClient


def install_flask_stimpact(app) -> None:
    client = StimpactClient.from_env(
        service="{service_name}",
        environment="{environment}",
    )

    app.extensions["stimpact_heartbeat"] = client.start_heartbeat()

    def _capture(sender, exception, **extra):
        client.capture_exception(
            exception,
            request={{
                "method": request.method,
                "url": request.url,
            }},
        )

    got_request_exception.connect(_capture, app)
'''


def _build_generic_javascript_snippet(*, service_name: str, environment: str) -> str:
    return f'''import {{ StimpactClient }} from "@stimpact/sdk";

const stimpact = new StimpactClient({{
  baseUrl: "<public-stimpact-url>",
  projectId: "<project-id>",
  browserKey: "<browser-key>",
  service: "{service_name}",
  environment: "{environment}",
}});

stimpact.startHeartbeat();
stimpact.registerBrowserAutoCapture();

export async function pingStimpact() {{
  await stimpact.ping();
}}

if (typeof window !== "undefined") {{
  const scope = window as Window & {{
    __stimpact?: {{
      ping: typeof pingStimpact;
      getClient: () => StimpactClient;
    }};
    pingStimpact?: typeof pingStimpact;
  }};
  scope.pingStimpact = pingStimpact;
  scope.__stimpact = {{
    ping: pingStimpact,
    getClient: () => stimpact,
  }};
}}
'''


def _build_generic_node_helper_source(*, service_name: str, environment: str, module_style: str) -> str:
    if module_style == "cjs":
        return f'''const {{ StimpactClient }} = require("@stimpact/sdk");

let installed = false;
let stimpactClient = null;

function getStimpactClient() {{
  return stimpactClient;
}}

async function pingStimpact() {{
  if (!stimpactClient) {{
    return;
  }}
  await stimpactClient.ping();
}}

function installStimpact() {{
  if (installed) {{
    return;
  }}
  installed = true;

  const baseUrl = process.env.STIMPACT_BASE_URL;
  const projectId = process.env.STIMPACT_PROJECT_ID;
  const apiKey = process.env.STIMPACT_API_KEY;
  const service = "{service_name}";
  const runtimeEnvironment = "{environment}";

  if (!baseUrl || !projectId || !apiKey || !service) {{
    return;
  }}

  const client = new StimpactClient({{
    baseUrl,
    projectId,
    apiKey,
    service,
    environment: runtimeEnvironment,
  }});
  stimpactClient = client;

  client.startHeartbeat();

  const capture = (error) => {{
    const exception = error instanceof Error ? error : new Error(String(error));
    void client.captureError({{ error: exception }});
  }};

  process.on("uncaughtException", capture);
  process.on("unhandledRejection", capture);
}}

module.exports = {{ installStimpact, getStimpactClient, pingStimpact }};
'''
    return f'''import {{ StimpactClient }} from "@stimpact/sdk";

let installed = false;
let stimpactClient: StimpactClient | null = null;

export function getStimpactClient(): StimpactClient | null {{
  return stimpactClient;
}}

export async function pingStimpact(): Promise<void> {{
  if (!stimpactClient) {{
    return;
  }}
  await stimpactClient.ping();
}}

export function installStimpact() {{
  if (installed) {{
    return;
  }}
  installed = true;

  const baseUrl = process.env.STIMPACT_BASE_URL;
  const projectId = process.env.STIMPACT_PROJECT_ID;
  const apiKey = process.env.STIMPACT_API_KEY;
  const service = "{service_name}";
  const runtimeEnvironment = "{environment}";

  if (!baseUrl || !projectId || !apiKey || !service) {{
    return;
  }}

  const client = new StimpactClient({{
    baseUrl,
    projectId,
    apiKey,
    service,
    environment: runtimeEnvironment,
  }});
  stimpactClient = client;

  client.startHeartbeat();

  const capture = (error: unknown) => {{
    const exception = error instanceof Error ? error : new Error(String(error));
    void client.captureError({{ error: exception }});
  }};

  process.on("uncaughtException", capture);
  process.on("unhandledRejection", capture);
}}
'''


def _build_python_generic_snippet(*, service_name: str, environment: str) -> str:
    return f'''from stimpact_sdk import StimpactClient

client = StimpactClient.from_env(
    service="{service_name}",
    environment="{environment}",
)

client.start_heartbeat()

try:
    do_work()
except Exception as exc:
    client.capture_exception(exc)
    raise
'''


def _clone_sdk_bootstrap_repo(*, clone_url: str, default_branch: str, repo_dir: Path) -> None:
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
        ]
    )
    _git(["checkout", default_branch], cwd=repo_dir)


def _javascript_manual_steps(label: str) -> list[SdkBootstrapManualStep]:
    return [
        SdkBootstrapManualStep(
            title="Install the SDK",
            content="Run the listed install command in the detected JavaScript app package, then expose the documented environment variables through your frontend build system.",
        ),
        SdkBootstrapManualStep(
            title=f"Wire the {label} runtime",
            content="Initialize `StimpactClient` in the main browser shell, start heartbeats, enable `registerBrowserAutoCapture()`, and keep the exported `pingStimpact()` helper available for future manual live checks.",
        ),
    ]


def _python_manual_steps(label: str) -> list[SdkBootstrapManualStep]:
    return [
        SdkBootstrapManualStep(
            title="Install the SDK",
            content="Add `stimpact-sdk` to the detected Python dependency manifest and set the documented `STIMPACT_*` environment variables in your runtime environment.",
        ),
        SdkBootstrapManualStep(
            title=f"Wire the {label} app",
            content="Create a shared Stimpact client, start the background heartbeat, and capture unhandled exceptions in the HTTP request lifecycle for the chosen Python app entrypoint.",
        ),
    ]


def _detect_python_app_variable(source: str, framework: str) -> str:
    pattern = r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*FastAPI\(" if framework == "fastapi" else r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*Flask\("
    match = re.search(pattern, source)
    if match:
        return str(match.group(1))
    raise APIError(
        f"Could not identify a supported {framework} application variable.",
        status_code=400,
        code="sdk_bootstrap_entrypoint_not_found",
    )


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise APIError(
            f"{path.name} is not valid JSON.",
            status_code=400,
            code="sdk_bootstrap_invalid_package_json",
        ) from exc
    if not isinstance(payload, dict):
        raise APIError(
            f"{path.name} must contain a JSON object.",
            status_code=400,
            code="sdk_bootstrap_invalid_package_json",
        )
    return payload


def _git(args: list[str], *, cwd: Path | None = None) -> str:
    result = _run_command(["git", *args], cwd=cwd, timeout_seconds=90)
    if result.returncode != 0:
        raise APIError(
            (result.stderr or result.stdout or "Git command failed.").strip(),
            status_code=502,
            code="sdk_bootstrap_git_failed",
        )
    return (result.stdout or result.stderr).strip()


def _git_apply(*, patch_diff: str, cwd: Path) -> None:
    if not (cwd / ".git").exists():
        return
    try:
        result = subprocess.run(
            ["git", "apply", "--index", "--whitespace=nowarn", "-"],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            input=patch_diff,
            timeout=90,
        )
    except subprocess.TimeoutExpired as exc:
        raise APIError(
            "SDK bootstrap timed out while applying the generated patch.",
            status_code=504,
            code="sdk_bootstrap_patch_apply_timeout",
        ) from exc
    if result.returncode != 0:
        raise APIError(
            (result.stderr or result.stdout or "Generated patch could not be applied cleanly.").strip(),
            status_code=409,
            code="sdk_bootstrap_patch_apply_failed",
        )


def _reset_sdk_bootstrap_checkout(repo_dir: Path) -> None:
    if not (repo_dir / ".git").exists():
        return
    _git(["reset", "--hard"], cwd=repo_dir)
    _git(["clean", "-fd"], cwd=repo_dir)


def _run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        command = " ".join(args[:3]).strip()
        raise APIError(
            f"SDK bootstrap timed out while running {command}.",
            status_code=504,
            code="sdk_bootstrap_command_timeout",
        ) from exc
