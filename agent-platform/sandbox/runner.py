from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Protocol


@dataclass(slots=True)
class SandboxCommandSet:
    install_command: str | None
    reproduce_command: str
    verify_command: str
    timeout_seconds: int


@dataclass(slots=True)
class SandboxExecutionResult:
    reproduction_succeeded: bool
    patch_applied: bool
    verification_succeeded: bool
    summary: str
    execution_log: str


@dataclass(slots=True)
class SecretBindingRef:
    mount_as: str
    external_ref: str


class SecretValueResolver(Protocol):
    def get_secret(self, *, external_ref: str) -> str: ...


@dataclass(slots=True)
class _PreparedSecrets:
    env_loader_path: str | None
    secret_values: list[str]
    log_text: str | None


class LocalSandboxRunner:
    _PASSTHROUGH_ENV_VARS = {
        "HOME",
        "LANG",
        "LC_ALL",
        "PATH",
        "SHELL",
        "SYSTEMROOT",
        "TEMP",
        "TERM",
        "TMP",
        "TMPDIR",
    }

    def run(
        self,
        *,
        repository_root: Path,
        patch_diff: str,
        commands: SandboxCommandSet,
        incident_id: str,
        patch_run_id: str,
        baseline_ref: str | None = None,
        secret_env: dict[str, str] | None = None,
        secret_files: dict[str, str] | None = None,
        secret_bindings: list[SecretBindingRef] | None = None,
        secrets_reader: SecretValueResolver | None = None,
    ) -> SandboxExecutionResult:
        if not repository_root.exists():
            return SandboxExecutionResult(
                reproduction_succeeded=False,
                patch_applied=False,
                verification_succeeded=False,
                summary="Repository root does not exist for sandbox execution.",
                execution_log=f"Missing repository root: {repository_root}",
            )

        with tempfile.TemporaryDirectory(prefix="stimpact-sandbox-") as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            clone_log = self._prepare_workspace(repository_root=repository_root, workspace=workspace)
            logs = [clone_log]
            if baseline_ref:
                checkout_result = self._checkout_baseline(
                    workspace=workspace,
                    baseline_ref=baseline_ref,
                    timeout_seconds=commands.timeout_seconds,
                )
                logs.append(checkout_result.log_text)
                if checkout_result.returncode != 0:
                    return SandboxExecutionResult(
                        reproduction_succeeded=False,
                        patch_applied=False,
                        verification_succeeded=False,
                        summary="Sandbox failed to restore the requested baseline before verification.",
                        execution_log="\n\n".join(logs),
                    )
            materialized_secret_files = self._materialize_secret_files(
                workspace=workspace,
                secret_files=secret_files or {},
            )
            if materialized_secret_files:
                logs.append(materialized_secret_files)
            prepared_secrets = self._prepare_secret_bindings(
                workspace=workspace,
                secret_bindings=secret_bindings or [],
                secrets_reader=secrets_reader,
            )
            if prepared_secrets.log_text:
                logs.append(prepared_secrets.log_text)
            redacted_secret_values = [
                *(secret_env.values() if secret_env else []),
                *prepared_secrets.secret_values,
            ]

            if commands.install_command:
                install_result = self._run_shell_command(
                    command=commands.install_command,
                    workspace=workspace,
                    timeout_seconds=commands.timeout_seconds,
                    incident_id=incident_id,
                    patch_run_id=patch_run_id,
                    step_name="install",
                    secret_env=secret_env,
                    env_loader_path=prepared_secrets.env_loader_path,
                    secret_values=redacted_secret_values,
                )
                logs.append(install_result.log_text)
                if install_result.returncode != 0:
                    return SandboxExecutionResult(
                        reproduction_succeeded=False,
                        patch_applied=False,
                        verification_succeeded=False,
                        summary="Sandbox install step failed before reproduction.",
                        execution_log="\n\n".join(logs),
                    )

            reproduce_result = self._run_shell_command(
                command=commands.reproduce_command,
                workspace=workspace,
                timeout_seconds=commands.timeout_seconds,
                incident_id=incident_id,
                patch_run_id=patch_run_id,
                step_name="reproduce",
                secret_env=secret_env,
                env_loader_path=prepared_secrets.env_loader_path,
                secret_values=redacted_secret_values,
            )
            logs.append(reproduce_result.log_text)
            reproduction_observed = self._reproduction_step_succeeded(reproduce_result)
            if not reproduction_observed:
                return SandboxExecutionResult(
                    reproduction_succeeded=False,
                    patch_applied=False,
                    verification_succeeded=False,
                    summary="Sandbox could not reproduce the original failure before applying the patch.",
                    execution_log="\n\n".join(logs),
                )

            apply_result = self._apply_patch(
                workspace=workspace,
                patch_diff=patch_diff,
                timeout_seconds=commands.timeout_seconds,
            )
            logs.append(apply_result.log_text)
            if apply_result.returncode != 0:
                return SandboxExecutionResult(
                    reproduction_succeeded=reproduction_observed,
                    patch_applied=False,
                    verification_succeeded=False,
                    summary="Sandbox reproduced the incident but failed to apply the generated patch.",
                    execution_log="\n\n".join(logs),
                )

            verify_result = self._run_shell_command(
                command=commands.verify_command,
                workspace=workspace,
                timeout_seconds=commands.timeout_seconds,
                incident_id=incident_id,
                patch_run_id=patch_run_id,
                step_name="verify",
                secret_env=secret_env,
                env_loader_path=prepared_secrets.env_loader_path,
                secret_values=redacted_secret_values,
            )
            logs.append(verify_result.log_text)
            if verify_result.returncode != 0:
                return SandboxExecutionResult(
                    reproduction_succeeded=reproduction_observed,
                    patch_applied=True,
                    verification_succeeded=False,
                    summary="Sandbox reproduced the incident and applied the patch, but verification failed.",
                    execution_log="\n\n".join(logs),
                )

            return SandboxExecutionResult(
                reproduction_succeeded=reproduction_observed,
                patch_applied=True,
                verification_succeeded=True,
                summary="Sandbox reproduced the incident, applied the patch, and verified the candidate fix.",
                execution_log="\n\n".join(logs),
            )

    def _reproduction_step_succeeded(self, result: "_CommandResult") -> bool:
        if result.returncode == 0:
            return True
        # Treat normal non-zero test failures as successful reproduction,
        # but keep shell/env failures and timeouts as hard sandbox errors.
        return result.returncode not in {124, 126, 127}

    def _checkout_baseline(
        self,
        *,
        workspace: Path,
        baseline_ref: str,
        timeout_seconds: int,
    ) -> "_CommandResult":
        return self._run_subprocess(
            ["/bin/sh", "-lc", f"git checkout --quiet {baseline_ref}"],
            workspace=workspace,
            timeout_seconds=timeout_seconds,
            step_name="checkout-baseline",
        )

    def _prepare_workspace(self, *, repository_root: Path, workspace: Path) -> str:
        if _is_git_repo(repository_root):
            result = subprocess.run(
                ["git", "clone", "--quiet", "--no-local", str(repository_root), str(workspace)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return _format_log(
                    step_name="clone",
                    command=f"git clone --quiet --no-local {repository_root} {workspace}",
                    returncode=result.returncode,
                    elapsed_ms=0,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )

        shutil.copytree(
            repository_root,
            workspace,
            ignore=shutil.ignore_patterns(
                ".git",
                ".next",
                "node_modules",
                "__pycache__",
                ".venv",
                ".pytest_cache",
            ),
        )
        return _format_log(
            step_name="clone",
            command=f"copytree {repository_root} -> {workspace}",
            returncode=0,
            elapsed_ms=0,
            stdout="Workspace copied without git metadata.",
            stderr="",
        )

    def _apply_patch(
        self,
        *,
        workspace: Path,
        patch_diff: str,
        timeout_seconds: int,
    ) -> "_CommandResult":
        patch_path = workspace / "stimpact.patch"
        patch_path.write_text(patch_diff, encoding="utf-8")
        check_result = self._run_subprocess(
            ["/bin/sh", "-lc", f"git apply --check {patch_path.name}"],
            workspace=workspace,
            timeout_seconds=timeout_seconds,
            step_name="patch-check",
        )
        if check_result.returncode != 0:
            return check_result
        return self._run_subprocess(
            ["/bin/sh", "-lc", f"git apply {patch_path.name}"],
            workspace=workspace,
            timeout_seconds=timeout_seconds,
            step_name="patch-apply",
        )

    def _materialize_secret_files(self, *, workspace: Path, secret_files: dict[str, str]) -> str | None:
        if not secret_files:
            return None
        written_paths: list[str] = []
        for mount_as, value in secret_files.items():
            target = Path(mount_as)
            if target.is_absolute():
                raise ValueError("Absolute secret file mounts are not supported for local sandbox execution.")
            destination = workspace / target
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(value, encoding="utf-8")
            written_paths.append(str(target))
        return _format_log(
            step_name="secret-materialize",
            command="materialize secret files",
            returncode=0,
            elapsed_ms=0,
            stdout="\n".join(f"wrote {path}" for path in written_paths),
            stderr="",
        )

    def _prepare_secret_bindings(
        self,
        *,
        workspace: Path,
        secret_bindings: list[SecretBindingRef],
        secrets_reader: SecretValueResolver | None,
    ) -> _PreparedSecrets:
        if not secret_bindings:
            return _PreparedSecrets(env_loader_path=None, secret_values=[], log_text=None)
        if secrets_reader is None:
            raise ValueError("A secrets reader is required when secret bindings are provided.")

        secret_root = workspace / ".stimpact" / "secrets"
        env_dir = secret_root / "env"
        env_dir.mkdir(parents=True, exist_ok=True)
        loader_path = secret_root / "export_env.sh"
        secret_values: list[str] = []
        written_paths: list[str] = []
        env_exports: list[str] = ["#!/bin/sh", "set -eu"]

        for binding in secret_bindings:
            value = secrets_reader.get_secret(external_ref=binding.external_ref)
            secret_values.append(value)
            if "/" in binding.mount_as:
                target = Path(binding.mount_as)
                if target.is_absolute():
                    raise ValueError("Absolute secret file mounts are not supported for local sandbox execution.")
                destination = workspace / target
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(value, encoding="utf-8")
                written_paths.append(str(target))
                continue

            env_file = env_dir / binding.mount_as
            env_file.write_text(value, encoding="utf-8")
            env_exports.append(
                f"export {binding.mount_as}={_shell_quote(env_file.read_text(encoding='utf-8'))}"
            )
            written_paths.append(binding.mount_as)

        loader_path.write_text("\n".join(env_exports) + "\n", encoding="utf-8")
        return _PreparedSecrets(
            env_loader_path=str(loader_path.relative_to(workspace)),
            secret_values=secret_values,
            log_text=_format_log(
                step_name="secret-materialize",
                command="resolve secret bindings",
                returncode=0,
                elapsed_ms=0,
                stdout="\n".join(f"prepared {path}" for path in written_paths),
                stderr="",
            ),
        )

    def _run_shell_command(
        self,
        *,
        command: str,
        workspace: Path,
        timeout_seconds: int,
        incident_id: str,
        patch_run_id: str,
        step_name: str,
        secret_env: dict[str, str] | None = None,
        env_loader_path: str | None = None,
        secret_values: list[str] | None = None,
    ) -> "_CommandResult":
        env = {
            **{
                key: value
                for key, value in os.environ.items()
                if key in self._PASSTHROUGH_ENV_VARS
            },
            "STIMPACT_INCIDENT_ID": incident_id,
            "STIMPACT_PATCH_RUN_ID": patch_run_id,
            "STIMPACT_SANDBOX_WORKSPACE": str(workspace),
        }
        if secret_env:
            env.update(secret_env)
        effective_command = command
        if env_loader_path:
            quoted_loader = shlex.quote(env_loader_path)
            effective_command = f". {quoted_loader}; {command}"
        return self._run_subprocess(
            ["/bin/sh", "-lc", effective_command],
            workspace=workspace,
            timeout_seconds=timeout_seconds,
            step_name=step_name,
            env=env,
            command_override=effective_command,
            secret_values=secret_values if secret_values is not None else list(secret_env.values()) if secret_env else None,
        )

    def _run_subprocess(
        self,
        args: list[str],
        *,
        workspace: Path,
        timeout_seconds: int,
        step_name: str,
        env: dict[str, str] | None = None,
        command_override: str | None = None,
        secret_values: list[str] | None = None,
    ) -> "_CommandResult":
        started = monotonic()
        try:
            completed = subprocess.run(
                args,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                env=env,
            )
            elapsed_ms = int((monotonic() - started) * 1000)
            return _CommandResult(
                returncode=completed.returncode,
                log_text=_format_log(
                    step_name=step_name,
                    command=command_override or " ".join(args),
                    returncode=completed.returncode,
                    elapsed_ms=elapsed_ms,
                    stdout=_redact_log_text(completed.stdout, secret_values),
                    stderr=_redact_log_text(completed.stderr, secret_values),
                ),
            )
        except subprocess.TimeoutExpired as exc:
            elapsed_ms = int((monotonic() - started) * 1000)
            return _CommandResult(
                returncode=124,
                log_text=_format_log(
                    step_name=step_name,
                    command=command_override or " ".join(args),
                    returncode=124,
                    elapsed_ms=elapsed_ms,
                    stdout=_redact_log_text(exc.stdout or "", secret_values),
                    stderr=_redact_log_text((exc.stderr or "") + "\nCommand timed out.", secret_values),
                ),
            )


@dataclass(slots=True)
class _CommandResult:
    returncode: int
    log_text: str


def _is_git_repo(path: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _format_log(
    *,
    step_name: str,
    command: str,
    returncode: int,
    elapsed_ms: int,
    stdout: str,
    stderr: str,
) -> str:
    return (
        f"[{step_name}]\n"
        f"command: {command}\n"
        f"exit_code: {returncode}\n"
        f"elapsed_ms: {elapsed_ms}\n"
        f"stdout:\n{stdout.strip()}\n"
        f"stderr:\n{stderr.strip()}"
    )


def _redact_log_text(value: str, secret_values: list[str] | None = None) -> str:
    redacted = value
    for token in ("ghp_", "glpat-", "AKIA", "ASIA"):
        if token in redacted:
            redacted = redacted.replace(token, f"{token[:2]}[redacted]")
    for secret in sorted((item for item in (secret_values or []) if item), key=len, reverse=True):
        if len(secret) >= 4 and secret in redacted:
            redacted = redacted.replace(secret, "[redacted-secret]")
    return redacted


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
