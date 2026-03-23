from __future__ import annotations

import asyncio
import json
from typing import Any
from pathlib import Path

import asyncpg

from api.core.config import (
    get_aws_region,
    get_database_url,
    get_openai_api_key,
    get_public_base_url,
    get_s3_artifact_bucket,
    get_sandbox_execution_backend,
    get_secrets_manager_prefix,
)


async def _collect_database_summary() -> dict[str, Any]:
    database_url = get_database_url()
    if not database_url:
        return {"configured": False}

    pool = await asyncpg.create_pool(dsn=database_url, min_size=1, max_size=1)
    try:
        counts = {}
        for table in (
            "provider_integrations",
            "provider_repositories",
            "repo_profiles",
            "repo_profile_secret_refs",
            "incidents",
            "async_jobs",
        ):
            counts[table] = await pool.fetchval(f"SELECT COUNT(*) FROM {table}")
        active_profiles = await pool.fetch(
            """
            SELECT id, project_id, provider_repository_id, reproduce_command, verify_command
            FROM repo_profiles
            WHERE active = TRUE
            ORDER BY updated_at DESC
            LIMIT 5
            """
        )
        integrations = await pool.fetch(
            """
            SELECT id, provider, name, metadata->>'project_id' AS project_id
            FROM provider_integrations
            ORDER BY updated_at DESC
            LIMIT 5
            """
        )
        return {
            "configured": True,
            "counts": counts,
            "active_repo_profiles": [dict(row) for row in active_profiles],
            "provider_integrations": [dict(row) for row in integrations],
        }
    finally:
        await pool.close()


def _collect_aws_summary() -> dict[str, Any]:
    try:
        import boto3  # type: ignore
    except ImportError:
        return {"configured": False, "error": "boto3 not installed"}

    summary: dict[str, Any] = {
        "configured": True,
        "region": get_aws_region(),
        "artifact_bucket": get_s3_artifact_bucket(),
        "secrets_prefix": get_secrets_manager_prefix(),
    }
    sts = boto3.client("sts", region_name=get_aws_region())
    summary["caller_identity"] = sts.get_caller_identity()
    bucket = get_s3_artifact_bucket()
    if bucket:
        s3 = boto3.client("s3", region_name=get_aws_region())
        summary["bucket_versioning"] = s3.get_bucket_versioning(Bucket=bucket)
    return summary


def _collect_kubernetes_summary() -> dict[str, Any]:
    try:
        from kubernetes import client, config  # type: ignore
        from kubernetes.config.config_exception import ConfigException  # type: ignore
    except ImportError:
        return {"configured": False, "error": "kubernetes package not installed"}

    try:
        config.load_incluster_config()
        config_mode = "in_cluster"
    except ConfigException:
        config.load_kube_config()
        config_mode = "kubeconfig"

    core_api = client.CoreV1Api()
    namespaces = [item.metadata.name for item in core_api.list_namespace().items]
    service_accounts = {
        "sandbox/stimpact-sandbox-job": core_api.read_namespaced_service_account(
            name="stimpact-sandbox-job",
            namespace="sandbox",
        ).metadata.name,
        "control-plane/stimpact-control-plane": core_api.read_namespaced_service_account(
            name="stimpact-control-plane",
            namespace="control-plane",
        ).metadata.name,
    }
    return {
        "configured": True,
        "config_mode": config_mode,
        "namespaces_present": {
            "sandbox": "sandbox" in namespaces,
            "control-plane": "control-plane" in namespaces,
        },
        "service_accounts": service_accounts,
    }


def _collect_manifest_summary() -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    manifest_paths = [
        "infra/kubernetes/apps/control-plane-config.yaml",
        "infra/kubernetes/apps/database-migration-job.yaml",
        "infra/kubernetes/apps/api-deployment.yaml",
        "infra/kubernetes/apps/frontend-deployment.yaml",
        "infra/kubernetes/apps/worker-deployments.yaml",
        "infra/kubernetes/apps/ingress.yaml",
    ]
    return {
        "required_manifests": {
            relative_path: (repo_root / relative_path).exists()
            for relative_path in manifest_paths
        }
    }


async def main() -> None:
    summary = {
        "env": {
            "database_url": bool(get_database_url()),
            "openai_api_key": bool(get_openai_api_key()),
            "aws_region": bool(get_aws_region()),
            "artifact_bucket": bool(get_s3_artifact_bucket()),
            "public_base_url": bool(get_public_base_url()),
            "sandbox_backend": get_sandbox_execution_backend(),
        },
        "aws": _collect_aws_summary(),
        "kubernetes": _collect_kubernetes_summary(),
        "manifests": _collect_manifest_summary(),
        "database": await _collect_database_summary(),
    }
    summary["ready_for_drill"] = bool(
        summary["env"]["database_url"]
        and summary["env"]["openai_api_key"]
        and summary["env"]["artifact_bucket"]
        and summary["env"]["sandbox_backend"] == "kubernetes"
        and summary["database"].get("configured")
        and summary["database"].get("counts", {}).get("provider_integrations", 0) > 0
        and summary["database"].get("counts", {}).get("repo_profiles", 0) > 0
        and all(summary["manifests"]["required_manifests"].values())
    )
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
