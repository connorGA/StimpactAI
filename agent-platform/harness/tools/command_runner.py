from __future__ import annotations

import os
import subprocess
from pathlib import Path

from harness.schemas.commands import RunCommandRequest, RunCommandResponse


class CommandRunner:
    _MAX_OUTPUT_CHARS = 20_000

    def __init__(self, *, repository_root: str) -> None:
        self._repository_root = Path(repository_root).expanduser().resolve()

    def run(self, request: RunCommandRequest) -> RunCommandResponse:
        working_directory = self._resolve_working_directory(request.working_directory)
        if working_directory is None:
            candidate = request.working_directory or str(self._repository_root)
            return RunCommandResponse(
                ok=False,
                command=request.command,
                working_directory=str(self._repository_root),
                exit_code=None,
                timed_out=False,
                stdout="",
                stderr="",
                output="",
                message=(
                    f"Working directory must stay inside the repository root: {candidate}"
                ),
            )

        try:
            completed = self._run_subprocess(
                command=request.command,
                working_directory=working_directory,
                timeout_seconds=request.timeout_seconds,
                env=request.env,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = self._truncate(exc.stdout or "")
            stderr = self._truncate(exc.stderr or "")
            return RunCommandResponse(
                ok=False,
                command=request.command,
                working_directory=str(working_directory),
                exit_code=None,
                timed_out=True,
                stdout=stdout,
                stderr=stderr,
                output=self._build_output(stdout, stderr),
                message=f"Command timed out after {request.timeout_seconds} seconds.",
            )

        fallback_note = None
        if self._should_retry_with_python3(request.command, completed):
            retried_command = self._rewrite_python_command(request.command)
            try:
                retried = self._run_subprocess(
                    command=retried_command,
                    working_directory=working_directory,
                    timeout_seconds=request.timeout_seconds,
                    env=request.env,
                )
            except subprocess.TimeoutExpired as exc:
                stdout = self._truncate(exc.stdout or "")
                stderr = self._truncate(exc.stderr or "")
                return RunCommandResponse(
                    ok=False,
                    command=request.command,
                    working_directory=str(working_directory),
                    exit_code=None,
                    timed_out=True,
                    stdout=stdout,
                    stderr=stderr,
                    output=self._build_output(stdout, stderr),
                    message=f"Command timed out after retrying with python3 for {request.timeout_seconds} seconds.",
                )
            completed = retried
            fallback_note = "Retried command with python3 after `python` was not available on PATH."

        stdout = self._truncate(completed.stdout)
        stderr = self._truncate(completed.stderr)
        ok = completed.returncode == 0
        output = self._build_output(stdout, stderr)
        if fallback_note:
            output = self._truncate(f"{fallback_note}\n\n{output}")
        return RunCommandResponse(
            ok=ok,
            command=request.command,
            working_directory=str(working_directory),
            exit_code=completed.returncode,
            timed_out=False,
            stdout=stdout,
            stderr=stderr,
            output=output,
            message=(
                "Command completed successfully."
                if ok
                else f"Command exited with status {completed.returncode}."
            ),
        )

    def _run_subprocess(
        self,
        *,
        command: str,
        working_directory: Path,
        timeout_seconds: int,
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=working_directory,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env={**os.environ, **env},
        )

    def _should_retry_with_python3(
        self,
        command: str,
        completed: subprocess.CompletedProcess[str],
    ) -> bool:
        normalized = command.lstrip()
        if not normalized.startswith("python "):
            return False
        if completed.returncode != 127:
            return False
        stderr = (completed.stderr or "").lower()
        return "python: command not found" in stderr

    def _rewrite_python_command(self, command: str) -> str:
        stripped = command.lstrip()
        prefix_len = len(command) - len(stripped)
        return f"{command[:prefix_len]}python3 {stripped.removeprefix('python ')}"

    def _resolve_working_directory(self, working_directory: str | None) -> Path | None:
        candidate = self._repository_root if working_directory is None else Path(working_directory).expanduser().resolve()
        try:
            candidate.relative_to(self._repository_root)
        except ValueError:
            return None
        return candidate

    def _build_output(self, stdout: str, stderr: str) -> str:
        sections: list[str] = []
        if stdout.strip():
            sections.append(f"stdout:\n{stdout.strip()}")
        if stderr.strip():
            sections.append(f"stderr:\n{stderr.strip()}")
        if not sections:
            return "Command produced no output."
        return self._truncate("\n\n".join(sections))

    def _truncate(self, value: str) -> str:
        if len(value) <= self._MAX_OUTPUT_CHARS:
            return value
        return f"{value[: self._MAX_OUTPUT_CHARS - 3]}..."
