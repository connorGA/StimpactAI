from __future__ import annotations

from dataclasses import dataclass

from api.core.errors import APIError


@dataclass(slots=True)
class SdkEnvVarSpec:
    name: str
    example_value: str
    description: str


@dataclass(slots=True)
class SdkFrameworkSpec:
    id: str
    language: str
    label: str
    package_name: str
    install_command: str
    env_vars: list[SdkEnvVarSpec]


_FRAMEWORK_SPECS: dict[str, SdkFrameworkSpec] = {
    "javascript-next": SdkFrameworkSpec(
        id="javascript-next",
        language="javascript",
        label="Next.js",
        package_name="@stimpact/sdk",
        install_command="npm install @stimpact/sdk",
        env_vars=[
            SdkEnvVarSpec(
                name="NEXT_PUBLIC_STIMPACT_BASE_URL",
                example_value="https://stimpact.example.com",
                description="Public Stimpact telemetry base URL.",
            ),
            SdkEnvVarSpec(
                name="NEXT_PUBLIC_STIMPACT_PROJECT_ID",
                example_value="billing-prod",
                description="Project identifier used for telemetry routing.",
            ),
            SdkEnvVarSpec(
                name="NEXT_PUBLIC_STIMPACT_API_KEY",
                example_value="stimp_live_replace_me",
                description="Project API key created during onboarding.",
            ),
            SdkEnvVarSpec(
                name="NEXT_PUBLIC_STIMPACT_SERVICE",
                example_value="web-app",
                description="Service name attached to captured incidents.",
            ),
            SdkEnvVarSpec(
                name="NEXT_PUBLIC_STIMPACT_ENVIRONMENT",
                example_value="production",
                description="Runtime environment tag.",
            ),
        ],
    ),
    "javascript-vite-react": SdkFrameworkSpec(
        id="javascript-vite-react",
        language="javascript",
        label="Vite React",
        package_name="@stimpact/sdk",
        install_command="npm install @stimpact/sdk",
        env_vars=[
            SdkEnvVarSpec(
                name="VITE_STIMPACT_BASE_URL",
                example_value="https://stimpact.example.com",
                description="Public Stimpact telemetry base URL.",
            ),
            SdkEnvVarSpec(
                name="VITE_STIMPACT_PROJECT_ID",
                example_value="billing-prod",
                description="Project identifier used for telemetry routing.",
            ),
            SdkEnvVarSpec(
                name="VITE_STIMPACT_API_KEY",
                example_value="stimp_live_replace_me",
                description="Project API key created during onboarding.",
            ),
            SdkEnvVarSpec(
                name="VITE_STIMPACT_SERVICE",
                example_value="web-app",
                description="Service name attached to captured incidents.",
            ),
            SdkEnvVarSpec(
                name="VITE_STIMPACT_ENVIRONMENT",
                example_value="production",
                description="Runtime environment tag.",
            ),
        ],
    ),
    "javascript-generic": SdkFrameworkSpec(
        id="javascript-generic",
        language="javascript",
        label="JavaScript application",
        package_name="@stimpact/sdk",
        install_command="npm install @stimpact/sdk",
        env_vars=[],
    ),
    "python-fastapi": SdkFrameworkSpec(
        id="python-fastapi",
        language="python",
        label="FastAPI",
        package_name="stimpact-sdk",
        install_command="pip install stimpact-sdk",
        env_vars=[
            SdkEnvVarSpec(
                name="STIMPACT_BASE_URL",
                example_value="https://stimpact.example.com",
                description="Public Stimpact telemetry base URL.",
            ),
            SdkEnvVarSpec(
                name="STIMPACT_PROJECT_ID",
                example_value="billing-prod",
                description="Project identifier used for telemetry routing.",
            ),
            SdkEnvVarSpec(
                name="STIMPACT_API_KEY",
                example_value="stimp_live_replace_me",
                description="Project API key created during onboarding.",
            ),
            SdkEnvVarSpec(
                name="STIMPACT_SERVICE",
                example_value="billing-api",
                description="Service name attached to captured incidents.",
            ),
            SdkEnvVarSpec(
                name="STIMPACT_ENVIRONMENT",
                example_value="production",
                description="Runtime environment tag.",
            ),
        ],
    ),
    "python-flask": SdkFrameworkSpec(
        id="python-flask",
        language="python",
        label="Flask",
        package_name="stimpact-sdk",
        install_command="pip install stimpact-sdk",
        env_vars=[
            SdkEnvVarSpec(
                name="STIMPACT_BASE_URL",
                example_value="https://stimpact.example.com",
                description="Public Stimpact telemetry base URL.",
            ),
            SdkEnvVarSpec(
                name="STIMPACT_PROJECT_ID",
                example_value="billing-prod",
                description="Project identifier used for telemetry routing.",
            ),
            SdkEnvVarSpec(
                name="STIMPACT_API_KEY",
                example_value="stimp_live_replace_me",
                description="Project API key created during onboarding.",
            ),
            SdkEnvVarSpec(
                name="STIMPACT_SERVICE",
                example_value="billing-api",
                description="Service name attached to captured incidents.",
            ),
            SdkEnvVarSpec(
                name="STIMPACT_ENVIRONMENT",
                example_value="production",
                description="Runtime environment tag.",
            ),
        ],
    ),
    "python-generic": SdkFrameworkSpec(
        id="python-generic",
        language="python",
        label="Python service",
        package_name="stimpact-sdk",
        install_command="pip install stimpact-sdk",
        env_vars=[
            SdkEnvVarSpec(
                name="STIMPACT_BASE_URL",
                example_value="https://stimpact.example.com",
                description="Public Stimpact telemetry base URL.",
            ),
            SdkEnvVarSpec(
                name="STIMPACT_PROJECT_ID",
                example_value="billing-prod",
                description="Project identifier used for telemetry routing.",
            ),
            SdkEnvVarSpec(
                name="STIMPACT_API_KEY",
                example_value="stimp_live_replace_me",
                description="Project API key created during onboarding.",
            ),
            SdkEnvVarSpec(
                name="STIMPACT_SERVICE",
                example_value="billing-api",
                description="Service name attached to captured incidents.",
            ),
            SdkEnvVarSpec(
                name="STIMPACT_ENVIRONMENT",
                example_value="production",
                description="Runtime environment tag.",
            ),
        ],
    ),
}


def get_framework_spec(framework_id: str) -> SdkFrameworkSpec:
    try:
        return _FRAMEWORK_SPECS[framework_id]
    except KeyError as exc:
        raise APIError(
            f"SDK framework {framework_id} is not supported.",
            status_code=400,
            code="sdk_bootstrap_framework_unsupported",
        ) from exc


def list_framework_specs() -> list[SdkFrameworkSpec]:
    return list(_FRAMEWORK_SPECS.values())
