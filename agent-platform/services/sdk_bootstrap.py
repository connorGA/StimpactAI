from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import subprocess
import tempfile

from api.core.errors import APIError
from services.sdk_catalog import SdkEnvVarSpec, get_framework_spec
from services.sdk_bootstrap_fallback import SdkBootstrapFallbackPlanner, SdkBootstrapFallbackProposal

SDK_BOOTSTRAP_API_KEY_PLACEHOLDER = "stimp_live_replace_me"


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
    patch_diff: str


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
        if not strategy.pr_supported:
            raise APIError(
                f"Strategy {strategy_id} is not safe for automatic PR generation.",
                status_code=400,
                code="sdk_bootstrap_strategy_requires_manual_setup",
            )
        if strategy.patch_diff is not None:
            return SdkBootstrapPatch(patch_diff=strategy.patch_diff)
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
        if not patch_diff.strip():
            raise APIError(
                "SDK bootstrap patch did not produce any file changes.",
                status_code=409,
                code="sdk_bootstrap_empty_patch",
            )
        return SdkBootstrapPatch(patch_diff=patch_diff)


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
    if not any(item.pr_supported for item in strategies) and fallback_planner is not None:
        try:
            fallback_proposal = fallback_planner.plan(
                repo_dir=repo_dir,
                service_name=service_name,
                environment=environment,
                project_id=project_id,
                base_url=base_url,
            )
        except Exception:  # noqa: BLE001
            fallback_proposal = None
            warnings.append(
                "Model-assisted SDK bootstrap was unavailable for this repository, so the planner kept the safer manual path."
            )
        if fallback_proposal is not None:
            strategies.append(
                _build_llm_strategy(
                    proposal=fallback_proposal,
                    service_name=service_name,
                    environment=environment,
                )
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
                        content="Pass your project API key, project id, service name, environment, and public Stimpact base URL when constructing `StimpactClient`.",
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
    for relative_path in ("src/main.tsx", "src/main.jsx", "src/main.ts", "src/main.js"):
        target_path = package_dir / relative_path
        if target_path.exists():
            helper_path = package_dir / "src" / "stimpact.ts"
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
            ("NEXT_PUBLIC_STIMPACT_API_KEY", api_key),
            ("NEXT_PUBLIC_STIMPACT_SERVICE", service_name),
            ("NEXT_PUBLIC_STIMPACT_ENVIRONMENT", environment),
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
    helper_path = package_dir / "src" / "stimpact.ts"
    _write_file(helper_path, _build_vite_helper_source(service_name=service_name, environment=environment))
    entrypoint_relative = _entrypoint_relative_to_subpath(strategy)
    entrypoint_path = package_dir / entrypoint_relative
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
            ("VITE_STIMPACT_API_KEY", api_key),
            ("VITE_STIMPACT_SERVICE", service_name),
            ("VITE_STIMPACT_ENVIRONMENT", environment),
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
            ("STIMPACT_SERVICE", service_name),
            ("STIMPACT_ENVIRONMENT", environment),
        ],
    )


def _candidate_manifest_dirs(repo_dir: Path, manifest_name: str) -> list[Path]:
    candidates: list[Path] = []
    for path in [repo_dir, *(repo_dir / name for name in ("frontend", "backend", "client", "server"))]:
        manifest_path = path / manifest_name
        if manifest_path.exists():
            candidates.append(path)
    for parent in ("apps", "packages", "services"):
        parent_dir = repo_dir / parent
        if not parent_dir.is_dir():
            continue
        for child in sorted(parent_dir.iterdir()):
            manifest_path = child / manifest_name
            if child.is_dir() and manifest_path.exists():
                candidates.append(child)
    return _dedupe_paths(candidates)


def _candidate_python_project_dirs(repo_dir: Path) -> list[Path]:
    candidates = _candidate_manifest_dirs(repo_dir, "requirements.txt")
    candidates.extend(_candidate_manifest_dirs(repo_dir, "pyproject.toml"))
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
    pyproject_path = project_dir / "pyproject.toml"
    if pyproject_path.exists():
        text = pyproject_path.read_text(encoding="utf-8")
        if "[project]" in text or "[tool.poetry.dependencies]" in text:
            return pyproject_path
    return None


def _ensure_python_dependency(path: Path, dependency_name: str) -> None:
    if path.name == "requirements.txt":
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


def _pick_recommended_strategy_id(strategies: list[SdkBootstrapStrategy]) -> str | None:
    if not strategies:
        return None
    ranking = {"high": 3, "medium": 2, "low": 1}
    sorted_strategies = sorted(
        strategies,
        key=lambda item: (ranking.get(item.confidence, 0), 1 if item.pr_supported else 0),
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

export function StimpactProvider() {{
  useEffect(() => {{
    const baseUrl = process.env.NEXT_PUBLIC_STIMPACT_BASE_URL;
    const projectId = process.env.NEXT_PUBLIC_STIMPACT_PROJECT_ID;
    const apiKey = process.env.NEXT_PUBLIC_STIMPACT_API_KEY;
    const service = process.env.NEXT_PUBLIC_STIMPACT_SERVICE ?? "{service_name}";
    const runtimeEnvironment =
      process.env.NEXT_PUBLIC_STIMPACT_ENVIRONMENT ?? "{environment}";

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

    const heartbeat = client.startHeartbeat();
    const subscription = client.registerBrowserAutoCapture();
    return () => {{
      heartbeat.dispose();
      subscription.dispose();
    }};
  }}, []);

  return null;
}}
'''


def _build_vite_helper_source(*, service_name: str, environment: str) -> str:
    return f'''import {{ StimpactClient }} from "@stimpact/sdk";

let installed = false;

export function installStimpact() {{
  if (installed) {{
    return;
  }}
  installed = true;

  const baseUrl = import.meta.env.VITE_STIMPACT_BASE_URL;
  const projectId = import.meta.env.VITE_STIMPACT_PROJECT_ID;
  const apiKey = import.meta.env.VITE_STIMPACT_API_KEY;
  const service = import.meta.env.VITE_STIMPACT_SERVICE ?? "{service_name}";
  const runtimeEnvironment =
    import.meta.env.VITE_STIMPACT_ENVIRONMENT ?? "{environment}";

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
  apiKey: "<project-api-key>",
  service: "{service_name}",
  environment: "{environment}",
}});

stimpact.startHeartbeat();
stimpact.registerBrowserAutoCapture();
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
            content="Initialize `StimpactClient` in the main browser shell and enable `registerBrowserAutoCapture()` so uncaught errors are reported automatically.",
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
            content="Create a shared Stimpact client and capture unhandled exceptions in the HTTP request lifecycle for the chosen Python app entrypoint.",
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
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired as exc:
        raise APIError(
            f"SDK bootstrap timed out while running git {' '.join(args[:3])}.",
            status_code=504,
            code="sdk_bootstrap_git_timeout",
        ) from exc
    if result.returncode != 0:
        raise APIError(
            (result.stderr or result.stdout or "Git command failed.").strip(),
            status_code=502,
            code="sdk_bootstrap_git_failed",
        )
    return (result.stdout or result.stderr).strip()
