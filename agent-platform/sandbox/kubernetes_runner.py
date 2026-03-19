from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import shlex
from typing import Any

from api.core.config import (
    get_kubeconfig_context,
    get_kubeconfig_path,
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


@dataclass(slots=True)
class KubernetesJobStatus:
    status: str
    summary: str
    execution_log: str = ""
    reproduction_succeeded: bool = False
    patch_applied: bool = False
    verification_succeeded: bool = False


class KubernetesClusterClient:
    def __init__(self, *, namespace: str | None = None) -> None:
        self._namespace = namespace or get_sandbox_namespace()
        self._batch_api = None
        self._core_api = None
        self._networking_api = None
        self._api_exception = None

    def apply_manifest(self, manifest: dict[str, object]) -> str:
        job_manifest = _extract_kind_from_list_manifest(manifest, "Job")
        if not isinstance(job_manifest, dict):
            raise APIError("Kubernetes manifest did not contain a Job resource.", code="invalid_kubernetes_manifest")
        network_policy_manifest = _extract_kind_from_list_manifest(manifest, "NetworkPolicy")
        if not isinstance(network_policy_manifest, dict):
            raise APIError(
                "Kubernetes manifest did not contain a NetworkPolicy resource.",
                code="invalid_kubernetes_manifest",
            )

        batch_api, _, networking_api = self._get_clients()
        job_name = _manifest_name(job_manifest)
        network_policy_name = _manifest_name(network_policy_manifest)

        try:
            job = batch_api.create_namespaced_job(namespace=self._namespace, body=job_manifest)
        except self._api_exception as exc:  # type: ignore[misc]
            if getattr(exc, "status", None) != 409:
                raise APIError(
                    f"Failed to submit Kubernetes Job {job_name}.",
                    status_code=502,
                    code="kubernetes_submit_failed",
                ) from exc
            job = batch_api.read_namespaced_job(name=job_name, namespace=self._namespace)

        try:
            networking_api.create_namespaced_network_policy(namespace=self._namespace, body=network_policy_manifest)
        except self._api_exception as exc:  # type: ignore[misc]
            if getattr(exc, "status", None) != 409:
                raise APIError(
                    f"Failed to submit Kubernetes NetworkPolicy {network_policy_name}.",
                    status_code=502,
                    code="kubernetes_submit_failed",
                ) from exc
            networking_api.patch_namespaced_network_policy(
                name=network_policy_name,
                namespace=self._namespace,
                body=network_policy_manifest,
            )

        metadata = getattr(job, "metadata", None)
        uid = getattr(metadata, "uid", None)
        return _encode_external_job_id(job_name=job_name, uid=str(uid) if uid else None)

    def poll_job(self, *, external_job_id: str) -> KubernetesJobStatus:
        job_name, _uid = _parse_external_job_id(external_job_id)
        batch_api, core_api, _networking_api = self._get_clients()

        try:
            job = batch_api.read_namespaced_job(name=job_name, namespace=self._namespace)
        except self._api_exception as exc:  # type: ignore[misc]
            if getattr(exc, "status", None) == 404:
                return KubernetesJobStatus(
                    status="failed",
                    summary=f"Kubernetes job {job_name} was not found.",
                    execution_log="",
                )
            raise APIError(
                f"Failed to poll Kubernetes Job {job_name}.",
                status_code=502,
                code="kubernetes_poll_failed",
            ) from exc

        status = getattr(job, "status", None)
        succeeded = int(getattr(status, "succeeded", 0) or 0)
        failed = int(getattr(status, "failed", 0) or 0)
        active = int(getattr(status, "active", 0) or 0)
        conditions = list(getattr(status, "conditions", []) or [])

        pods = core_api.list_namespaced_pod(namespace=self._namespace, label_selector=f"job-name={job_name}")
        pod_items = list(getattr(pods, "items", []) or [])
        pod = _select_latest_pod(pod_items)
        execution_log = self._read_pod_log(core_api, pod)
        phase_results = _extract_phase_results(execution_log)
        default_success = succeeded > 0 or any(getattr(condition, "type", None) == "Complete" for condition in conditions)

        if default_success:
            return KubernetesJobStatus(
                status="succeeded",
                summary=f"Kubernetes job {job_name} completed successfully.",
                execution_log=execution_log,
                reproduction_succeeded=phase_results.get("reproduce", True),
                patch_applied=phase_results.get("patch-apply", True),
                verification_succeeded=phase_results.get("verify", True),
            )
        if failed > 0 or any(getattr(condition, "type", None) == "Failed" for condition in conditions):
            return KubernetesJobStatus(
                status="failed",
                summary=_build_failure_summary(job_name=job_name, pod=pod),
                execution_log=execution_log,
                reproduction_succeeded=phase_results.get("reproduce", False),
                patch_applied=phase_results.get("patch-apply", False),
                verification_succeeded=phase_results.get("verify", False),
            )
        if active > 0 or pod is not None:
            return KubernetesJobStatus(
                status="running",
                summary=f"Kubernetes job {job_name} is still running.",
                execution_log=execution_log,
                reproduction_succeeded=phase_results.get("reproduce", False),
                patch_applied=phase_results.get("patch-apply", False),
                verification_succeeded=phase_results.get("verify", False),
            )
        return KubernetesJobStatus(
            status="running",
            summary=f"Kubernetes job {job_name} is pending scheduling.",
            execution_log=execution_log,
            reproduction_succeeded=phase_results.get("reproduce", False),
            patch_applied=phase_results.get("patch-apply", False),
            verification_succeeded=phase_results.get("verify", False),
        )

    def _read_pod_log(self, core_api, pod) -> str:
        if pod is None:
            return ""
        metadata = getattr(pod, "metadata", None)
        pod_name = getattr(metadata, "name", None)
        if not pod_name:
            return ""
        try:
            result = core_api.read_namespaced_pod_log(
                name=pod_name,
                namespace=self._namespace,
                timestamps=True,
            )
        except self._api_exception:  # type: ignore[misc]
            return ""
        return str(result or "")

    def _get_clients(self):
        if self._batch_api is not None and self._core_api is not None and self._networking_api is not None:
            return self._batch_api, self._core_api, self._networking_api

        try:
            from kubernetes import client, config  # type: ignore
            from kubernetes.client import ApiException  # type: ignore
            from kubernetes.config.config_exception import ConfigException  # type: ignore
        except ImportError as exc:
            raise APIError(
                "The kubernetes Python package is not installed.",
                status_code=503,
                code="kubernetes_sdk_unavailable",
            ) from exc

        try:
            config.load_incluster_config()
        except ConfigException:
            try:
                config.load_kube_config(
                    config_file=get_kubeconfig_path(),
                    context=get_kubeconfig_context(),
                )
            except Exception as exc:  # noqa: BLE001
                raise APIError(
                    "No Kubernetes cluster configuration was available.",
                    status_code=503,
                    code="kubernetes_unconfigured",
                ) from exc

        api_client = client.ApiClient()
        self._batch_api = client.BatchV1Api(api_client)
        self._core_api = client.CoreV1Api(api_client)
        self._networking_api = client.NetworkingV1Api(api_client)
        self._api_exception = ApiException
        return self._batch_api, self._core_api, self._networking_api


class KubernetesJobLauncher:
    def __init__(
        self,
        *,
        namespace: str | None = None,
        base_image: str | None = None,
        service_account_name: str | None = None,
        cluster_client: KubernetesClusterClient | None = None,
    ) -> None:
        self._namespace = namespace or get_sandbox_namespace()
        self._base_image = base_image or get_sandbox_base_image()
        self._service_account_name = service_account_name or get_sandbox_service_account()
        self._cluster_client = cluster_client or KubernetesClusterClient(namespace=self._namespace)

    def build_job_manifest(
        self,
        *,
        incident_id: str,
        sandbox_run_id: str,
        snapshot: RepositorySnapshot,
        repo_profile: RepoProfileRecord,
        patch_diff_s3_uri: str | None,
        patch_diff_content: str | None,
        network_allowlist: list[str],
        network_allowlist_cidrs: list[str],
        secret_env_refs: list[str],
        secret_env: dict[str, str] | None,
        secret_files: dict[str, str] | None,
        authenticated_clone_url: str | None,
        repository_archive_url: str | None,
        provider_access_secret_arn: str | None,
        provider_access_secret_format: str | None,
    ) -> dict[str, object]:
        container_commands = ["set -euo pipefail", "cd /workspace/repo"]
        volume_mounts = [
            {"name": "workspace", "mountPath": "/workspace"},
            {"name": "tmp", "mountPath": "/tmp"},
            {"name": "home", "mountPath": "/home/stimpact"},
        ]
        volumes = [
            {"name": "workspace", "emptyDir": {}},
            {"name": "tmp", "emptyDir": {}},
            {"name": "home", "emptyDir": {}},
        ]
        secret_file_entries = sorted((secret_files or {}).items())
        secret_file_env: list[dict[str, str]] = []
        container_setup_commands = ["set -euo pipefail"]
        mounted_parents: dict[str, str] = {}
        for index, (mount_as, value) in enumerate(secret_file_entries):
            target = PurePosixPath(mount_as)
            if not target.is_absolute():
                target = PurePosixPath("/workspace/repo") / target
            parent = str(target.parent)
            volume_name = mounted_parents.get(parent)
            if volume_name is None:
                volume_name = f"secret-file-{len(mounted_parents)}"
                mounted_parents[parent] = volume_name
                volumes.append({"name": volume_name, "emptyDir": {}})
                volume_mounts.append({"name": volume_name, "mountPath": parent})
            env_name = f"STIMPACT_SECRET_FILE_{index}"
            secret_file_env.append({"name": env_name, "value": value})
            container_setup_commands.append(f"mkdir -p {shlex.quote(parent)}")
            container_setup_commands.append(
                f"printf '%s' \"${env_name}\" > {shlex.quote(str(target))} && chmod 600 {shlex.quote(str(target))}"
            )
        container_commands.extend(container_setup_commands[1:])
        if repo_profile.install_command:
            container_commands.append(_phase_command("install", repo_profile.install_command))
        container_commands.append(_phase_command("reproduce", repo_profile.reproduce_command))
        container_commands.append(_phase_command("patch-apply", "git apply /workspace/.stimpact/patch.diff"))
        container_commands.append(_phase_command("verify", repo_profile.verify_command))
        init_containers = [
            {
                "name": "clone-and-apply",
                "image": "docker.io/alpine/git:latest",
                "workingDir": "/workspace",
                "command": ["/bin/sh", "-lc"],
                "args": [
                    "\n".join(
                        [
                            "set -euo pipefail",
                            "mkdir -p /workspace/.stimpact",
                            "printf '%s\\n' \"$STIMPACT_PATCH_DIFF_CONTENT\" > /workspace/.stimpact/patch.diff",
                            "rm -rf /workspace/repo",
                            (
                                "if [ -n \"$STIMPACT_REPOSITORY_ARCHIVE_URL\" ]; then "
                                "wget -q -O /workspace/.stimpact/repo.tar.gz \"$STIMPACT_REPOSITORY_ARCHIVE_URL\" && "
                                "mkdir -p /workspace/repo && "
                                "tar -xzf /workspace/.stimpact/repo.tar.gz -C /workspace/repo && "
                                "git init --quiet /workspace/repo; "
                                "else "
                                "git clone --quiet "
                                "--branch \"$STIMPACT_DEFAULT_BRANCH\" "
                                "\"$STIMPACT_AUTHENTICATED_CLONE_URL\" /workspace/repo && "
                                "cd /workspace/repo && "
                                "if [ -n \"$STIMPACT_TARGET_COMMIT_SHA\" ]; then git checkout --quiet \"$STIMPACT_TARGET_COMMIT_SHA\"; fi; "
                                "fi"
                            ),
                        ]
                    )
                ],
                "env": [
                    {
                        "name": "STIMPACT_AUTHENTICATED_CLONE_URL",
                        "value": authenticated_clone_url or snapshot.clone_url,
                    },
                    {
                        "name": "STIMPACT_PATCH_DIFF_CONTENT",
                        "value": patch_diff_content or "",
                    },
                    {
                        "name": "STIMPACT_REPOSITORY_ARCHIVE_URL",
                        "value": repository_archive_url or "",
                    },
                    {"name": "STIMPACT_DEFAULT_BRANCH", "value": snapshot.default_branch},
                    {"name": "STIMPACT_TARGET_COMMIT_SHA", "value": snapshot.target_commit_sha or ""},
                ],
                "volumeMounts": [{"name": "workspace", "mountPath": "/workspace"}],
                "securityContext": {
                    "allowPrivilegeEscalation": False,
                    "capabilities": {"drop": ["ALL"]},
                    "readOnlyRootFilesystem": True,
                },
            }
        ]
        job_manifest = {
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
                    "stimpact/network-policy-mode": "default-deny-allowlist",
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
                        "automountServiceAccountToken": False,
                        "enableServiceLinks": False,
                        "securityContext": {
                            "runAsNonRoot": True,
                            "runAsUser": 10001,
                            "runAsGroup": 10001,
                            "fsGroup": 10001,
                            "seccompProfile": {"type": "RuntimeDefault"},
                        },
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
                        "volumes": volumes,
                        "initContainers": init_containers,
                        "containers": [
                            {
                                "name": "sandbox",
                                "image": repo_profile.base_image or self._base_image,
                                "workingDir": "/workspace/repo",
                                "command": ["/bin/sh", "-lc"],
                                "args": ["\n".join(container_commands)],
                                "env": [
                                    {"name": "STIMPACT_INCIDENT_ID", "value": incident_id},
                                    {"name": "STIMPACT_SANDBOX_RUN_ID", "value": sandbox_run_id},
                                    {"name": "HOME", "value": "/home/stimpact"},
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
                                    *[
                                        {"name": name, "value": value}
                                        for name, value in sorted((secret_env or {}).items())
                                    ],
                                    *secret_file_env,
                                ],
                                "resources": {
                                    "requests": {"cpu": "500m", "memory": "1Gi"},
                                    "limits": {"cpu": "2", "memory": "4Gi"},
                                },
                                "volumeMounts": volume_mounts,
                                "securityContext": {
                                    "allowPrivilegeEscalation": False,
                                    "capabilities": {"drop": ["ALL"]},
                                    "readOnlyRootFilesystem": True,
                                },
                            }
                        ],
                    },
                },
            },
        }
        network_policy = self._build_network_policy(
            sandbox_run_id=sandbox_run_id,
            network_allowlist=network_allowlist,
            network_allowlist_cidrs=network_allowlist_cidrs,
        )
        return {
            "apiVersion": "v1",
            "kind": "List",
            "items": [job_manifest, network_policy],
        }

    def _build_network_policy(
        self,
        *,
        sandbox_run_id: str,
        network_allowlist: list[str],
        network_allowlist_cidrs: list[str],
    ) -> dict[str, object]:
        egress_rules: list[dict[str, object]] = [
            {
                "to": [
                    {
                        "namespaceSelector": {
                            "matchLabels": {"kubernetes.io/metadata.name": "kube-system"},
                        }
                    }
                ],
                "ports": [
                    {"protocol": "UDP", "port": 53},
                    {"protocol": "TCP", "port": 53},
                ],
            }
        ]
        if network_allowlist_cidrs:
            egress_rules.append(
                {
                    "to": [
                        {"ipBlock": {"cidr": cidr}}
                        for cidr in sorted(set(network_allowlist_cidrs))
                    ]
                }
            )
        return {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {
                "name": f"stimpact-sandbox-egress-{sandbox_run_id[:8]}",
                "namespace": self._namespace,
                "annotations": {
                    "stimpact/network-allowlist": ",".join(network_allowlist),
                },
            },
            "spec": {
                "podSelector": {
                    "matchLabels": {
                        "sandbox-run-id": sandbox_run_id,
                    }
                },
                "policyTypes": ["Egress"],
                "egress": egress_rules,
            },
        }

    def submit_job(self, manifest: dict[str, object]) -> KubernetesSandboxSubmission:
        external_job_id = self._cluster_client.apply_manifest(manifest)
        return KubernetesSandboxSubmission(
            external_job_id=external_job_id,
            manifest=manifest,
        )


