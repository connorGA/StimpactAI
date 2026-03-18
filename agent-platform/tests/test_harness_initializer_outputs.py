from __future__ import annotations

import subprocess
from pathlib import Path

from harness.git_ops.checkpoints import GitCheckpointManager
from harness.runtime.initializer import InitializerOutputBuilder
from harness.schemas.initializer import FeatureCatalog, FeatureSeed, FeatureStatus
from harness.schemas.verification import VerificationKind, VerificationStatus


def test_initializer_output_builder_persists_init_script_and_feature_catalog(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\nversion = '0.1.0'\n", encoding="utf-8")
    (tmp_path / "requirements-dev.txt").write_text("pytest\n", encoding="utf-8")
    (tmp_path / "client-ui").mkdir()
    (tmp_path / "client-ui" / "package.json").write_text('{"name":"client-ui"}\n', encoding="utf-8")

    builder = InitializerOutputBuilder()
    output = builder.build_output(
        repository_root=str(tmp_path),
        summary="Initializer mapped local setup and product capabilities.",
        feature_seeds=[
            FeatureSeed(
                feature_name="user can open a new chat",
                description="The user can navigate to chat and start a new conversation.",
                verification_method="Browser workflow smoke test",
                required_verification=[VerificationKind.BROWSER],
                notes=["Initial state should remain unverified until executed."],
            ),
            FeatureSeed(
                feature_name="dashboard loads with incident summaries",
                description="The dashboard renders incident summaries for the signed-in user.",
                verification_method="Authenticated browser check",
                required_verification=[VerificationKind.INTEGRATION, VerificationKind.BROWSER],
            ),
        ],
        environment_notes=["Requires Python and Node installed locally."],
    )

    builder.persist_output(repository_root=str(tmp_path), initializer_output=output)

    init_path = tmp_path / "init.sh"
    features_path = tmp_path / ".stimpactai" / "features.json"

    assert init_path.exists()
    assert ".venv/bin/activate" in init_path.read_text(encoding="utf-8")
    assert "cd client-ui && npm run dev" in init_path.read_text(encoding="utf-8")
    assert init_path.stat().st_mode & 0o111

    catalog = FeatureCatalog.model_validate_json(features_path.read_text(encoding="utf-8"))
    assert len(catalog.features) == 2
    assert catalog.features[0].status is FeatureStatus.UNVERIFIED
    assert catalog.features[0].id == "user-can-open-a-new-chat"
    assert catalog.features[0].verification_state.status is VerificationStatus.UNVERIFIED
    assert catalog.features[0].verification_state.can_mark_complete is False
    assert catalog.features[0].required_verification == [VerificationKind.BROWSER]


def test_git_checkpoint_manager_reset_failed_attempt_restores_checkpoint(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    tracked_file = tmp_path / "app.txt"
    tracked_file.write_text("baseline\n", encoding="utf-8")
    _git(tmp_path, "add", "app.txt")
    _git(tmp_path, "commit", "-m", "initial commit")

    tracked_file.write_text("checkpointed\n", encoding="utf-8")
    manager = GitCheckpointManager()
    checkpoint_result = manager.create_checkpoint(repository_root=str(tmp_path), label="baseline state")
    checkpoint = checkpoint_result.checkpoint
    assert checkpoint is not None

    tracked_file.write_text("broken attempt\n", encoding="utf-8")
    (tmp_path / "scratch.log").write_text("temporary\n", encoding="utf-8")

    result = manager.reset_failed_attempt(
        repository_root=str(tmp_path),
        checkpoint_ref=checkpoint.tag_name,
    )

    assert result.ok is True
    assert tracked_file.read_text(encoding="utf-8") == "checkpointed\n"
    assert not (tmp_path / "scratch.log").exists()


def test_git_checkpoint_manager_can_revert_to_checkpoint_commit(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    tracked_file = tmp_path / "service.py"
    tracked_file.write_text("version = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "service.py")
    _git(tmp_path, "commit", "-m", "initial commit")

    manager = GitCheckpointManager()
    checkpoint = manager.create_checkpoint(repository_root=str(tmp_path), label="known good").checkpoint
    assert checkpoint is not None

    tracked_file.write_text("version = 2\n", encoding="utf-8")
    _git(tmp_path, "add", "service.py")
    _git(tmp_path, "commit", "-m", "breaking change")

    result = manager.revert_to_checkpoint(
        repository_root=str(tmp_path),
        checkpoint_ref=checkpoint.commit_sha,
    )

    assert result.ok is True
    assert tracked_file.read_text(encoding="utf-8") == "version = 1\n"


def _init_git_repo(repository_root: Path) -> None:
    _git(repository_root, "init", "-b", "main")
    _git(repository_root, "config", "user.email", "test@example.com")
    _git(repository_root, "config", "user.name", "Test User")


def _git(repository_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or result.stderr.strip()
