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
            completed = subprocess.run(
                request.command,
                cwd=working_directory,
                shell=True,
                capture_output=True,
                text=True,
                timeout=request.timeout_seconds,
                env={**os.environ, **request.env},
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

        stdout = self._truncate(completed.stdout)
        stderr = self._truncate(completed.stderr)
        ok = completed.returncode == 0
        return RunCommandResponse(
            ok=ok,
            command=request.command,
            working_directory=str(working_directory),
            exit_code=completed.returncode,
            timed_out=False,
            stdout=stdout,
            stderr=stderr,
            output=self._build_output(stdout, stderr),
            message=(
                "Command completed successfully."
                if ok
                else f"Command exited with status {completed.returncode}."
            ),
        )

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
