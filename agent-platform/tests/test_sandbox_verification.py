from __future__ import annotations

import os
import subprocess
from pathlib import Path

from sandbox.runner import LocalSandboxRunner, SandboxCommandSet


def test_local_sandbox_runner_reproduces_applies_patch_and_verifies(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    target_file = repo_root / "app.py"
    target_file.write_text("VALUE = 'old'\n", encoding="utf-8")

    env = {
        "GIT_AUTHOR_NAME": "Cursor Test",
        "GIT_AUTHOR_EMAIL": "cursor@example.com",
        "GIT_COMMITTER_NAME": "Cursor Test",
        "GIT_COMMITTER_EMAIL": "cursor@example.com",
    }
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial app state"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **env},
    )

    target_file.write_text("VALUE = 'new'\n", encoding="utf-8")
    patch_diff = subprocess.run(
        ["git", "diff", "--", "app.py"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    target_file.write_text("VALUE = 'old'\n", encoding="utf-8")
    runner = LocalSandboxRunner()
    result = runner.run(
        repository_root=repo_root,
        patch_diff=patch_diff,
        commands=SandboxCommandSet(
            install_command=None,
            reproduce_command="python3 -c \"from pathlib import Path; import sys; sys.exit(0 if \\\"old\\\" in Path('app.py').read_text() else 1)\"",
            verify_command="python3 -c \"from pathlib import Path; import sys; sys.exit(0 if \\\"new\\\" in Path('app.py').read_text() else 1)\"",
            timeout_seconds=30,
        ),
        incident_id="incident-1",
        patch_run_id="patch-1",
    )

    assert result.reproduction_succeeded is True
    assert result.patch_applied is True
    assert result.verification_succeeded is True
    assert "verified the candidate fix" in result.summary
