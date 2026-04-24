from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import subprocess

from models.control_plane import ProviderIntegrationRecord, ProviderIntegrationStatus, ProviderKind, ProviderRepositoryRecord
from services.provider_clients import apply_patch_and_push_branch
from services.github_provider import GitHubProviderClient
from services.gitlab_provider import GitLabProviderClient
from services.repository_provider import get_provider_adapter


def build_repository(provider: ProviderKind) -> ProviderRepositoryRecord:
    now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
    return ProviderRepositoryRecord(
        id="provider-repo-1",
        provider_integration_id="integration-1",
        provider=provider,
        external_repository_id="123",
        owner="acme",
        name="billing-api",
        default_branch="main",
        clone_url=f"https://{provider.value}.com/acme/billing-api.git",
        created_at=now,
        updated_at=now,
    )


def test_github_provider_adapter_builds_snapshot_and_compare_url() -> None:
    adapter = get_provider_adapter(ProviderKind.GITHUB)
    repository = build_repository(ProviderKind.GITHUB)

    snapshot = adapter.build_snapshot(repository=repository, target_commit_sha="deadbeef")
    compare_url = adapter.build_change_request_url(
        repository=repository,
        branch_name=adapter.build_branch_name(incident_id="incident-1"),
    )

    assert snapshot.provider is ProviderKind.GITHUB
    assert snapshot.target_commit_sha == "deadbeef"
    assert compare_url.startswith("https://github.com/acme/billing-api/compare/")


def test_gitlab_provider_adapter_builds_snapshot_and_merge_request_url() -> None:
    adapter = get_provider_adapter(ProviderKind.GITLAB)
    repository = build_repository(ProviderKind.GITLAB)

    snapshot = adapter.build_snapshot(repository=repository, target_commit_sha="cafebabe")
    merge_request_url = adapter.build_change_request_url(
        repository=repository,
        branch_name=adapter.build_branch_name(incident_id="incident-1"),
    )

    assert snapshot.provider is ProviderKind.GITLAB
    assert snapshot.target_commit_sha == "cafebabe"
    assert "/-/merge_requests/new" in merge_request_url


def test_gitlab_provider_client_builds_oauth_authorization_url(monkeypatch) -> None:
    monkeypatch.setenv("GITLAB_APPLICATION_ID", "gitlab-app-id")
    monkeypatch.setenv("GITLAB_CALLBACK_URL", "https://example.ngrok.dev/auth/gitlab/callback")
    client = GitLabProviderClient(base_url="https://gitlab.com")

    authorization = client.build_authorization(state="oauth-state-1")

    assert authorization.state == "oauth-state-1"
    assert authorization.authorization_url.startswith("https://gitlab.com/oauth/authorize")
    assert "client_id=gitlab-app-id" in authorization.authorization_url
    assert "state=oauth-state-1" in authorization.authorization_url


def test_provider_integration_record_decodes_json_metadata_strings() -> None:
    now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
    record = ProviderIntegrationRecord.from_db_row(
        {
            "id": "integration-1",
            "provider": "github",
            "name": "Acme GitHub",
            "status": "active",
            "credentials_secret_ref_id": None,
            "webhook_secret_ref_id": None,
            "aws_region": "us-west-2",
            "metadata": (
                '{"project_id":"project-1","install_state":"state-1",'
                '"redirect_url":"http://localhost:3000/onboarding?project_id=project-1"}'
            ),
            "created_at": now,
            "updated_at": now,
        }
    )

    assert record.metadata["project_id"] == "project-1"
    assert record.metadata["install_state"] == "state-1"


