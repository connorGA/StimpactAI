from __future__ import annotations

from dataclasses import dataclass

from api.core.config import (
    get_sandbox_base_image,
    get_sandbox_namespace,
    get_sandbox_service_account,
)
from api.core.errors import APIError
from models.control_plane import RepoProfileRecord
from services.repository_provider import RepositorySnapshot


@dataclass(slots=True)
class KubernetesSandboxSubmission:
    external_job_id: str
    manifest: dict[str, object]


class KubernetesJobLauncher:
    def __init__(
        self,
        *,
        namespace: str | None = None,
        base_image: str | None = None,
        service_account_name: str | None = None,
    ) -> None:
        self._namespace = namespace or get_sandbox_namespace()
        self._base_image = base_image or get_sandbox_base_image()
        self._service_account_name = service_account_name or get_sandbox_service_account()

    def build_job_manifest(
        self,
        *,
        incident_id: str,
        sandbox_run_id: str,
        snapshot: RepositorySnapshot,
        repo_profile: RepoProfileRecord,
        patch_diff_s3_uri: str | None,
        network_allowlist: list[str],
        secret_env_refs: list[str],
        provider_access_secret_arn: str | None,
        provider_access_secret_format: str | None,
    ) -> dict[str, object]:
        commands = [
            repo_profile.install_command or "echo 'no install command configured'",
            *repo_profile.startup_commands,
            repo_profile.reproduce_command,
            repo_profile.verify_command,
        ]
        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": f"stimpact-sandbox-{sandbox_run_id[:8]}",
                "namespace": self._namespace,
                "labels": {
                    "app": "stimpact-sandbox",
                    "incident-id": incident_id,
                    "sandbox-run-id": sandbox_run_id,
                    "provider": snapshot.provider.value,
                },
                "annotations": {
                    "stimpact/repo-owner": snapshot.owner,
                    "stimpact/repo-name": snapshot.repository_name,
                    "stimpact/default-branch": snapshot.default_branch,
                    "stimpact/target-commit-sha": snapshot.target_commit_sha or "",
                    "stimpact/network-allowlist": ",".join(network_allowlist),
                    "stimpact/patch-diff-s3-uri": patch_diff_s3_uri or "",
                    "stimpact/secret-env-refs": ",".join(secret_env_refs),
                    "stimpact/provider-access-secret-arn": provider_access_secret_arn or "",
                },
            },
            "spec": {
                "ttlSecondsAfterFinished": 3600,
                "backoffLimit": 0,
                "template": {
                    "metadata": {
                        "labels": {
                            "app": "stimpact-sandbox",
                            "sandbox-run-id": sandbox_run_id,
                        }
                    },
                    "spec": {
                        "restartPolicy": "Never",
                        "serviceAccountName": self._service_account_name,
                        "nodeSelector": {
                            "stimpact.ai/workload": "sandbox",
                        },
                        "tolerations": [
                            {
                                "key": "stimpact.ai/workload",
                                "operator": "Equal",
                                "value": "sandbox",
                                "effect": "NoSchedule",
                            }
                        ],
                        "containers": [
                            {
                                "name": "sandbox",
                                "image": repo_profile.base_image or self._base_image,
                                "command": ["/bin/sh", "-lc"],
                                "args": [" && ".join(command for command in commands if command)],
                                "env": [
                                    {"name": "STIMPACT_INCIDENT_ID", "value": incident_id},
                                    {"name": "STIMPACT_SANDBOX_RUN_ID", "value": sandbox_run_id},
                                    {"name": "STIMPACT_PROVIDER", "value": snapshot.provider.value},
                                    {"name": "STIMPACT_CLONE_URL", "value": snapshot.clone_url},
                                    {"name": "STIMPACT_DEFAULT_BRANCH", "value": snapshot.default_branch},
                                    {"name": "STIMPACT_TARGET_COMMIT_SHA", "value": snapshot.target_commit_sha or ""},
                                    {"name": "STIMPACT_PATCH_DIFF_S3_URI", "value": patch_diff_s3_uri or ""},
                                    {
                                        "name": "STIMPACT_PROVIDER_ACCESS_SECRET_ARN",
                                        "value": provider_access_secret_arn or "",
                                    },
                                    {
                                        "name": "STIMPACT_PROVIDER_ACCESS_SECRET_FORMAT",
                                        "value": provider_access_secret_format or "",
                                    },
                                ],
                                "resources": {
                                    "requests": {"cpu": "500m", "memory": "1Gi"},
                                    "limits": {"cpu": "2", "memory": "4Gi"},
                                },
                            }
                        ],
                    },
                },
            },
        }

    def submit_job(self, manifest: dict[str, object]) -> KubernetesSandboxSubmission:
        metadata = manifest.get("metadata")
        if not isinstance(metadata, dict):
            raise APIError("Invalid Kubernetes job manifest.", code="invalid_kubernetes_manifest")
        external_job_id = str(metadata.get("name") or "stimpact-sandbox-job")
        return KubernetesSandboxSubmission(
            external_job_id=external_job_id,
            manifest=manifest,
        )


class KubernetesSandboxRunner:
    def __init__(self, *, launcher: KubernetesJobLauncher | None = None) -> None:
        self._launcher = launcher or KubernetesJobLauncher()

    def submit(
        self,
        *,
        incident_id: str,
        sandbox_run_id: str,
        snapshot: RepositorySnapshot,
        repo_profile: RepoProfileRecord,
        patch_diff_s3_uri: str | None,
        network_allowlist: list[str],
        secret_env_refs: list[str],
        provider_access_secret_arn: str | None,
        provider_access_secret_format: str | None,
    ) -> KubernetesSandboxSubmission:
        manifest = self._launcher.build_job_manifest(
            incident_id=incident_id,
            sandbox_run_id=sandbox_run_id,
            snapshot=snapshot,
            repo_profile=repo_profile,
            patch_diff_s3_uri=patch_diff_s3_uri,
            network_allowlist=network_allowlist,
            secret_env_refs=secret_env_refs,
            provider_access_secret_arn=provider_access_secret_arn,
            provider_access_secret_format=provider_access_secret_format,
        )
        return self._launcher.submit_job(manifest)


class KubernetesJobMonitor:
    def poll_status(self, *, external_job_id: str) -> str:
        _ = external_job_id
        return "running"
