from __future__ import annotations

import hashlib
from typing import Protocol

from api.core.config import get_aws_region, get_s3_artifact_bucket
from api.core.errors import APIError


class ArtifactStorage(Protocol):
    def put_text(
        self,
        *,
        object_key: str,
        content: str,
        content_type: str,
    ) -> tuple[str, int, str | None]: ...

    def put_bytes(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
    ) -> tuple[str, int, str | None]: ...

    def generate_download_url(
        self,
        *,
        object_key: str,
        expires_in_seconds: int = 3600,
    ) -> str: ...


class S3ArtifactStorage:
    def __init__(self, *, bucket_name: str | None = None, region: str | None = None) -> None:
        self._bucket_name = bucket_name or get_s3_artifact_bucket()
        self._region = region or get_aws_region()

    @property
    def bucket_name(self) -> str:
        if self._bucket_name is None:
            raise APIError(
                "S3 artifact bucket is not configured.",
                status_code=503,
                code="artifact_storage_unconfigured",
            )
        return self._bucket_name

    def put_text(
        self,
        *,
        object_key: str,
        content: str,
        content_type: str,
    ) -> tuple[str, int, str | None]:
        return self.put_bytes(
            object_key=object_key,
            content=content.encode("utf-8"),
            content_type=content_type,
        )

    def put_bytes(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
    ) -> tuple[str, int, str | None]:
        checksum = hashlib.sha256(content).hexdigest()
        client = self._client()
        client.put_object(
            Bucket=self.bucket_name,
            Key=object_key,
            Body=content,
            ContentType=content_type,
        )
        uri = f"s3://{self.bucket_name}/{object_key}"
        return uri, len(content), checksum

    def generate_download_url(
        self,
        *,
        object_key: str,
        expires_in_seconds: int = 3600,
    ) -> str:
        client = self._client()
        return str(
            client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": object_key},
                ExpiresIn=expires_in_seconds,
            )
        )

    def _client(self):
        try:
            import boto3  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on runtime environment
            raise APIError(
                "boto3 is not installed for S3 artifact storage.",
                status_code=503,
                code="aws_sdk_unavailable",
            ) from exc
        return boto3.client("s3", region_name=self._region)
