from __future__ import annotations

from services.sdk_bootstrap_harness.models import (
    SdkBootstrapHarnessTarget,
    SdkBootstrapRecipe,
    SdkBootstrapRecipeStep,
)


def build_recipe(*, strategy, target: SdkBootstrapHarnessTarget) -> SdkBootstrapRecipe:
    label = getattr(strategy, "framework", None) or getattr(strategy, "language", None) or "application"
    runtime_surface = getattr(strategy, "runtime_surface", "server")
    credential_kind = getattr(strategy, "credential_kind", "api_key")
    language = getattr(strategy, "language", "")

    if language == "python":
        return SdkBootstrapRecipe(
            recipe_id="python-server-heartbeat",
            summary=f"Install Stimpact into the {label} app entrypoint without changing deploy commands.",
            manual_steps=[
                SdkBootstrapRecipeStep(
                    title="Install the SDK",
                    content=(
                        "Add `stimpact-sdk` to the detected Python dependency manifest and configure the "
                        "documented `STIMPACT_*` environment variables in the deployed runtime."
                    ),
                ),
                SdkBootstrapRecipeStep(
                    title=f"Wire the {label} app",
                    content=(
                        "Create one shared Stimpact client in the real process entrypoint, start the heartbeat "
                        "loop during application startup, and capture unhandled exceptions inside the framework "
                        "request lifecycle."
                    ),
                ),
            ],
        )

    if runtime_surface == "browser" and credential_kind == "browser_token":
        return SdkBootstrapRecipe(
            recipe_id="browser-token-heartbeat",
            summary=f"Initialize browser telemetry for {label} with a same-origin token route and heartbeat.",
            manual_steps=[
                SdkBootstrapRecipeStep(
                    title="Install the SDK",
                    content=(
                        "Run the listed install command in the detected JavaScript app package, then configure "
                        "the public browser variables plus the server-only token mint key used by your backend route."
                    ),
                ),
                SdkBootstrapRecipeStep(
                    title=f"Wire the {label} runtime",
                    content=(
                        "Initialize `StimpactClient` in the main browser shell with `browserTokenEndpoint` or "
                        "`tokenProvider`, start the heartbeat loop once during app startup, and enable "
                        "`registerBrowserAutoCapture()` so uncaught errors are reported without exposing a reusable key."
                    ),
                ),
                SdkBootstrapRecipeStep(
                    title="Add a same-origin token route",
                    content=(
                        "Create a backend or edge route such as `/api/stimpact-token` that keeps "
                        "`STIMPACT_BROWSER_TOKEN_KEY` on the server, forwards the browser origin to Stimpact, "
                        "and returns only short-lived ingest tokens to the browser."
                    ),
                ),
            ],
        )

    return SdkBootstrapRecipe(
        recipe_id="server-api-key-heartbeat",
        summary=f"Install Stimpact into the {label} service entrypoint without changing start or deploy commands.",
        manual_steps=[
            SdkBootstrapRecipeStep(
                title="Install the SDK",
                content=(
                    "Run the listed install command in the detected JavaScript service package, then configure the "
                    "server-side `STIMPACT_*` environment variables including the project telemetry key."
                ),
            ),
            SdkBootstrapRecipeStep(
                title=f"Wire the {label} runtime",
                content=(
                    "Initialize `StimpactClient` with `apiKey` in the real process entrypoint, start the heartbeat "
                    "loop once during startup, and capture uncaught exceptions or unhandled rejections in the server runtime."
                ),
            ),
        ],
    )
