from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urljoin, urlparse

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENV_PATH = REPO_ROOT / ".env"

load_dotenv(DEFAULT_ENV_PATH)


def get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_nonempty_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def get_database_url() -> str | None:
    return os.getenv("DATABASE_URL")


def get_openai_api_key() -> str | None:
    value = os.getenv("OPENAI_API_KEY")
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


def _get_model_from_env(*names: str, default: str) -> str:
    return get_nonempty_env(*names) or default


def get_openai_model() -> str:
    return _get_model_from_env("OPENAI_MODEL", default="gpt-4.1-mini")


def get_openai_chat_model() -> str:
    return _get_model_from_env(
        "OPENAI_CHAT_MODEL",
        "OPENAI_MODEL",
        default="gpt-4.1-mini",
    )


def get_openai_rca_model() -> str:
    return _get_model_from_env(
        "OPENAI_RCA_MODEL",
        "OPENAI_MODEL",
        default="gpt-4.1-mini",
    )


def get_openai_patch_model() -> str:
    return _get_model_from_env(
        "OPENAI_PATCH_MODEL",
        "OPENAI_RCA_MODEL",
        "OPENAI_MODEL",
        default="gpt-4.1-mini",
    )


def get_openai_autonomous_model() -> str:
    return _get_model_from_env(
        "OPENAI_AUTONOMOUS_MODEL",
        "OPENAI_PATCH_MODEL",
        "OPENAI_RCA_MODEL",
        "OPENAI_MODEL",
        default="gpt-4.1-mini",
    )


