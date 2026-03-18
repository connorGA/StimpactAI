from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from harness.schemas.git import (
    GitAction,
    GitActionResult,
    GitBranchInfo,
    GitChangedFile,
    GitCheckpointRecord,
    GitDiffInspection,
    GitFileChangeStatus,
)


class GitCheckpointManager:
    def current_branch_info(self, *, repository_root: str) -> GitActionResult:
        root = Path(repository_root).resolve()
        branch_info = self._build_branch_info(root)
        return GitActionResult(
            ok=True,
            action=GitAction.CURRENT_BRANCH_INFO,
            target_ref=branch_info.head_sha,
            branch_name=branch_info.branch_name,
            output=f"Current branch is {branch_info.branch_name} at {branch_info.head_sha}.",
            branch_info=branch_info,
        )

    def create_checkpoint(self, *, repository_root: str, label: str) -> GitActionResult:
        root = Path(repository_root).resolve()
        branch_name = self._git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        sanitized_label = self._sanitize_label(label)
        checkpoint_message = f"stimpact checkpoint: {sanitized_label}"
        self._git(root, "add", "-A")
        self._git(root, "commit", "--allow-empty", "-m", checkpoint_message)
        commit_sha = self._git(root, "rev-parse", "HEAD").strip()
        tag_name = f"stimpact-checkpoint/{sanitized_label}"
        self._delete_tag_if_exists(root, tag_name)
        self._git(root, "tag", tag_name, commit_sha)
        checkpoint = GitCheckpointRecord(
            commit_sha=commit_sha,
            tag_name=tag_name,
            branch_name=branch_name,
            created_at=datetime.now(UTC),
        )
        return GitActionResult(
            ok=True,
            action=GitAction.CHECKPOINT,
            target_ref=commit_sha,
            branch_name=branch_name,
            output=checkpoint_message,
            checkpoint=checkpoint,
            branch_info=self._build_branch_info(root),
        )

    def revert_to_checkpoint(
        self,
        *,
        repository_root: str,
        checkpoint_ref: str | None = None,
    ) -> GitActionResult:
        root = Path(repository_root).resolve()
        resolved_checkpoint_ref = self._resolve_checkpoint_ref(root, checkpoint_ref)
        branch_name = self._git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        self._git(root, "reset", "--hard", resolved_checkpoint_ref)
        return GitActionResult(
            ok=True,
            action=GitAction.REVERT_TO_CHECKPOINT,
            target_ref=resolved_checkpoint_ref,
            branch_name=branch_name,
            output=f"Repository reset to {resolved_checkpoint_ref}.",
            branch_info=self._build_branch_info(root),
        )

    def reset_failed_attempt(
        self,
        *,
        repository_root: str,
        checkpoint_ref: str | None = None,
    ) -> GitActionResult:
        root = Path(repository_root).resolve()
        resolved_checkpoint_ref = self._resolve_checkpoint_ref(root, checkpoint_ref)
        branch_name = self._git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        self._git(root, "reset", "--hard", resolved_checkpoint_ref)
        self._git(root, "clean", "-fd")
        return GitActionResult(
            ok=True,
            action=GitAction.RESET_FAILED_ATTEMPT,
            target_ref=resolved_checkpoint_ref,
            branch_name=branch_name,
            output=f"Repository hard reset and cleaned back to {resolved_checkpoint_ref}.",
            branch_info=self._build_branch_info(root),
        )

    def discard_failed_work(
        self,
        *,
        repository_root: str,
        checkpoint_ref: str | None = None,
    ) -> GitActionResult:
        root = Path(repository_root).resolve()
        resolved_checkpoint_ref = self._resolve_checkpoint_ref(root, checkpoint_ref)
        branch_name = self._git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        self._git(root, "reset", "--hard", resolved_checkpoint_ref)
        self._git(root, "clean", "-fd")
        return GitActionResult(
            ok=True,
            action=GitAction.DISCARD_FAILED_WORK,
            target_ref=resolved_checkpoint_ref,
            branch_name=branch_name,
            output=f"Discarded failed work and restored repository to {resolved_checkpoint_ref}.",
            branch_info=self._build_branch_info(root),
        )

    def diff_since_checkpoint(
        self,
        *,
        repository_root: str,
        checkpoint_ref: str | None = None,
    ) -> GitActionResult:
        root = Path(repository_root).resolve()
        resolved_checkpoint_ref = self._resolve_checkpoint_ref(root, checkpoint_ref)
        branch_info = self._build_branch_info(root)
        name_status_output = self._git(root, "diff", "--name-status", resolved_checkpoint_ref, "--")
        patch_output = self._git(root, "diff", "--binary", "--no-ext-diff", resolved_checkpoint_ref, "--")
        diff = GitDiffInspection(
            checkpoint_ref=resolved_checkpoint_ref,
            changed_files=self._parse_name_status_output(name_status_output),
            patch=patch_output,
        )
        return GitActionResult(
            ok=True,
            action=GitAction.DIFF_SINCE_CHECKPOINT,
            target_ref=resolved_checkpoint_ref,
            branch_name=branch_info.branch_name,
            output=f"Collected diff from {resolved_checkpoint_ref} to working tree.",
            branch_info=branch_info,
            diff=diff,
        )

    def _delete_tag_if_exists(self, repository_root: Path, tag_name: str) -> None:
        result = subprocess.run(
            ["git", "tag", "--list", tag_name],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            self._git(repository_root, "tag", "-d", tag_name)

    def _build_branch_info(self, repository_root: Path) -> GitBranchInfo:
        branch_name = self._git(repository_root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        head_sha = self._git(repository_root, "rev-parse", "HEAD").strip()
        upstream_branch = self._git_optional(
            repository_root,
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{upstream}",
        )
        staged_files: list[str] = []
        unstaged_files: list[str] = []
        untracked_files: list[str] = []
        porcelain_output = self._git(repository_root, "status", "--porcelain")
        for line in [entry for entry in porcelain_output.splitlines() if entry.strip()]:
            status = line[:2]
            path = line[3:]
            staged_status = status[0]
            unstaged_status = status[1]
            if status == "??":
                untracked_files.append(path)
                continue
            if staged_status != " ":
                staged_files.append(path)
            if unstaged_status != " ":
                unstaged_files.append(path)
        return GitBranchInfo(
            branch_name=branch_name,
            upstream_branch=upstream_branch or None,
            head_sha=head_sha,
            is_dirty=bool(staged_files or unstaged_files or untracked_files),
            has_staged_changes=bool(staged_files),
            has_unstaged_changes=bool(unstaged_files),
            has_untracked_files=bool(untracked_files),
            staged_files=staged_files,
            unstaged_files=unstaged_files,
            untracked_files=untracked_files,
        )

    def _resolve_checkpoint_ref(self, repository_root: Path, checkpoint_ref: str | None) -> str:
        if checkpoint_ref:
            return checkpoint_ref
        latest_checkpoint = self._git_optional(
            repository_root,
            "for-each-ref",
            "--sort=-creatordate",
            "--format=%(refname:short)",
            "refs/tags/stimpact-checkpoint/*",
        )
        if not latest_checkpoint:
            raise ValueError("No checkpoint reference was provided and no stimpact checkpoint tags exist.")
        return latest_checkpoint.splitlines()[0].strip()

    def _parse_name_status_output(self, value: str) -> list[GitChangedFile]:
        changed_files: list[GitChangedFile] = []
        for line in [entry for entry in value.splitlines() if entry.strip()]:
            parts = line.split("\t")
            status_token = parts[0]
            status = self._map_change_status(status_token)
            if status is GitFileChangeStatus.RENAMED and len(parts) >= 3:
                changed_files.append(
                    GitChangedFile(
                        path=parts[2],
                        previous_path=parts[1],
                        status=status,
                    )
                )
                continue
            changed_files.append(
                GitChangedFile(
                    path=parts[-1],
                    status=status,
                )
            )
        return changed_files

    def _map_change_status(self, value: str) -> GitFileChangeStatus:
        token = value[:1]
        mapping = {
            "A": GitFileChangeStatus.ADDED,
            "M": GitFileChangeStatus.MODIFIED,
            "D": GitFileChangeStatus.DELETED,
            "R": GitFileChangeStatus.RENAMED,
            "C": GitFileChangeStatus.COPIED,
            "U": GitFileChangeStatus.UNMERGED,
            "?": GitFileChangeStatus.UNTRACKED,
        }
        return mapping.get(token, GitFileChangeStatus.UNKNOWN)

    def _sanitize_label(self, value: str) -> str:
        pieces = ["-".join(value.strip().lower().split())]
        sanitized = "".join(pieces).strip("-")
        return sanitized or "checkpoint"

    def _git(self, repository_root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return (result.stdout + result.stderr).strip()

    def _git_optional(self, repository_root: Path, *args: str) -> str | None:
        result = subprocess.run(
            ["git", *args],
            cwd=repository_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        return (result.stdout + result.stderr).strip()
