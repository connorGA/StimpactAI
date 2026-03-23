from __future__ import annotations

from datetime import UTC, datetime

from models.control_plane import (
    ProviderKind,
    RepoProfileRecord,
    RepoProfileSecretBindingRecord,
    RuntimeKind,
    SecretBackend,
    SecretRefRecord,
)
from sandbox.kubernetes_runner import (
    KubernetesJobLauncher,
    KubernetesJobMonitor,
    KubernetesJobStatus,
    KubernetesSandboxRunner,
    _extract_phase_results,
)
from services.repository_provider import RepositorySnapshot


def build_repo_profile() -> RepoProfileRecord:
    now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
    return RepoProfileRecord(
        id="profile-1",
        project_id="project-1",
        provider_repository_id="provider-repo-1",
        runtime_kind=RuntimeKind.PYTHON,
        base_image="public.ecr.aws/acme/sandbox:latest",
        install_command="pip install -r requirements.txt",
        startup_commands=["python app.py"],
        reproduce_command="python reproduce.py",
        verify_command="pytest",
        success_criteria="Exit 0 after patch verification.",
        network_allowlist=["pypi.org", "files.pythonhosted.org"],
        active=True,
        created_at=now,
        updated_at=now,
    )


def build_snapshot() -> RepositorySnapshot:
    return RepositorySnapshot(
        provider=ProviderKind.GITHUB,
        clone_url="https://github.com/acme/billing-api.git",
        owner="acme",
        repository_name="billing-api",
        default_branch="main",
        target_commit_sha="deadbeef",
    )


def build_secret_bindings() -> list[RepoProfileSecretBindingRecord]:
    now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
    secret_ref = SecretRefRecord(
        id="secret-1",
        project_id="project-1",
        label="OPENAI_API_KEY",
        description="Runtime secret",
        backend=SecretBackend.AWS_SECRETS_MANAGER,
        external_ref="arn:aws:secretsmanager:us-west-2:123456789012:secret:project/runtime-openai",
        created_at=now,
        updated_at=now,
    )
    file_secret_ref = SecretRefRecord(
        id="secret-2",
        project_id="project-1",
        label="RUNTIME_KEY_FILE",
        description="Runtime file secret",
        backend=SecretBackend.AWS_SECRETS_MANAGER,
        external_ref="arn:aws:secretsmanager:us-west-2:123456789012:secret:project/runtime-file",
        created_at=now,
        updated_at=now,
    )
    return [
        RepoProfileSecretBindingRecord(
            repo_profile_id="profile-1",
            mount_as="OPENAI_API_KEY",
            secret_ref=secret_ref,
            created_at=now,
        ),
        RepoProfileSecretBindingRecord(
            repo_profile_id="profile-1",
            mount_as="/var/run/secrets/runtime/openai.key",
            secret_ref=file_secret_ref,
            created_at=now,
        ),
    ]


class FakeKubernetesClusterClient:
    def __init__(self) -> None:
        self.applied_manifest = None
        self.polled_job_ids: list[str] = []

    def apply_manifest(self, manifest):
        self.applied_manifest = manifest
        return "stimpact-sandbox-sandbox-1:uid-123"

    def poll_job(self, *, external_job_id: str) -> KubernetesJobStatus:
        self.polled_job_ids.append(external_job_id)
        return KubernetesJobStatus(
            status="succeeded",
            summary="Kubernetes job succeeded.",
            execution_log="pod logs",
        )


