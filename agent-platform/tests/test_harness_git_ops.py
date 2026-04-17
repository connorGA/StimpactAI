from __future__ import annotations

import subprocess
from pathlib import Path

from harness.git_ops.checkpoints import GitCheckpointManager
from harness.schemas.git import GitAction, GitFileChangeStatus


def test_git_checkpoint_manager_reports_structured_current_branch_info(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    tracked_file = tmp_path / "tracked.py"
    tracked_file.write_text("print('baseline')\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.py")
    _git(tmp_path, "commit", "-m", "initial commit")

    tracked_file.write_text("print('changed')\n", encoding="utf-8")
    staged_file = tmp_path / "staged.py"
    staged_file.write_text("print('staged')\n", encoding="utf-8")
    _git(tmp_path, "add", "staged.py")
    (tmp_path / "scratch.txt").write_text("temp\n", encoding="utf-8")

    manager = GitCheckpointManager()
    result = manager.current_branch_info(repository_root=str(tmp_path))

    assert result.ok is True
    assert result.action is GitAction.CURRENT_BRANCH_INFO
    assert result.branch_info is not None
    assert result.branch_info.branch_name == "main"
    assert result.branch_info.is_dirty is True
    assert result.branch_info.has_staged_changes is True
    assert result.branch_info.has_unstaged_changes is True
    assert result.branch_info.has_untracked_files is True
    assert "staged.py" in result.branch_info.staged_files
    assert "tracked.py" in result.branch_info.unstaged_files
    assert "scratch.txt" in result.branch_info.untracked_files


def test_git_checkpoint_manager_returns_diff_since_checkpoint(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    tracked_file = tmp_path / "service.py"
    tracked_file.write_text("version = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "service.py")
    _git(tmp_path, "commit", "-m", "initial commit")

    manager = GitCheckpointManager()
    checkpoint = manager.create_checkpoint(repository_root=str(tmp_path), label="known good").checkpoint
    assert checkpoint is not None

    tracked_file.write_text("version = 2\n", encoding="utf-8")
    added_file = tmp_path / "new_module.py"
    added_file.write_text("print('new')\n", encoding="utf-8")
    _git(tmp_path, "add", "new_module.py")

    diff_result = manager.diff_since_checkpoint(
        repository_root=str(tmp_path),
        checkpoint_ref=checkpoint.tag_name,
    )

    assert diff_result.ok is True
    assert diff_result.action is GitAction.DIFF_SINCE_CHECKPOINT
    assert diff_result.diff is not None
    assert diff_result.diff.checkpoint_ref == checkpoint.tag_name
    statuses = {item.path: item.status for item in diff_result.diff.changed_files}
    assert statuses["service.py"] is GitFileChangeStatus.MODIFIED
    assert statuses["new_module.py"] is GitFileChangeStatus.ADDED
    assert "version = 2" in diff_result.diff.patch
    assert "new_module.py" in diff_result.diff.patch


def test_git_checkpoint_manager_preserves_patch_trailing_newline(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    package_lock = tmp_path / "package-lock.json"
    package_lock.write_text('{\n  "name": "demo"\n}\n', encoding="utf-8")
    _git(tmp_path, "add", "package-lock.json")
    _git(tmp_path, "commit", "-m", "initial commit")

    manager = GitCheckpointManager()
    checkpoint = manager.create_checkpoint(repository_root=str(tmp_path), label="known good").checkpoint
    assert checkpoint is not None

    package_lock.write_text(
        '{\n  "name": "demo",\n  "packages": {\n    "node_modules/example": {\n      "version": "1.0.0"\n    }\n  }\n}\n',
        encoding="utf-8",
    )

    diff_result = manager.diff_since_checkpoint(
        repository_root=str(tmp_path),
        checkpoint_ref=checkpoint.tag_name,
    )

    assert diff_result.diff is not None
    assert diff_result.diff.patch.endswith("\n")

    patch_path = tmp_path / "patch.diff"
    patch_path.write_text(diff_result.diff.patch, encoding="utf-8")
    verify_repo = tmp_path / "verify"
    _git(tmp_path, "clone", "--quiet", "--no-local", str(tmp_path), str(verify_repo))
    _git(verify_repo, "checkout", "--quiet", checkpoint.tag_name)
    apply_result = subprocess.run(
        ["git", "apply", "--check", str(patch_path)],
        cwd=verify_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert apply_result.returncode == 0, apply_result.stderr


def test_git_checkpoint_manager_discards_failed_work_using_latest_checkpoint(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    tracked_file = tmp_path / "app.txt"
    tracked_file.write_text("baseline\n", encoding="utf-8")
    _git(tmp_path, "add", "app.txt")
    _git(tmp_path, "commit", "-m", "initial commit")

    manager = GitCheckpointManager()
    tracked_file.write_text("known good\n", encoding="utf-8")
    checkpoint = manager.create_checkpoint(repository_root=str(tmp_path), label="latest stable").checkpoint
    assert checkpoint is not None

    tracked_file.write_text("broken attempt\n", encoding="utf-8")
    (tmp_path / "scratch.log").write_text("temporary\n", encoding="utf-8")

    result = manager.discard_failed_work(repository_root=str(tmp_path))

    assert result.ok is True
    assert result.action is GitAction.DISCARD_FAILED_WORK
    assert result.target_ref == checkpoint.tag_name
    assert tracked_file.read_text(encoding="utf-8") == "known good\n"
    assert not (tmp_path / "scratch.log").exists()


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
