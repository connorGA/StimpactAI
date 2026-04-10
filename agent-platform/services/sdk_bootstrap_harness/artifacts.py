from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import asdict, is_dataclass

from api.core.errors import APIError
from services.sdk_bootstrap_harness.models import (
    SdkBootstrapHarnessTarget,
    SdkBootstrapPreviewArtifact,
    SdkBootstrapSafeChangePolicy,
)


def encode_preview_artifact(
    *,
    secret: str,
    strategy_id: str,
    target: SdkBootstrapHarnessTarget,
    safe_change_policy: SdkBootstrapSafeChangePolicy,
    patch_diff: str | None,
    branch_name: str,
    credential_kind: str,
    framework: str,
    summary: str,
    entrypoints: list[str],
    attempt: dict[str, object],
) -> SdkBootstrapPreviewArtifact:
    payload = {
        "strategy_id": strategy_id,
        "target": _serialize(target),
        "safe_change_policy": _serialize(safe_change_policy),
        "patch_diff": patch_diff,
        "branch_name": branch_name,
        "credential_kind": credential_kind,
        "framework": framework,
        "summary": summary,
        "entrypoints": list(entrypoints),
        "attempt": attempt,
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
    artifact_id = f"{token}.{signature}"
    checksum = hashlib.sha256((patch_diff or "").encode("utf-8")).hexdigest() if patch_diff is not None else None
    return SdkBootstrapPreviewArtifact(
        artifact_id=artifact_id,
        checksum=checksum,
        strategy_id=strategy_id,
        target=target,
        safe_change_policy=safe_change_policy,
    )


def decode_preview_artifact(*, secret: str, artifact_id: str) -> dict[str, object]:
    try:
        token, supplied_signature = artifact_id.split(".", 1)
    except ValueError as exc:
        raise _invalid_artifact_error() from exc
    padding = "=" * (-len(token) % 4)
    try:
        body = base64.urlsafe_b64decode(f"{token}{padding}".encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise _invalid_artifact_error() from exc
    expected_signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, supplied_signature):
        raise _invalid_artifact_error()
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise _invalid_artifact_error() from exc
    if not isinstance(payload, dict):
        raise _invalid_artifact_error()
    return payload


def _serialize(value):
    if is_dataclass(value):
        return asdict(value)
    return value


def _invalid_artifact_error() -> APIError:
    return APIError(
        "The reviewed SDK bootstrap artifact could not be validated. Generate a fresh preview and approve that exact patch bundle before creating a PR.",
        code="sdk_bootstrap_artifact_invalid",
        status_code=409,
    )
