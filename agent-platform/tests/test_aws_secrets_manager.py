from __future__ import annotations

from services.aws_secrets_manager import AwsSecretsManagerWriter


def test_build_secret_name_uses_project_environment_prefix() -> None:
    writer = AwsSecretsManagerWriter(region="us-west-2", prefix="stimpactai")
    writer._environment = "dev"

    assert (
        writer.build_secret_name(project_id="project-123", label="OPENAI_API_KEY")
        == "stimpactai/projects/project-123/env/dev/OPENAI_API_KEY"
    )


def test_build_secret_name_sanitizes_invalid_label_characters() -> None:
    writer = AwsSecretsManagerWriter(region="us-west-2", prefix="stimpactai")
    writer._environment = "prod"

    assert (
        writer.build_secret_name(project_id="project-123", label="OpenAI API Key")
        == "stimpactai/projects/project-123/env/prod/OpenAI_API_Key"
    )
