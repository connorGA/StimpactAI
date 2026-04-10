from __future__ import annotations

from dataclasses import dataclass, field


SAFE_CHANGE_CATEGORY_DEPENDENCY = "dependency_manifest"
SAFE_CHANGE_CATEGORY_RUNTIME = "runtime_wiring"
SAFE_CHANGE_CATEGORY_TOKEN_ROUTE = "token_route"
SAFE_CHANGE_CATEGORY_ENV = "env_example"
SAFE_CHANGE_CATEGORY_DOCS = "documentation"
SAFE_CHANGE_CATEGORY_OTHER = "other"
SAFE_CHANGE_CATEGORY_RUNTIME_COMMAND = "runtime_command"
SAFE_CHANGE_CATEGORY_DEPLOYMENT = "deployment_surface"


@dataclass(slots=True)
class SdkBootstrapHarnessTarget:
    project_id: str
    service: str
    environment: str
    base_url: str
    provider_repository_id: str | None = None
    release: str | None = None


@dataclass(slots=True)
class SdkBootstrapCapabilityGraph:
    runtime: str | None
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    runtime_surfaces: list[str] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)
    target_subpath: str | None = None
    evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SdkBootstrapRecipeStep:
    title: str
    content: str


@dataclass(slots=True)
class SdkBootstrapRecipe:
    recipe_id: str
    summary: str
    manual_steps: list[SdkBootstrapRecipeStep] = field(default_factory=list)


@dataclass(slots=True)
class SdkBootstrapSafeChangePolicy:
    allowed_categories: list[str] = field(default_factory=list)
    prohibited_categories: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def requires_manual_review(self) -> bool:
        return bool(self.prohibited_categories)


@dataclass(slots=True)
class SdkBootstrapPreviewArtifact:
    artifact_id: str
    checksum: str | None
    strategy_id: str
    target: SdkBootstrapHarnessTarget
    safe_change_policy: SdkBootstrapSafeChangePolicy