class KubernetesSandboxRunner:
    def __init__(
        self,
        *,
        launcher: KubernetesJobLauncher | None = None,
        cluster_client: KubernetesClusterClient | None = None,
    ) -> None:
        self._launcher = launcher or KubernetesJobLauncher(cluster_client=cluster_client)

    def submit(
        self,
        *,
        incident_id: str,
        sandbox_run_id: str,
        snapshot: RepositorySnapshot,
        repo_profile: RepoProfileRecord,
        patch_diff_s3_uri: str | None,
        patch_diff_content: str | None,
        network_allowlist: list[str],
        network_allowlist_cidrs: list[str],
        secret_env_refs: list[str],
        secret_env: dict[str, str] | None,
        secret_files: dict[str, str] | None,
        authenticated_clone_url: str | None,
        repository_archive_url: str | None,
        provider_access_secret_arn: str | None,
        provider_access_secret_format: str | None,
    ) -> KubernetesSandboxSubmission:
        manifest = self._launcher.build_job_manifest(
            incident_id=incident_id,
            sandbox_run_id=sandbox_run_id,
            snapshot=snapshot,
            repo_profile=repo_profile,
            patch_diff_s3_uri=patch_diff_s3_uri,
            patch_diff_content=patch_diff_content,
            network_allowlist=network_allowlist,
            network_allowlist_cidrs=network_allowlist_cidrs,
            secret_env_refs=secret_env_refs,
            secret_env=secret_env,
            secret_files=secret_files,
            authenticated_clone_url=authenticated_clone_url,
            repository_archive_url=repository_archive_url,
            provider_access_secret_arn=provider_access_secret_arn,
            provider_access_secret_format=provider_access_secret_format,
        )
        return self._launcher.submit_job(manifest)


