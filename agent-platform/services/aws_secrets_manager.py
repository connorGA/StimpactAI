from __future__ import annotations

import re
from typing import Protocol

from api.core.config import (
    get_aws_region,
    get_deployment_environment,
    get_secrets_manager_prefix,
)
from api.core.errors import APIError


class SecretsWriter(Protocol):
    def put_secret(self, *, project_id: str, label: str, value: str) -> str: ...


class SecretsReader(Protocol):
    def get_secret(self, *, external_ref: str) -> str: ...


class AwsSecretsManagerWriter:
    def __init__(self, *, region: str | None = None, prefix: str | None = None) -> None:
        self._region = region or get_aws_region()
        self._prefix = prefix or get_secrets_manager_prefix()
        self._environment = get_deployment_environment()

    @staticmethod
    def _normalize_secret_label(label: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9/_+=.@-]+", "_", label.strip())
        normalized = normalized.strip("/")
        return normalized or "unnamed-secret"

    def build_secret_name(self, *, project_id: str, label: str) -> str:
        normalized_label = self._normalize_secret_label(label)
        return (
            f"{self._prefix}/projects/{project_id}/env/"
            f"{self._environment}/{normalized_label}"
        )

    def put_secret(self, *, project_id: str, label: str, value: str) -> str:
        if self._region is None:
            raise APIError(
                "AWS region is not configured for Secrets Manager.",
                status_code=503,
                code="aws_unconfigured",
            )

        try:
            import boto3  # type: ignore
            from botocore.exceptions import ClientError  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on runtime environment
            raise APIError(
                "boto3 is not installed for AWS Secrets Manager integration.",
                status_code=503,
                code="aws_sdk_unavailable",
            ) from exc

        client = boto3.client("secretsmanager", region_name=self._region)
        secret_name = self.build_secret_name(project_id=project_id, label=label)
        try:
            create_result = client.create_secret(
                Name=secret_name,
                SecretString=value,
                Description=(
                    f"Stimpact secret for project {project_id} "
                    f"environment {self._environment} label {label}"
                ),
                Tags=[
                    {"Key": "managed-by", "Value": "stimpact"},
                    {"Key": "project-id", "Value": project_id},
                    {"Key": "environment", "Value": self._environment},
                    {"Key": "label", "Value": label},
                ],
            )
            return str(create_result["ARN"])
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code != "ResourceExistsException":
                raise APIError(
                    "Failed to write secret to AWS Secrets Manager.",
                    status_code=502,
                    code="secrets_manager_write_failed",
                ) from exc

        try:
            put_result = client.put_secret_value(
                SecretId=secret_name,
                SecretString=value,
            )
            return str(put_result["ARN"])
        except ClientError as exc:
            raise APIError(
                "Failed to update secret in AWS Secrets Manager.",
                status_code=502,
                code="secrets_manager_write_failed",
            ) from exc


class AwsSecretsManagerReader:
    def __init__(self, *, region: str | None = None) -> None:
        self._region = region or get_aws_region()

    def get_secret(self, *, external_ref: str) -> str:
        if self._region is None:
            raise APIError(
                "AWS region is not configured for Secrets Manager.",
                status_code=503,
                code="aws_unconfigured",
            )

        try:
            import boto3  # type: ignore
            from botocore.exceptions import ClientError  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on runtime environment
            raise APIError(
                "boto3 is not installed for AWS Secrets Manager integration.",
                status_code=503,
                code="aws_sdk_unavailable",
            ) from exc

        client = boto3.client("secretsmanager", region_name=self._region)
        try:
            result = client.get_secret_value(SecretId=external_ref)
        except ClientError as exc:
            raise APIError(
                "Failed to read secret from AWS Secrets Manager.",
                status_code=502,
                code="secrets_manager_read_failed",
            ) from exc

        value = result.get("SecretString")
        if not isinstance(value, str) or not value.strip():
            raise APIError(
                "Secret payload was empty or unavailable.",
                status_code=502,
                code="secrets_manager_read_failed",
            )
        return value
