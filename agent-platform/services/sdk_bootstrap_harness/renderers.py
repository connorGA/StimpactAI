from __future__ import annotations

from services.sdk_bootstrap_harness.models import SdkBootstrapRecipe


def render_manual_steps(recipe: SdkBootstrapRecipe) -> list[tuple[str, str]]:
    return [(step.title, step.content) for step in recipe.manual_steps]