class KubernetesJobMonitor:
    def __init__(self, *, cluster_client: KubernetesClusterClient | None = None) -> None:
        self._cluster_client = cluster_client or KubernetesClusterClient()

    def poll_status(self, *, external_job_id: str) -> KubernetesJobStatus:
        return self._cluster_client.poll_job(external_job_id=external_job_id)


def _extract_kind_from_list_manifest(manifest: dict[str, object], kind: str) -> dict[str, object] | None:
    if manifest.get("kind") == kind:
        return manifest
    items = manifest.get("items")
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and item.get("kind") == kind:
            return item
    return None


def _manifest_name(resource: dict[str, object]) -> str:
    metadata = resource.get("metadata")
    if not isinstance(metadata, dict):
        raise APIError("Kubernetes resource metadata is invalid.", code="invalid_kubernetes_manifest")
    name = metadata.get("name")
    if not isinstance(name, str) or not name.strip():
        raise APIError("Kubernetes resource metadata.name is required.", code="invalid_kubernetes_manifest")
    return name.strip()


def _encode_external_job_id(*, job_name: str, uid: str | None) -> str:
    return f"{job_name}:{uid}" if uid else job_name


def _parse_external_job_id(external_job_id: str) -> tuple[str, str | None]:
    if ":" not in external_job_id:
        return external_job_id, None
    job_name, uid = external_job_id.split(":", 1)
    return job_name, uid or None