def test_github_provider_client_builds_installation_url(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_APP_NAME", "stimpact")
    client = GitHubProviderClient()

    installation_url = client.build_installation_url(state="install-state-1")

    assert installation_url == "https://github.com/apps/stimpact/installations/new?state=install-state-1"


async def test_github_provider_client_builds_sandbox_access(monkeypatch) -> None:
    now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
    integration = ProviderIntegrationRecord(
        id="integration-1",
        provider=ProviderKind.GITHUB,
        name="Acme GitHub",
        status=ProviderIntegrationStatus.ACTIVE,
        credentials_secret_ref_id=None,
        webhook_secret_ref_id=None,
        aws_region="us-west-2",
        metadata={"installation_id": "117170229"},
        created_at=now,
        updated_at=now,
    )
    repository = build_repository(ProviderKind.GITHUB)
    client = GitHubProviderClient()

    async def fake_create_installation_token(installation_id: str) -> str:
        assert installation_id == "117170229"
        return "token-123"

    monkeypatch.setattr(client, "_create_installation_token", fake_create_installation_token)
    access = await client.build_sandbox_access(integration, repository)
    assert access.secret_format == "text"
    assert access.secret_value.startswith("https://x-access-token:token-123@github.com/")


def test_apply_patch_and_push_branch_accepts_diff_without_trailing_newline(tmp_path: Path) -> None:
    remote_dir = tmp_path / "remote.git"
    work_dir = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", str(remote_dir)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "clone", str(remote_dir), str(work_dir)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=work_dir, check=True, capture_output=True, text=True)
    (work_dir / "app.py").write_text("print('broken')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=work_dir, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.name=Test User", "-c", "user.email=test@example.com", "commit", "-m", "initial"],
        cwd=work_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=work_dir, check=True, capture_output=True, text=True)

    (work_dir / "app.py").write_text("print('fixed')\n", encoding="utf-8")
    patch = subprocess.run(
        ["git", "diff", "--", "app.py"],
        cwd=work_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.rstrip("\n")
    subprocess.run(["git", "checkout", "--", "app.py"], cwd=work_dir, check=True, capture_output=True, text=True)
    commit_sha = apply_patch_and_push_branch(
        clone_url=str(remote_dir),
        default_branch="main",
        branch_name="stimpact/fix/test",
        patch_diff=patch,
        commit_message="Apply fix",
    )

    verification_dir = tmp_path / "verify"
    subprocess.run(["git", "clone", "--branch", "stimpact/fix/test", str(remote_dir), str(verification_dir)], check=True, capture_output=True, text=True)
    assert len(commit_sha) == 40
    assert (verification_dir / "app.py").read_text(encoding="utf-8") == "print('fixed')\n"


def test_apply_patch_and_push_branch_uses_explicit_base_commit(tmp_path: Path) -> None:
    remote_dir = tmp_path / "remote.git"
    work_dir = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", str(remote_dir)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "clone", str(remote_dir), str(work_dir)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=work_dir, check=True, capture_output=True, text=True)
    (work_dir / "app.py").write_text("print('broken')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=work_dir, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.name=Test User", "-c", "user.email=test@example.com", "commit", "-m", "initial"],
        cwd=work_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    base_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=work_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=work_dir, check=True, capture_output=True, text=True)

    (work_dir / "app.py").write_text("print('fixed from base')\n", encoding="utf-8")
    patch = subprocess.run(
        ["git", "diff", "--", "app.py"],
        cwd=work_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    subprocess.run(["git", "checkout", "--", "app.py"], cwd=work_dir, check=True, capture_output=True, text=True)

    (work_dir / "app.py").write_text("print('default branch moved')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=work_dir, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.name=Test User", "-c", "user.email=test@example.com", "commit", "-m", "move main"],
        cwd=work_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["git", "push"], cwd=work_dir, check=True, capture_output=True, text=True)

    commit_sha = apply_patch_and_push_branch(
        clone_url=str(remote_dir),
        default_branch="main",
        branch_name="stimpact/fix/base-test",
        patch_diff=patch,
        commit_message="Apply fix",
        base_commit_sha=base_commit,
    )

    verification_dir = tmp_path / "verify-base"
    subprocess.run(["git", "clone", "--branch", "stimpact/fix/base-test", str(remote_dir), str(verification_dir)], check=True, capture_output=True, text=True)
    parent_sha = subprocess.run(
        ["git", "rev-parse", f"{commit_sha}^"],
        cwd=verification_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert parent_sha == base_commit
    assert (verification_dir / "app.py").read_text(encoding="utf-8") == "print('fixed from base')\n"