def test_kubernetes_job_launcher_builds_manifest() -> None:
    launcher = KubernetesJobLauncher(
        namespace="sandbox",
        base_image="public.ecr.aws/acme/sandbox:latest",
        service_account_name="sandbox-sa",
        cluster_client=FakeKubernetesClusterClient(),
    )
    manifest = launcher.build_job_manifest(
        incident_id="incident-1",
        sandbox_run_id="sandbox-1",
        snapshot=build_snapshot(),
        repo_profile=build_repo_profile(),
        patch_diff_s3_uri="s3://artifact-bucket/sandbox-runs/sandbox-1/patch.diff",
        patch_diff_content="diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n",
        network_allowlist=["pypi.org"],
        network_allowlist_cidrs=["151.101.0.223/32"],
        secret_bindings=build_secret_bindings(),
        repository_archive_url=None,
        provider_access_secret_arn="arn:aws:secretsmanager:us-west-2:123456789012:secret:provider-access",
    )

    assert manifest["kind"] == "List"
    items = manifest["items"]
    assert isinstance(items, list)
    job = next(item for item in items if item["kind"] == "Job")
    network_policy = next(item for item in items if item["kind"] == "NetworkPolicy")
    metadata = job["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["namespace"] == "sandbox"
    spec = job["spec"]
    assert isinstance(spec, dict)
    template = spec["template"]
    assert isinstance(template, dict)
    pod_spec = template["spec"]
    assert isinstance(pod_spec, dict)
    assert pod_spec["serviceAccountName"] == "sandbox-sa"
    assert pod_spec["nodeSelector"] == {"stimpact.ai/workload": "sandbox"}
    assert pod_spec["enableServiceLinks"] is False
    assert len(pod_spec["initContainers"]) == 2
    containers = pod_spec["containers"]
    assert isinstance(containers, list)
    container = containers[0]
    assert container["workingDir"] == "/workspace/repo"
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert len(container["volumeMounts"]) == 4
    env = containers[0]["env"]
    assert isinstance(env, list)
    assert any(
        entry["name"] == "STIMPACT_PROVIDER_ACCESS_SECRET_ARN"
        and entry["value"] == "arn:aws:secretsmanager:us-west-2:123456789012:secret:provider-access"
        for entry in env
        if isinstance(entry, dict)
    )
    assert any(
        entry["name"] == "STIMPACT_CLONE_URL" and entry["value"] == "https://github.com/acme/billing-api.git"
        for entry in env
        if isinstance(entry, dict)
    )
    secrets_init = pod_spec["initContainers"][0]
    clone_init = pod_spec["initContainers"][1]
    assert any(
        entry["name"] == "STIMPACT_SECRET_BINDING_COUNT" and entry["value"] == "2"
        for entry in secrets_init["env"]
        if isinstance(entry, dict)
    )
    assert any(
        entry["name"] == "STIMPACT_SECRET_BINDING_0_EXTERNAL_REF"
        and entry["value"].startswith("arn:aws:secretsmanager:")
        for entry in secrets_init["env"]
        if isinstance(entry, dict)
    )
    assert "aws secretsmanager get-secret-value" in secrets_init["args"][0]
    assert "/workspace/.stimpact/provider-clone-url" in secrets_init["args"][0]
    assert "/workspace/.stimpact/patch.diff" in clone_init["args"][0]
    assert "printf '%s\\n' \"$STIMPACT_PATCH_DIFF_CONTENT\"" in clone_init["args"][0]
    assert "STIMPACT_REPOSITORY_ARCHIVE_URL" in clone_init["args"][0]
    assert "git checkout --quiet \"$STIMPACT_TARGET_COMMIT_SHA\"" in clone_init["args"][0]
    assert "git apply /workspace/.stimpact/patch.diff" not in clone_init["args"][0]
    assert "file-mounts.tsv" in container["args"][0]
    assert "printf 'STIMPACT_PHASE_RESULT phase=%s status=observed exit_code=%s\\n' reproduce \"$code\"" in container["args"][0]
    assert "printf 'STIMPACT_PHASE_RESULT phase=%s status=passed\\n' patch-apply" in container["args"][0]
    assert "printf 'STIMPACT_PHASE_RESULT phase=%s status=passed\\n' verify" in container["args"][0]
    assert network_policy["spec"]["policyTypes"] == ["Egress"]
    assert network_policy["spec"]["egress"][1]["to"][0]["ipBlock"]["cidr"] == "151.101.0.223/32"


def test_kubernetes_sandbox_runner_returns_submission() -> None:
    cluster_client = FakeKubernetesClusterClient()
    runner = KubernetesSandboxRunner(cluster_client=cluster_client)
    submission = runner.submit(
        incident_id="incident-1",
        sandbox_run_id="sandbox-1",
        snapshot=build_snapshot(),
        repo_profile=build_repo_profile(),
        patch_diff_s3_uri="s3://artifact-bucket/sandbox-runs/sandbox-1/patch.diff",
        patch_diff_content="diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n",
        network_allowlist=["pypi.org"],
        network_allowlist_cidrs=["151.101.0.223/32"],
        secret_bindings=build_secret_bindings(),
        repository_archive_url=None,
        provider_access_secret_arn="arn:aws:secretsmanager:us-west-2:123456789012:secret:provider-access",
    )

    assert submission.external_job_id == "stimpact-sandbox-sandbox-1:uid-123"
    assert submission.manifest["kind"] == "List"
    assert cluster_client.applied_manifest is submission.manifest


def test_kubernetes_job_launcher_uses_repository_archive_when_provided() -> None:
    launcher = KubernetesJobLauncher(
        namespace="sandbox",
        base_image="public.ecr.aws/acme/sandbox:latest",
        service_account_name="sandbox-sa",
        cluster_client=FakeKubernetesClusterClient(),
    )
    manifest = launcher.build_job_manifest(
        incident_id="incident-1",
        sandbox_run_id="sandbox-1",
        snapshot=build_snapshot(),
        repo_profile=build_repo_profile(),
        patch_diff_s3_uri="s3://artifact-bucket/sandbox-runs/sandbox-1/patch.diff",
        patch_diff_content="diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n",
        network_allowlist=["pypi.org"],
        network_allowlist_cidrs=["151.101.0.223/32"],
        secret_bindings=[],
        repository_archive_url="https://example.com/repo.tar.gz?signature=test",
        provider_access_secret_arn=None,
    )

    job = next(item for item in manifest["items"] if item["kind"] == "Job")
    pod_spec = job["spec"]["template"]["spec"]
    init_container = pod_spec["initContainers"][1]

    assert "wget -q -O /workspace/.stimpact/repo.tar.gz \"$STIMPACT_REPOSITORY_ARCHIVE_URL\"" in init_container["args"][0]
    assert "tar -xzf /workspace/.stimpact/repo.tar.gz -C /workspace/repo" in init_container["args"][0]
    assert "git init --quiet /workspace/repo" in init_container["args"][0]
    assert any(
        entry["name"] == "STIMPACT_REPOSITORY_ARCHIVE_URL"
        and entry["value"] == "https://example.com/repo.tar.gz?signature=test"
        for entry in init_container["env"]
        if isinstance(entry, dict)
    )


def test_kubernetes_job_monitor_returns_cluster_status() -> None:
    cluster_client = FakeKubernetesClusterClient()
    monitor = KubernetesJobMonitor(cluster_client=cluster_client)

    status = monitor.poll_status(external_job_id="stimpact-sandbox-1:uid-123")

    assert status.status == "succeeded"
    assert status.execution_log == "pod logs"
    assert cluster_client.polled_job_ids == ["stimpact-sandbox-1:uid-123"]


def test_extract_phase_results_parses_structured_phase_markers() -> None:
    results = _extract_phase_results(
        "\n".join(
            [
                "STIMPACT_PHASE_RESULT phase=reproduce status=observed exit_code=1",
                "STIMPACT_PHASE_RESULT phase=patch-apply status=passed",
                "STIMPACT_PHASE_RESULT phase=verify status=failed exit_code=1",
            ]
        )
    )

    assert results == {
        "reproduce": True,
        "patch-apply": True,
        "verify": False,
    }
