from __future__ import annotations

from api.core.config import (
    get_aws_region,
    get_control_plane_namespace,
    get_control_plane_service_account,
    get_deployment_environment,
    get_eks_cluster_name,
    get_github_api_base_url,
    get_github_callback_url,
    get_github_installation_id,
    get_github_private_key,
    get_github_webhook_url,
    get_gitlab_application_id,
    get_gitlab_base_url,
    get_gitlab_callback_url,
    get_gitlab_oauth_scopes,
    get_kubernetes_namespace,
    get_openai_autonomous_model,
    get_openai_chat_model,
    get_openai_model,
    get_openai_patch_model,
    get_openai_rca_model,
    get_public_base_url,
    get_s3_artifact_bucket,
    get_sandbox_base_image,
    get_sandbox_execution_backend,
    get_sandbox_namespace,
    get_sandbox_service_account,
    get_sandbox_install_command,
    get_sandbox_reproduce_command,
    get_sandbox_timeout_seconds,
    get_sandbox_verify_command,
    get_secrets_manager_prefix,
)


def clear_model_env(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_CHAT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_RCA_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_PATCH_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_AUTONOMOUS_MODEL", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_SANDBOX_INSTALL_COMMAND", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_SANDBOX_REPRODUCE_COMMAND", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_SANDBOX_VERIFY_COMMAND", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_SANDBOX_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_S3_ARTIFACT_BUCKET", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_SECRETS_PREFIX", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_ENVIRONMENT", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_EKS_CLUSTER_NAME", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_CONTROL_PLANE_NAMESPACE", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_CONTROL_PLANE_SERVICE_ACCOUNT", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_SANDBOX_NAMESPACE", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_KUBERNETES_NAMESPACE", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_SANDBOX_SERVICE_ACCOUNT", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_SANDBOX_EXECUTION_BACKEND", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_SANDBOX_BASE_IMAGE", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("GITHUB_CALLBACK_URL", raising=False)
    monkeypatch.delenv("GITHUB_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("GITHUB_API_BASE_URL", raising=False)
    monkeypatch.delenv("GITHUB_INSTALLATION_ID", raising=False)
    monkeypatch.delenv("GITHUB_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("GITHUB_PRIVATE_KEY_PATH", raising=False)
    monkeypatch.delenv("GITHUB_PRIVATE_KEY_FILE", raising=False)
    monkeypatch.delenv("GITLAB_APPLICATION_ID", raising=False)
    monkeypatch.delenv("GITLAB_BASE_URL", raising=False)
    monkeypatch.delenv("GITLAB_CALLBACK_URL", raising=False)
    monkeypatch.delenv("GITLAB_OAUTH_SCOPES", raising=False)


def test_openai_model_defaults(monkeypatch) -> None:
    clear_model_env(monkeypatch)

    assert get_openai_model() == "gpt-4.1-mini"
    assert get_openai_chat_model() == "gpt-4.1-mini"
    assert get_openai_rca_model() == "gpt-4.1-mini"
    assert get_openai_patch_model() == "gpt-4.1-mini"
    assert get_openai_autonomous_model() == "gpt-4.1-mini"


def test_chat_model_prefers_dedicated_override(monkeypatch) -> None:
    clear_model_env(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", "shared-model")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "chat-model")

    assert get_openai_chat_model() == "chat-model"
    assert get_openai_rca_model() == "shared-model"


def test_rca_model_prefers_dedicated_override(monkeypatch) -> None:
    clear_model_env(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", "shared-model")
    monkeypatch.setenv("OPENAI_RCA_MODEL", "rca-model")

    assert get_openai_rca_model() == "rca-model"
    assert get_openai_chat_model() == "shared-model"


def test_patch_model_falls_back_to_rca_then_shared(monkeypatch) -> None:
    clear_model_env(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", "shared-model")
    monkeypatch.setenv("OPENAI_RCA_MODEL", "rca-model")

    assert get_openai_patch_model() == "rca-model"

    monkeypatch.setenv("OPENAI_PATCH_MODEL", "patch-model")
    assert get_openai_patch_model() == "patch-model"


def test_autonomous_model_falls_back_to_patch_then_rca_then_shared(monkeypatch) -> None:
    clear_model_env(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", "shared-model")
    monkeypatch.setenv("OPENAI_RCA_MODEL", "rca-model")
    monkeypatch.setenv("OPENAI_PATCH_MODEL", "patch-model")

    assert get_openai_autonomous_model() == "patch-model"

    monkeypatch.setenv("OPENAI_AUTONOMOUS_MODEL", "autonomous-model")
    assert get_openai_autonomous_model() == "autonomous-model"


def test_sandbox_command_defaults(monkeypatch) -> None:
    clear_model_env(monkeypatch)

    assert get_sandbox_install_command() is None
    assert get_sandbox_reproduce_command() is None
    assert get_sandbox_verify_command() is None
    assert get_sandbox_timeout_seconds() == 300


def test_sandbox_command_overrides(monkeypatch) -> None:
    clear_model_env(monkeypatch)
    monkeypatch.setenv("AGENT_PLATFORM_SANDBOX_INSTALL_COMMAND", "npm install")
    monkeypatch.setenv("AGENT_PLATFORM_SANDBOX_REPRODUCE_COMMAND", "python reproduce.py")
    monkeypatch.setenv("AGENT_PLATFORM_SANDBOX_VERIFY_COMMAND", "pytest")
    monkeypatch.setenv("AGENT_PLATFORM_SANDBOX_TIMEOUT_SECONDS", "45")

    assert get_sandbox_install_command() == "npm install"
    assert get_sandbox_reproduce_command() == "python reproduce.py"
    assert get_sandbox_verify_command() == "pytest"
    assert get_sandbox_timeout_seconds() == 45


def test_aws_and_kubernetes_config_defaults(monkeypatch) -> None:
    clear_model_env(monkeypatch)

    assert get_aws_region() is None
    assert get_s3_artifact_bucket() is None
    assert get_secrets_manager_prefix() == "stimpactai"
    assert get_deployment_environment() == "dev"
    assert get_eks_cluster_name() == "stimpactai-cluster"
    assert get_control_plane_namespace() == "control-plane"
    assert get_control_plane_service_account() == "stimpact-control-plane"
    assert get_sandbox_namespace() == "sandbox"
    assert get_kubernetes_namespace() == "sandbox"
    assert get_sandbox_service_account() == "stimpact-sandbox-job"
    assert get_sandbox_execution_backend() == "local"
    assert get_sandbox_base_image().startswith("public.ecr.aws/")
    assert get_public_base_url() is None
    assert get_github_api_base_url() == "https://api.github.com"
    assert get_github_callback_url() is None
    assert get_github_webhook_url() is None
    assert get_github_installation_id() is None
    assert get_gitlab_application_id() is None
    assert get_gitlab_base_url() == "https://gitlab.com"
    assert get_gitlab_callback_url() is None
    assert get_gitlab_oauth_scopes() == ["api", "read_repository", "write_repository"]


def test_aws_and_kubernetes_config_overrides(monkeypatch) -> None:
    clear_model_env(monkeypatch)
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AGENT_PLATFORM_S3_ARTIFACT_BUCKET", "stimpact-artifacts")
    monkeypatch.setenv("AGENT_PLATFORM_SECRETS_PREFIX", "prod/stimpact")
    monkeypatch.setenv("AGENT_PLATFORM_ENVIRONMENT", "production")
    monkeypatch.setenv("AGENT_PLATFORM_EKS_CLUSTER_NAME", "stimpactai-prod")
    monkeypatch.setenv("AGENT_PLATFORM_CONTROL_PLANE_NAMESPACE", "cp")
    monkeypatch.setenv("AGENT_PLATFORM_CONTROL_PLANE_SERVICE_ACCOUNT", "cp-sa")
    monkeypatch.setenv("AGENT_PLATFORM_SANDBOX_NAMESPACE", "sandbox-jobs")
    monkeypatch.setenv("AGENT_PLATFORM_SANDBOX_SERVICE_ACCOUNT", "sandbox-sa")
    monkeypatch.setenv("AGENT_PLATFORM_SANDBOX_EXECUTION_BACKEND", "kubernetes")
    monkeypatch.setenv("AGENT_PLATFORM_SANDBOX_BASE_IMAGE", "public.ecr.aws/acme/sandbox:latest")
    monkeypatch.setenv("AGENT_PLATFORM_PUBLIC_BASE_URL", "https://example.ngrok.dev")
    monkeypatch.setenv("GITHUB_INSTALLATION_ID", "123")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "/tmp/github-key.pem")
    monkeypatch.setenv("GITLAB_APPLICATION_ID", "gitlab-app")
    monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.example.com")
    monkeypatch.setenv("GITLAB_OAUTH_SCOPES", "api,read_repository,write_repository")

    assert get_aws_region() == "us-east-1"
    assert get_s3_artifact_bucket() == "stimpact-artifacts"
    assert get_secrets_manager_prefix() == "prod/stimpact"
    assert get_deployment_environment() == "production"
    assert get_eks_cluster_name() == "stimpactai-prod"
    assert get_control_plane_namespace() == "cp"
    assert get_control_plane_service_account() == "cp-sa"
    assert get_sandbox_namespace() == "sandbox-jobs"
    assert get_kubernetes_namespace() == "sandbox-jobs"
    assert get_sandbox_service_account() == "sandbox-sa"
    assert get_sandbox_execution_backend() == "kubernetes"
    assert get_sandbox_base_image() == "public.ecr.aws/acme/sandbox:latest"
    assert get_public_base_url() == "https://example.ngrok.dev"
    assert get_github_callback_url() == "https://example.ngrok.dev/api/github/callback"
    assert get_github_webhook_url() == "https://example.ngrok.dev/webhooks/github"
    assert get_github_installation_id() == "123"
    assert get_gitlab_application_id() == "gitlab-app"
    assert get_gitlab_base_url() == "https://gitlab.example.com"
    assert get_gitlab_callback_url() == "https://example.ngrok.dev/auth/gitlab/callback"
    assert get_gitlab_oauth_scopes() == ["api", "read_repository", "write_repository"]
