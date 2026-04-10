from __future__ import annotations

from services.sdk_bootstrap_harness.models import SdkBootstrapCapabilityGraph


def build_capability_graph(*, runtime: str | None, strategy) -> SdkBootstrapCapabilityGraph:
    frameworks = [strategy.framework] if getattr(strategy, "framework", None) else []
    languages = [strategy.language] if getattr(strategy, "language", None) else []
    runtime_surfaces = [strategy.runtime_surface] if getattr(strategy, "runtime_surface", None) else []
    evidence = []
    evidence.extend(list(getattr(strategy, "evidence", []) or []))
    evidence.extend(list(getattr(strategy, "entrypoints", []) or []))
    return SdkBootstrapCapabilityGraph(
        runtime=runtime or getattr(strategy, "language", None),
        languages=languages,
        frameworks=frameworks,
        runtime_surfaces=runtime_surfaces,
        entrypoints=list(getattr(strategy, "entrypoints", []) or []),
        target_subpath=getattr(strategy, "target_subpath", None),
        evidence=list(dict.fromkeys(item for item in evidence if item)),
    )