def _phase_command(phase: str, command: str) -> str:
    escaped_phase = shlex.quote(phase)
    if phase == "reproduce":
        return (
            f"printf 'STIMPACT_PHASE_START phase=%s\\n' {escaped_phase}; "
            f"if {command}; then "
            f"printf 'STIMPACT_PHASE_RESULT phase=%s status=passed\\n' {escaped_phase}; "
            "else code=$?; "
            "if [ \"$code\" -eq 124 ] || [ \"$code\" -eq 126 ] || [ \"$code\" -eq 127 ]; then "
            f"printf 'STIMPACT_PHASE_RESULT phase=%s status=failed exit_code=%s\\n' {escaped_phase} \"$code\"; "
            "exit \"$code\"; "
            "fi; "
            f"printf 'STIMPACT_PHASE_RESULT phase=%s status=observed exit_code=%s\\n' {escaped_phase} \"$code\"; "
            "fi"
        )
    return (
        f"printf 'STIMPACT_PHASE_START phase=%s\\n' {escaped_phase}; "
        f"if {command}; then "
        f"printf 'STIMPACT_PHASE_RESULT phase=%s status=passed\\n' {escaped_phase}; "
        "else code=$?; "
        f"printf 'STIMPACT_PHASE_RESULT phase=%s status=failed exit_code=%s\\n' {escaped_phase} \"$code\"; "
        "exit \"$code\"; "
        "fi"
    )


