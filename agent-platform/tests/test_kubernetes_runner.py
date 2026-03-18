from __future__ import annotations

from datetime import UTC, datetime

from models.control_plane import ProviderKind, RepoProfileRecord, RuntimeKind
from sandbox.kubernetes_runner import KubernetesJobLauncher, KubernetesSandboxRunner
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


def test_kubernetes_job_launcher_builds_manifest() -> None:
    launcher = KubernetesJobLauncher(
        namespace="sandbox",
        base_image="public.ecr.aws/acme/sandbox:latest",
        service_account_name="sandbox-sa",
    )
    manifest = launcher.build_job_manifest(
        incident_id="incident-1",
        sandbox_run_id="sandbox-1",
        snapshot=build_snapshot(),
        repo_profile=build_repo_profile(),
        patch_diff_s3_uri="s3://artifact-bucket/sandbox-runs/sandbox-1/patch.diff",
        network_allowlist=["pypi.org"],
        secret_env_refs=["OPENAI_API_KEY"],
        provider_access_secret_arn="arn:aws:secretsmanager:us-west-2:123456789012:secret:provider-access",
        provider_access_secret_format="json",
    )

    assert manifest["kind"] == "Job"
    metadata = manifest["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["namespace"] == "sandbox"
    spec = manifest["spec"]
    assert isinstance(spec, dict)
    template = spec["template"]
    assert isinstance(template, dict)
    pod_spec = template["spec"]
    assert isinstance(pod_spec, dict)
    assert pod_spec["serviceAccountName"] == "sandbox-sa"
    assert pod_spec["nodeSelector"] == {"stimpact.ai/workload": "sandbox"}
    containers = pod_spec["containers"]
    assert isinstance(containers, list)
    env = containers[0]["env"]
    assert isinstance(env, list)
    assert any(
        entry["name"] == "STIMPACT_PROVIDER_ACCESS_SECRET_ARN"
        and entry["value"] == "arn:aws:secretsmanager:us-west-2:123456789012:secret:provider-access"
        for entry in env
        if isinstance(entry, dict)
    )


def test_kubernetes_sandbox_runner_returns_submission() -> None:
    runner = KubernetesSandboxRunner()
    submission = runner.submit(
        incident_id="incident-1",
        sandbox_run_id="sandbox-1",
        snapshot=build_snapshot(),
        repo_profile=build_repo_profile(),
        patch_diff_s3_uri="s3://artifact-bucket/sandbox-runs/sandbox-1/patch.diff",
        network_allowlist=["pypi.org"],
        secret_env_refs=["OPENAI_API_KEY"],
        provider_access_secret_arn="arn:aws:secretsmanager:us-west-2:123456789012:secret:provider-access",
        provider_access_secret_format="json",
    )

    assert submission.external_job_id.startswith("stimpact-sandbox-")
    assert submission.manifest["kind"] == "Job"