def get_repository_root() -> Path:
    value = os.getenv("AGENT_PLATFORM_REPOSITORY_ROOT")
    if value is None or not value.strip():
        return REPO_ROOT

    candidate = Path(value.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    return candidate


def get_sandbox_install_command() -> str | None:
    value = os.getenv("AGENT_PLATFORM_SANDBOX_INSTALL_COMMAND")
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def get_sandbox_reproduce_command() -> str | None:
    value = os.getenv("AGENT_PLATFORM_SANDBOX_REPRODUCE_COMMAND")
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def get_sandbox_verify_command() -> str | None:
    value = os.getenv("AGENT_PLATFORM_SANDBOX_VERIFY_COMMAND")
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def get_sandbox_timeout_seconds() -> int:
    value = os.getenv("AGENT_PLATFORM_SANDBOX_TIMEOUT_SECONDS", "300").strip()
    try:
        return max(10, int(value))
    except ValueError:
        return 300


def get_aws_region() -> str | None:
    return get_nonempty_env("AWS_REGION", "AWS_DEFAULT_REGION")


def get_public_base_url() -> str | None:
    return get_nonempty_env("AGENT_PLATFORM_PUBLIC_BASE_URL")


def get_frontend_base_url() -> str | None:
    explicit = get_nonempty_env("CLIENT_UI_BASE_URL", "FRONTEND_BASE_URL", "APP_BASE_URL")
    if explicit is not None:
        return explicit
    if is_local_development_environment():
        return "http://localhost:3000"
    return None


def get_s3_artifact_bucket() -> str | None:
    return get_nonempty_env("AGENT_PLATFORM_S3_ARTIFACT_BUCKET")


def get_secrets_manager_prefix() -> str:
    return get_nonempty_env("AGENT_PLATFORM_SECRETS_PREFIX") or "stimpactai"


def get_deployment_environment() -> str:
    return get_nonempty_env("AGENT_PLATFORM_ENVIRONMENT", "ENVIRONMENT") or "dev"


def is_local_development_environment() -> bool:
    return get_deployment_environment().strip().lower() in {"dev", "development", "local", "test"}


def get_admin_api_token() -> str | None:
    return get_nonempty_env("AGENT_PLATFORM_ADMIN_TOKEN")


def get_auth_session_secret() -> str:
    return get_nonempty_env("AGENT_PLATFORM_AUTH_SESSION_SECRET") or "stimpact-dev-session-secret"


def get_auth_session_ttl_seconds() -> int:
    value = os.getenv("AGENT_PLATFORM_AUTH_SESSION_TTL_SECONDS", "43200").strip()
    try:
        return max(300, int(value))
    except ValueError:
        return 43_200


def is_control_plane_auth_enforced() -> bool:
    explicit = os.getenv("AGENT_PLATFORM_REQUIRE_CONTROL_PLANE_AUTH")
    if explicit is not None:
        return explicit.strip().lower() in {"1", "true", "yes", "on"}
    return get_admin_api_token() is not None


def is_project_api_key_auth_enforced() -> bool:
    explicit = os.getenv("AGENT_PLATFORM_REQUIRE_PROJECT_API_KEYS")
    if explicit is not None:
        return explicit.strip().lower() in {"1", "true", "yes", "on"}
    return False


def should_run_migrations_on_startup() -> bool:
    explicit = os.getenv("AGENT_PLATFORM_RUN_MIGRATIONS")
    if explicit is not None:
        return explicit.strip().lower() in {"1", "true", "yes", "on"}
    return is_local_development_environment()


def should_require_database() -> bool:
    explicit = os.getenv("AGENT_PLATFORM_REQUIRE_DATABASE")
    if explicit is not None:
        return explicit.strip().lower() in {"1", "true", "yes", "on"}
    return not is_local_development_environment()


def should_require_redis() -> bool:
    explicit = os.getenv("AGENT_PLATFORM_REQUIRE_REDIS")
    if explicit is not None:
        return explicit.strip().lower() in {"1", "true", "yes", "on"}
    return not is_local_development_environment()


def should_fail_readiness_when_degraded() -> bool:
    explicit = os.getenv("AGENT_PLATFORM_STRICT_READINESS")
    if explicit is not None:
        return explicit.strip().lower() in {"1", "true", "yes", "on"}
    return not is_local_development_environment()


def validate_runtime_configuration(*, runtime: str) -> None:
    errors: list[str] = []
    if should_require_database() and get_database_url() is None:
        errors.append("DATABASE_URL is required for this runtime.")
    if should_require_redis() and get_redis_url() is None:
        errors.append("REDIS_URL is required for this runtime.")
    if not is_local_development_environment() and should_run_migrations_on_startup():
        errors.append(
            "AGENT_PLATFORM_RUN_MIGRATIONS must be disabled for long-running services; run migrations via an explicit job."
        )
    if runtime == "api" and is_control_plane_auth_enforced() and get_admin_api_token() is None:
        errors.append("AGENT_PLATFORM_ADMIN_TOKEN must be configured when control-plane auth is enabled.")
    if errors:
        raise ValueError("Invalid runtime configuration: " + " ".join(errors))


def get_control_plane_rate_limit_per_minute() -> int:
    value = os.getenv("AGENT_PLATFORM_CONTROL_PLANE_RATE_LIMIT_PER_MINUTE", "120").strip()
    try:
        return max(1, int(value))
    except ValueError:
        return 120


def get_telemetry_rate_limit_per_minute() -> int:
    value = os.getenv("AGENT_PLATFORM_TELEMETRY_RATE_LIMIT_PER_MINUTE", "600").strip()
    try:
        return max(1, int(value))
    except ValueError:
        return 600


def get_outbox_stale_lock_seconds() -> int:
    value = os.getenv("AGENT_PLATFORM_OUTBOX_STALE_LOCK_SECONDS", "300").strip()
    try:
        return max(30, int(value))
    except ValueError:
        return 300


def get_async_job_stale_lease_seconds() -> int:
    value = os.getenv("AGENT_PLATFORM_ASYNC_JOB_STALE_LEASE_SECONDS", "300").strip()
    try:
        return max(30, int(value))
    except ValueError:
        return 300


def get_eks_cluster_name() -> str:
    return get_nonempty_env("AGENT_PLATFORM_EKS_CLUSTER_NAME") or "stimpactai-cluster"


def get_control_plane_namespace() -> str:
    return get_nonempty_env("AGENT_PLATFORM_CONTROL_PLANE_NAMESPACE") or "control-plane"


def get_control_plane_service_account() -> str:
    return get_nonempty_env("AGENT_PLATFORM_CONTROL_PLANE_SERVICE_ACCOUNT") or "stimpact-control-plane"


def get_sandbox_namespace() -> str:
    return get_nonempty_env(
        "AGENT_PLATFORM_SANDBOX_NAMESPACE",
        "AGENT_PLATFORM_KUBERNETES_NAMESPACE",
    ) or "sandbox"


def get_sandbox_service_account() -> str:
    return get_nonempty_env("AGENT_PLATFORM_SANDBOX_SERVICE_ACCOUNT") or "stimpact-sandbox-job"


def get_kubernetes_namespace() -> str:
    return get_sandbox_namespace()


def get_sandbox_execution_backend() -> str:
    value = os.getenv("AGENT_PLATFORM_SANDBOX_EXECUTION_BACKEND", "local")
    normalized = value.strip().lower()
    return normalized or "local"


def get_sandbox_base_image() -> str:
    value = os.getenv("AGENT_PLATFORM_SANDBOX_BASE_IMAGE", "public.ecr.aws/docker/library/python:3.12")
    normalized = value.strip()
    return normalized or "public.ecr.aws/docker/library/python:3.12"


def get_kubeconfig_path() -> str | None:
    return get_nonempty_env("KUBECONFIG", "AGENT_PLATFORM_KUBECONFIG")


def get_kubeconfig_context() -> str | None:
    return get_nonempty_env("AGENT_PLATFORM_KUBECONFIG_CONTEXT")


def get_worker_idle_seconds() -> float:
    value = os.getenv("AGENT_PLATFORM_WORKER_IDLE_SECONDS", "2").strip()
    try:
        return max(0.1, float(value))
    except ValueError:
        return 2.0


def get_kubernetes_monitor_interval_seconds() -> float:
    value = os.getenv("AGENT_PLATFORM_KUBERNETES_MONITOR_INTERVAL_SECONDS", "5").strip()
    try:
        return max(0.5, float(value))
    except ValueError:
        return 5.0


def get_github_app_name() -> str | None:
    return get_nonempty_env("GITHUB_APP_NAME")


def get_github_app_id() -> str | None:
    return get_nonempty_env("GITHUB_APP_ID")


def get_github_client_id() -> str | None:
    return get_nonempty_env("GITHUB_CLIENT_ID")


def get_github_client_secret() -> str | None:
    return get_nonempty_env("GITHUB_CLIENT_SECRET")


def get_github_installation_id() -> str | None:
    return get_nonempty_env("GITHUB_INSTALLATION_ID")


def _read_text_file(path_value: str) -> str | None:
    candidate = Path(path_value.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    if not candidate.exists() or not candidate.is_file():
        return None
    contents = candidate.read_text(encoding="utf-8").strip()
    return contents or None


def _discover_github_private_key_file() -> str | None:
    matches = sorted(REPO_ROOT.glob("*.private-key.pem"))
    if len(matches) != 1:
        return None
    contents = matches[0].read_text(encoding="utf-8").strip()
    return contents or None


def get_github_private_key() -> str | None:
    inline_value = os.getenv("GITHUB_PRIVATE_KEY")
    if inline_value is not None:
        normalized = inline_value.strip()
        if "BEGIN" in normalized and "PRIVATE KEY" in normalized:
            return normalized
        path_contents = _read_text_file(normalized)
        if path_contents is not None:
            return path_contents

    path_value = get_nonempty_env("GITHUB_PRIVATE_KEY_PATH", "GITHUB_PRIVATE_KEY_FILE")
    if path_value is not None:
        path_contents = _read_text_file(path_value)
        if path_contents is not None:
            return path_contents

    return _discover_github_private_key_file()


def get_github_api_base_url() -> str:
    return get_nonempty_env("GITHUB_API_BASE_URL") or "https://api.github.com"


def get_github_callback_url() -> str | None:
    explicit = get_nonempty_env("GITHUB_CALLBACK_URL")
    if explicit is not None:
        return explicit
    base_url = get_public_base_url()
    if base_url is None:
        return None
    return urljoin(base_url.rstrip("/") + "/", "api/github/callback")


def get_github_webhook_url() -> str | None:
    explicit = get_nonempty_env("GITHUB_WEBHOOK_URL")
    if explicit is not None:
        return explicit
    base_url = get_public_base_url()
    if base_url is None:
        return None
    return urljoin(base_url.rstrip("/") + "/", "webhooks/github")


def get_github_webhook_secret() -> str | None:
    return get_nonempty_env("GITHUB_WEBHOOK_SECRET")


def get_gitlab_app_name() -> str | None:
    return get_nonempty_env("GITLAB_APP_NAME")


def get_gitlab_application_id() -> str | None:
    return get_nonempty_env("GITLAB_APPLICATION_ID")


def get_gitlab_app_secret() -> str | None:
    return get_nonempty_env("GITLAB_APP_SECRET")


def get_gitlab_base_url() -> str:
    return get_nonempty_env("GITLAB_BASE_URL") or "https://gitlab.com"


def get_gitlab_callback_url() -> str | None:
    explicit = get_nonempty_env("GITLAB_CALLBACK_URL")
    if explicit is not None:
        return explicit
    base_url = get_public_base_url()
    if base_url is None:
        return None
    return urljoin(base_url.rstrip("/") + "/", "auth/gitlab/callback")


def get_gitlab_oauth_scopes() -> list[str]:
    value = get_nonempty_env("GITLAB_OAUTH_SCOPES")
    if value is None:
        return ["api", "read_repository", "write_repository"]
    return [scope.strip() for scope in value.split(",") if scope.strip()]


def get_redis_url() -> str | None:
    value = os.getenv("REDIS_URL")
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    if "://" not in normalized:
        return f"redis://{normalized}"

    return normalized


def get_outbox_signal_stream() -> str:
    return os.getenv("AGENT_PLATFORM_OUTBOX_SIGNAL_STREAM", "agent-platform:outbox-signals")


def get_outbox_signal_block_ms() -> int:
    value = os.getenv("AGENT_PLATFORM_OUTBOX_SIGNAL_BLOCK_MS", "5000").strip()
    try:
        return max(1, int(value))
    except ValueError:
        return 5000


def get_outbox_signal_maxlen() -> int:
    value = os.getenv("AGENT_PLATFORM_OUTBOX_SIGNAL_MAXLEN", "10000").strip()
    try:
        return max(100, int(value))
    except ValueError:
        return 10000


def is_valid_database_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"postgres", "postgresql"} and bool(parsed.netloc)
