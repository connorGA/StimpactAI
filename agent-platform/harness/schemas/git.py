from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class GitAction(StrEnum):
    CURRENT_BRANCH_INFO = "current_branch_info"
    CHECKPOINT = "checkpoint"
    REVERT_TO_CHECKPOINT = "revert_to_checkpoint"
    RESET_FAILED_ATTEMPT = "reset_failed_attempt"
    DISCARD_FAILED_WORK = "discard_failed_work"
    DIFF_SINCE_CHECKPOINT = "diff_since_checkpoint"


class GitCurrentBranchInfoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GitCheckpointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=128)


class GitCheckpointRefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_ref: str | None = Field(default=None, max_length=256)


class GitFileChangeStatus(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    COPIED = "copied"
    UNMERGED = "unmerged"
    UNTRACKED = "untracked"
    UNKNOWN = "unknown"


class GitCheckpointRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commit_sha: str = Field(min_length=1, max_length=128)
    tag_name: str = Field(min_length=1, max_length=256)
    branch_name: str = Field(min_length=1, max_length=256)
    created_at: datetime


class GitBranchInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_name: str = Field(min_length=1, max_length=256)
    upstream_branch: str | None = Field(default=None, max_length=256)
    head_sha: str = Field(min_length=1, max_length=128)
    is_dirty: bool
    has_staged_changes: bool
    has_unstaged_changes: bool
    has_untracked_files: bool
    staged_files: list[str] = Field(default_factory=list)
    unstaged_files: list[str] = Field(default_factory=list)
    untracked_files: list[str] = Field(default_factory=list)


class GitChangedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=4096)
    status: GitFileChangeStatus
    previous_path: str | None = Field(default=None, max_length=4096)


class GitDiffInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_ref: str = Field(min_length=1, max_length=256)
    changed_files: list[GitChangedFile] = Field(default_factory=list)
    patch: str = ""


class GitActionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    action: GitAction
    target_ref: str | None = None
    branch_name: str | None = None
    output: str = ""
    checkpoint: GitCheckpointRecord | None = None
    branch_info: GitBranchInfo | None = None
    diff: GitDiffInspection | None = None
