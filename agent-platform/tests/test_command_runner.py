from __future__ import annotations

import subprocess
from pathlib import Path

from harness.schemas.commands import RunCommandRequest
from harness.tools.command_runner import CommandRunner


def test_command_runner_retries_python_with_python3(monkeypatch, tmp_path: Path) -> None:
    runner = CommandRunner(repository_root=str(tmp_path))
    calls: list[str] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command == "python -m pytest test_buggy_retry.py -q":
            return subprocess.CompletedProcess(
                command,
                127,
                stdout="",
                stderr="/bin/sh: python: command not found\n",
            )
        if command == "python3 -m pytest test_buggy_retry.py -q":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="1 passed in 0.01s\n",
                stderr="",
            )
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr("harness.tools.command_runner.subprocess.run", fake_run)

    result = runner.run(
        RunCommandRequest(
            command="python -m pytest test_buggy_retry.py -q",
            working_directory=str(tmp_path),
        )
    )

    assert result.ok is True
    assert result.exit_code == 0
    assert result.command == "python -m pytest test_buggy_retry.py -q"
    assert "Retried command with python3" in result.output
    assert result.stdout == "1 passed in 0.01s\n"
    assert calls == [
        "python -m pytest test_buggy_retry.py -q",
        "python3 -m pytest test_buggy_retry.py -q",
    ]