def _extract_phase_results(execution_log: str) -> dict[str, bool]:
    phase_results: dict[str, bool] = {}
    for raw_line in execution_log.splitlines():
        line = raw_line.strip()
        if not line.startswith("STIMPACT_PHASE_RESULT "):
            continue
        fields = dict(
            part.split("=", 1)
            for part in line.removeprefix("STIMPACT_PHASE_RESULT ").split()
            if "=" in part
        )
        phase = fields.get("phase")
        status = fields.get("status")
        if phase:
            phase_results[phase] = status in {"passed", "observed"} if phase == "reproduce" else status == "passed"
    return phase_results


def _select_latest_pod(pods: list[object]):
    if not pods:
        return None

    def _sort_key(pod: object):
        metadata = getattr(pod, "metadata", None)
        return (
            getattr(metadata, "creation_timestamp", None),
            getattr(metadata, "name", ""),
        )

    return sorted(pods, key=_sort_key, reverse=True)[0]


def _build_failure_summary(*, job_name: str, pod) -> str:
    if pod is None:
        return f"Kubernetes job {job_name} failed."
    status = getattr(pod, "status", None)
    container_statuses = list(getattr(status, "container_statuses", []) or [])
    for container_status in container_statuses:
        state = getattr(container_status, "state", None)
        terminated = getattr(state, "terminated", None)
        if terminated is None:
            continue
        reason = getattr(terminated, "reason", None) or "terminated"
        message = getattr(terminated, "message", None)
        if isinstance(message, str) and message.strip():
            return f"Kubernetes job {job_name} failed: {reason} - {message.strip()}"
        return f"Kubernetes job {job_name} failed: {reason}."
    phase = getattr(status, "phase", None)
    return f"Kubernetes job {job_name} failed with pod phase {phase or 'unknown'}."
