from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import socket
import subprocess
from urllib.parse import urlparse

from api.core.config import (
    get_aws_region,
    get_repository_root,
    get_sandbox_execution_backend,
    get_sandbox_timeout_seconds,
)
from api.core.errors import APIError
from api.repositories.artifact_repository import ArtifactRepository
from api.repositories.async_job_repository import AsyncJobRepository
from api.repositories.control_plane_repository import ControlPlaneRepository
from api.repositories.incident_repository import IncidentRepository
from api.repositories.patch_repository import PatchRepository
from api.repositories.sandbox_repository import SandboxRepository
from models.artifact import ArtifactStorageBackend, ArtifactType
from models.async_job import AsyncJobRecord, AsyncJobType
from models.control_plane import ProjectServiceRecord, RepoProfileRecord, RepoProfileSecretBindingRecord
from models.patch import PatchRunRecord
from models.sandbox import SandboxRunRecord, SandboxRunStatus
from sandbox.kubernetes_runner import (
    DEFAULT_SANDBOX_REQUEST_CPU_CORES,
    DEFAULT_SANDBOX_REQUEST_MEMORY_GIB,
    KubernetesJobMonitor,
    KubernetesSandboxRunner,
)
from sandbox.runner import LocalSandboxRunner, SandboxCommandSet, SecretBindingRef
from services.artifact_storage import ArtifactStorage, S3ArtifactStorage
from services.aws_secrets_manager import AwsSecretsManagerReader, AwsSecretsManagerWriter, SecretsReader
from services.patch_generation import PatchGenerationService
from services.provider_integration_service import ProviderIntegrationService
from services.repository_provider import get_provider_adapter


@dataclass(slots=True)
class ResolvedSandboxServiceContext:
    incident_id: str
    project_service: ProjectServiceRecord | None
    repo_profile: RepoProfileRecord
    dependency_services: list[ProjectServiceRecord]


@dataclass(slots=True)
class SandboxExecutionMetrics:
    backend: str
    queue_wait_seconds: float
    total_elapsed_seconds: float
    execution_window_seconds: float | None = None
    estimated_requested_vcpu_seconds: float | None = None
    estimated_requested_memory_gib_seconds: float | None = None


class SandboxVerificationService:
    def __init__(
        self,
        incident_repository: IncidentRepository,
        sandbox_repository: SandboxRepository,
        *,
        control_plane_repository: ControlPlaneRepository,
        async_job_repository: AsyncJobRepository,
        artifact_repository: ArtifactRepository,
        patch_repository: PatchRepository,
        patch_generation: PatchGenerationService,
        local_runner: LocalSandboxRunner | None = None,
        kubernetes_runner: KubernetesSandboxRunner | None = None,
        kubernetes_monitor: KubernetesJobMonitor | None = None,
        artifact_storage: ArtifactStorage | None = None,
        provider_integration_service: ProviderIntegrationService | None = None,
        secrets_reader: SecretsReader | None = None,
        runner: LocalSandboxRunner | None = None,
        repository_root: Path | None = None,
    ) -> None:
        self._incident_repository = incident_repository
        self._sandbox_repository = sandbox_repository
        self._control_plane_repository = control_plane_repository
        self._async_job_repository = async_job_repository
        self._artifact_repository = artifact_repository
        self._patch_repository = patch_repository
        self._patch_generation = patch_generation
        self._local_runner = local_runner or runner or LocalSandboxRunner()
        self._kubernetes_runner = kubernetes_runner or KubernetesSandboxRunner()
        self._kubernetes_monitor = kubernetes_monitor or KubernetesJobMonitor()
        self._artifact_storage = artifact_storage or S3ArtifactStorage()
        self._repository_root = repository_root or get_repository_root()
        self._secrets_reader = secrets_reader or AwsSecretsManagerReader()
        self._provider_integration_service = provider_integration_service or ProviderIntegrationService(
            control_plane_repository,
            secrets_writer=AwsSecretsManagerWriter(),
            secrets_reader=self._secrets_reader,
        )

    async def get_latest_run(self, incident_id: str) -> SandboxRunRecord | None:
        incident = await self._incident_repository.get_incident(incident_id)
        if incident is None:
            raise APIError(
                f"Incident {incident_id} was not found.",
                status_code=404,
                code="incident_not_found",
            )
        return await self._sandbox_repository.get_latest_sandbox_run(incident_id)

    async def list_runs(self, incident_id: str, *, limit: int = 20) -> list[SandboxRunRecord]:
        incident = await self._incident_repository.get_incident(incident_id)
        if incident is None:
            raise APIError(
                f"Incident {incident_id} was not found.",
                status_code=404,
                code="incident_not_found",
            )
        return await self._sandbox_repository.list_sandbox_runs(incident_id, limit=limit)

    async def get_run(self, incident_id: str, sandbox_run_id: str) -> SandboxRunRecord:
        incident = await self._incident_repository.get_incident(incident_id)
        if incident is None:
            raise APIError(
                f"Incident {incident_id} was not found.",
                status_code=404,
                code="incident_not_found",
            )
        run = await self._sandbox_repository.get_sandbox_run(sandbox_run_id)
        if run is None or run.incident_id != incident.id:
            raise APIError(
                f"Sandbox run {sandbox_run_id} was not found for incident {incident_id}.",
                status_code=404,
                code="sandbox_run_not_found",
            )
        return run

    async def queue_sandbox_run(
        self,
        incident_id: str,
        *,
        event_limit: int = 50,
        refresh_patch: bool = False,
        patch_run_id: str | None = None,
        repository_root: str | None = None,
        baseline_commit_sha: str | None = None,
        repository_branch: str | None = None,
        repository_upstream_branch: str | None = None,
    ) -> tuple[SandboxRunRecord, AsyncJobRecord]:
        incident = await self._incident_repository.get_incident(incident_id)
        if incident is None:
            raise APIError(
                f"Incident {incident_id} was not found.",
                status_code=404,
                code="incident_not_found",
            )

        service_context = await self._resolve_service_context(incident)
        patch_run = await self._resolve_patch_run(
            incident_id=incident_id,
            patch_run_id=patch_run_id,
            refresh_patch=refresh_patch,
            event_limit=event_limit,
        )
        backend = self._resolve_executor_backend()

        job = await self._async_job_repository.create_job(
            job_type=AsyncJobType.SANDBOX_RUN,
            payload={
                "incident_id": incident.id,
                "patch_run_id": patch_run.id,
                "project_service_id": service_context.project_service.id
                if service_context.project_service is not None
                else None,
                "repo_profile_id": service_context.repo_profile.id,
                "dependency_service_ids": [service.id for service in service_context.dependency_services],
                "event_limit": event_limit,
                "refresh_patch": refresh_patch,
                "repository_root": repository_root or str(self._repository_root),
                "baseline_commit_sha": baseline_commit_sha or patch_run.based_on_commit_sha,
                "repository_branch": repository_branch,
                "repository_upstream_branch": repository_upstream_branch,
                "executor_backend": backend,
            },
            dedupe_key=f"sandbox:{incident.id}:{patch_run.id}",
        )
        sandbox_run = await self._sandbox_repository.create_sandbox_run(
            incident_id=incident.id,
            patch_run_id=patch_run.id,
            project_service_id=service_context.project_service.id
            if service_context.project_service is not None
            else None,
            repo_profile_id=service_context.repo_profile.id,
            dependency_service_ids=[service.id for service in service_context.dependency_services],
            async_job_id=job.id,
            status=SandboxRunStatus.QUEUED,
            executor_backend=backend,
            install_command=service_context.repo_profile.install_command,
            reproduce_command=service_context.repo_profile.reproduce_command,
            verify_command=service_context.repo_profile.verify_command,
            reproduction_succeeded=False,
            patch_applied=False,
            verification_succeeded=False,
            summary=f"Sandbox run queued for asynchronous execution on the {backend} backend.",
            execution_log="",
        )
        await self._sandbox_repository.create_sandbox_run_step(
            sandbox_run_id=sandbox_run.id,
            step_name="queue",
            status=SandboxRunStatus.QUEUED,
            command=None,
            summary=f"Sandbox run was queued for the {backend} backend.",
            artifact_id=None,
            exit_code=None,
            finished=True,
        )
        if service_context.project_service is not None:
            dependency_summary = (
                ", ".join(service.slug for service in service_context.dependency_services)
                if service_context.dependency_services
                else "none"
            )
            await self._sandbox_repository.create_sandbox_run_step(
                sandbox_run_id=sandbox_run.id,
                step_name="dependency-plan",
                status=SandboxRunStatus.QUEUED,
                command=None,
                summary=(
                    f"Target service {service_context.project_service.slug}; "
                    f"declared dependencies: {dependency_summary}."
                ),
                artifact_id=None,
                exit_code=None,
                finished=True,
            )
        return sandbox_run, job

    async def process_async_job(self, job: AsyncJobRecord) -> SandboxRunRecord:
        if job.job_type is not AsyncJobType.SANDBOX_RUN:
            raise APIError(
                f"Unsupported async job type {job.job_type.value}.",
                code="unsupported_async_job",
            )

        incident_id = str(job.payload["incident_id"])
        sandbox_run = await self._find_run_by_async_job(job.id, incident_id)
        if sandbox_run is None:
            raise APIError(
                f"No sandbox run is linked to async job {job.id}.",
                code="sandbox_run_not_found",
            )

        patch_run = await self._resolve_patch_run(
            incident_id=incident_id,
            patch_run_id=str(job.payload["patch_run_id"]) if job.payload.get("patch_run_id") is not None else None,
            refresh_patch=bool(job.payload.get("refresh_patch", False)),
            event_limit=int(job.payload.get("event_limit", 50)),
        )
        repo_profile = await self._require_repo_profile(str(job.payload["repo_profile_id"]))
        project_service = (
            await self._control_plane_repository.get_project_service(str(job.payload["project_service_id"]))
            if job.payload.get("project_service_id") is not None
            else None
        )
        await self._sandbox_repository.update_sandbox_run(
            sandbox_run.id,
            status=SandboxRunStatus.RUNNING,
            summary=f"Sandbox run is starting execution on the {sandbox_run.executor_backend} backend.",
        )
        run_attempt = await self._sandbox_repository.create_sandbox_run_attempt(
            sandbox_run_id=sandbox_run.id,
            async_job_id=job.id,
            attempt_number=job.attempts,
            status=SandboxRunStatus.RUNNING,
            error_message=None,
            finished=False,
        )
        await self._record_queue_metrics_step(
            sandbox_run=sandbox_run,
            backend=sandbox_run.executor_backend,
            started_at=run_attempt.started_at,
        )
        await self._sandbox_repository.create_sandbox_run_step(
            sandbox_run_id=sandbox_run.id,
            step_name="resolve-profile",
            status=SandboxRunStatus.RUNNING,
            command=None,
            summary=(
                f"Resolved service {project_service.slug} and its repo profile for {sandbox_run.executor_backend} execution."
                if project_service is not None
                else f"Resolved repo profile and confirmed the {sandbox_run.executor_backend} execution backend."
            ),
            artifact_id=None,
            exit_code=None,
            finished=True,
        )

        backend = self._resolve_executor_backend(
            job_backend=str(job.payload.get("executor_backend") or ""),
            run_backend=sandbox_run.executor_backend,
        )
        if backend == "kubernetes":
            return await self._submit_kubernetes_run(
                sandbox_run=sandbox_run,
                patch_run=patch_run,
                repo_profile=repo_profile,
                repository_root=Path(str(job.payload.get("repository_root") or self._repository_root)),
                repository_branch=(
                    str(job.payload["repository_branch"]) if job.payload.get("repository_branch") is not None else None
                ),
                repository_upstream_branch=(
                    str(job.payload["repository_upstream_branch"])
                    if job.payload.get("repository_upstream_branch") is not None
                    else None
                ),
            )
        return await self._execute_local_run(
            sandbox_run=sandbox_run,
            patch_diff=patch_run.unified_diff,
            repo_profile=repo_profile,
            repository_root=Path(str(job.payload.get("repository_root") or self._repository_root)),
            baseline_commit_sha=str(job.payload["baseline_commit_sha"])
            if job.payload.get("baseline_commit_sha") is not None
            else None,
            attempt_started_at=run_attempt.started_at,
        )

    async def poll_kubernetes_runs(self, *, limit: int = 50) -> list[SandboxRunRecord]:
        runs = await self._sandbox_repository.list_active_kubernetes_runs(limit=limit)
        updated_runs: list[SandboxRunRecord] = []
        for run in runs:
            if run.external_job_id is None:
                continue
            status = self._kubernetes_monitor.poll_status(external_job_id=run.external_job_id)
            if status.status == "running":
                updated_runs.append(run)
                continue
            terminal_status = (
                SandboxRunStatus.SUCCEEDED if status.status == "succeeded" else SandboxRunStatus.FAILED
            )
            artifact_id = None
            if status.execution_log:
                artifact_id = await self._store_log_artifact(
                    incident_id=run.incident_id,
                    patch_run_id=run.patch_run_id,
                    sandbox_run_id=run.id,
                    object_key=f"sandbox-runs/{run.id}/kubernetes-execution.log",
                    content=status.execution_log,
                    content_type="text/plain",
                    artifact_type=ArtifactType.EXECUTION_LOG,
                )
            await self._sandbox_repository.create_sandbox_run_step(
                sandbox_run_id=run.id,
                step_name="monitor-kubernetes-job",
                status=terminal_status,
                command="kubernetes job monitor",
                summary=status.summary,
                artifact_id=artifact_id,
                exit_code=0 if terminal_status is SandboxRunStatus.SUCCEEDED else 1,
                finished=True,
            )
            attempts = await self._sandbox_repository.list_sandbox_run_attempts(run.id)
            latest_attempt = attempts[-1] if attempts else None
            await self._record_execution_metrics_step(
                sandbox_run=run,
                backend=run.executor_backend,
                finished_at=self._utcnow(),
                attempt_started_at=latest_attempt.started_at if latest_attempt is not None else None,
                status=terminal_status,
            )
            updated_runs.append(
                await self._sandbox_repository.update_sandbox_run(
                    run.id,
                    status=terminal_status,
                    reproduction_succeeded=status.reproduction_succeeded,
                    patch_applied=status.patch_applied,
                    verification_succeeded=status.verification_succeeded,
                    summary=status.summary,
                    execution_log=status.execution_log or run.execution_log,
                )
            )
        return updated_runs

    async def _execute_local_run(
        self,
        *,
        sandbox_run: SandboxRunRecord,
        patch_diff: str,
        repo_profile: RepoProfileRecord,
        repository_root: Path,
        baseline_commit_sha: str | None,
        attempt_started_at: datetime,
    ) -> SandboxRunRecord:
        commands = SandboxCommandSet(
            install_command=repo_profile.install_command,
            reproduce_command=repo_profile.reproduce_command,
            verify_command=repo_profile.verify_command,
            timeout_seconds=get_sandbox_timeout_seconds(),
        )
        secret_bindings = await self._resolve_secret_bindings(repo_profile.id)
        execution = self._local_runner.run(
            repository_root=repository_root,
            patch_diff=patch_diff,
            commands=commands,
            incident_id=sandbox_run.incident_id,
            patch_run_id=sandbox_run.patch_run_id,
            baseline_ref=baseline_commit_sha,
            secret_bindings=[
                SecretBindingRef(
                    mount_as=binding.mount_as,
                    external_ref=binding.secret_ref.external_ref,
                )
                for binding in secret_bindings
            ],
            secrets_reader=self._secrets_reader,
        )
        artifact_id = await self._store_log_artifact(
            incident_id=sandbox_run.incident_id,
            patch_run_id=sandbox_run.patch_run_id,
            sandbox_run_id=sandbox_run.id,
            object_key=f"sandbox-runs/{sandbox_run.id}/execution.log",
            content=execution.execution_log,
            content_type="text/plain",
            artifact_type=ArtifactType.EXECUTION_LOG,
        )
        terminal_status = (
            SandboxRunStatus.SUCCEEDED
            if execution.reproduction_succeeded and execution.patch_applied and execution.verification_succeeded
            else SandboxRunStatus.FAILED
        )
        finished_at = self._utcnow()
        await self._sandbox_repository.create_sandbox_run_step(
            sandbox_run_id=sandbox_run.id,
            step_name="execute-local",
            status=terminal_status,
            command="local sandbox runner",
            summary=execution.summary,
            artifact_id=artifact_id,
            exit_code=0 if terminal_status is SandboxRunStatus.SUCCEEDED else 1,
            finished=True,
        )
        await self._record_execution_metrics_step(
            sandbox_run=sandbox_run,
            backend="local",
            finished_at=finished_at,
            attempt_started_at=attempt_started_at,
            status=terminal_status,
        )
        return await self._sandbox_repository.update_sandbox_run(
            sandbox_run.id,
            status=terminal_status,
            reproduction_succeeded=execution.reproduction_succeeded,
            patch_applied=execution.patch_applied,
            verification_succeeded=execution.verification_succeeded,
            summary=execution.summary,
            execution_log=execution.execution_log,
        )

    async def _submit_kubernetes_run(
        self,
        *,
        sandbox_run: SandboxRunRecord,
        patch_run,
        repo_profile: RepoProfileRecord,
        repository_root: Path,
        repository_branch: str | None,
        repository_upstream_branch: str | None,
    ) -> SandboxRunRecord:
        provider_repository = await self._control_plane_repository.get_provider_repository(
            repo_profile.provider_repository_id
        )
        if provider_repository is None:
            raise APIError(
                f"Provider repository {repo_profile.provider_repository_id} was not found.",
                code="provider_repository_not_found",
            )
        provider_integration = await self._control_plane_repository.get_provider_integration(
            provider_repository.provider_integration_id
        )
        if provider_integration is None:
            raise APIError(
                f"Provider integration {provider_repository.provider_integration_id} was not found.",
                code="provider_integration_not_found",
            )
        adapter = get_provider_adapter(provider_repository.provider)
        snapshot = adapter.build_snapshot(
            repository=provider_repository,
            target_commit_sha=patch_run.based_on_commit_sha,
        )
        source_branch = self._resolve_repository_branch(
            repository_branch=repository_branch,
            repository_upstream_branch=repository_upstream_branch,
            fallback_branch=snapshot.default_branch,
        )
        snapshot = snapshot.__class__(
            provider=snapshot.provider,
            clone_url=snapshot.clone_url,
            owner=snapshot.owner,
            repository_name=snapshot.repository_name,
            default_branch=source_branch,
            target_commit_sha=snapshot.target_commit_sha,
        )
        provider_access_secret_arn = await self._provider_integration_service.build_sandbox_access_secret(
            project_id=repo_profile.project_id,
            sandbox_run_id=sandbox_run.id,
            integration=provider_integration,
            repository=provider_repository,
        )
        repository_archive_url = self._store_repository_archive(
            repository_root=repository_root,
            baseline_commit_sha=patch_run.based_on_commit_sha,
            sandbox_run_id=sandbox_run.id,
        )
        patch_diff_artifact_uri = await self._store_artifact_content(
            incident_id=sandbox_run.incident_id,
            patch_run_id=sandbox_run.patch_run_id,
            sandbox_run_id=sandbox_run.id,
            object_key=f"sandbox-runs/{sandbox_run.id}/patch.diff",
            content=patch_run.unified_diff,
            content_type="text/x-diff",
            artifact_type=ArtifactType.PATCH_DIFF,
        )
        secret_bindings = await self._resolve_secret_bindings(repo_profile.id)
        network_allowlist = list(repo_profile.network_allowlist)
        if repository_archive_url:
            archive_host = urlparse(repository_archive_url).hostname
            if archive_host:
                network_allowlist.append(archive_host)
        aws_region = get_aws_region()
        if aws_region and (secret_bindings or provider_access_secret_arn):
            network_allowlist.append(f"secretsmanager.{aws_region}.amazonaws.com")
        submission = self._kubernetes_runner.submit(
            incident_id=sandbox_run.incident_id,
            sandbox_run_id=sandbox_run.id,
            snapshot=snapshot,
            repo_profile=repo_profile,
            patch_diff_s3_uri=patch_diff_artifact_uri,
            patch_diff_content=patch_run.unified_diff,
            network_allowlist=network_allowlist,
            network_allowlist_cidrs=self._resolve_network_allowlist_cidrs(network_allowlist),
            secret_bindings=secret_bindings,
            repository_archive_url=repository_archive_url,
            provider_access_secret_arn=provider_access_secret_arn,
        )
        manifest_text = self._redact_manifest(
            submission.manifest,
            secret_bindings=secret_bindings,
        )
        manifest_artifact_id = await self._store_log_artifact(
            incident_id=sandbox_run.incident_id,
            patch_run_id=sandbox_run.patch_run_id,
            sandbox_run_id=sandbox_run.id,
            object_key=f"sandbox-runs/{sandbox_run.id}/job-manifest.json",
            content=manifest_text,
            content_type="application/json",
            artifact_type=ArtifactType.SANDBOX_MANIFEST,
        )
        await self._sandbox_repository.create_sandbox_run_step(
            sandbox_run_id=sandbox_run.id,
            step_name="submit-kubernetes-job",
            status=SandboxRunStatus.RUNNING,
            command="kubernetes job submission",
            summary=(
                f"Submitted Kubernetes job {submission.external_job_id} "
                "with a 500m CPU / 1Gi memory requested sandbox profile."
            ),
            artifact_id=manifest_artifact_id,
            exit_code=0,
            finished=True,
        )
        return await self._sandbox_repository.update_sandbox_run(
            sandbox_run.id,
            status=SandboxRunStatus.RUNNING,
            external_job_id=submission.external_job_id,
            summary="Sandbox run submitted to Kubernetes and is awaiting sandbox capacity.",
        )

    def _resolve_executor_backend(
        self,
        *,
        job_backend: str | None = None,
        run_backend: str | None = None,
    ) -> str:
        for candidate in (job_backend, run_backend, get_sandbox_execution_backend()):
            normalized = str(candidate or "").strip().lower()
            if normalized:
                if normalized in {"local", "kubernetes"}:
                    return normalized
                raise APIError(
                    f"Unsupported sandbox execution backend {normalized}.",
                    code="sandbox_backend_unsupported",
                )
        return "local"

    async def _record_queue_metrics_step(
        self,
        *,
        sandbox_run: SandboxRunRecord,
        backend: str,
        started_at: datetime,
    ) -> None:
        queue_wait_seconds = max(0.0, (started_at - sandbox_run.created_at).total_seconds())
        await self._sandbox_repository.create_sandbox_run_step(
            sandbox_run_id=sandbox_run.id,
            step_name="queue-metrics",
            status=SandboxRunStatus.RUNNING,
            command=None,
            summary=(
                f"Execution started on {backend} after {self._format_duration(queue_wait_seconds)} in queue."
            ),
            artifact_id=None,
            exit_code=None,
            finished=True,
        )

    async def _record_execution_metrics_step(
        self,
        *,
        sandbox_run: SandboxRunRecord,
        backend: str,
        finished_at: datetime,
        attempt_started_at: datetime | None,
        status: SandboxRunStatus,
    ) -> None:
        metrics = self._build_execution_metrics(
            sandbox_run=sandbox_run,
            backend=backend,
            finished_at=finished_at,
            attempt_started_at=attempt_started_at,
        )
        summary = (
            f"Performance profile: queued {self._format_duration(metrics.queue_wait_seconds)}, "
            f"total {self._format_duration(metrics.total_elapsed_seconds)}"
        )
        if metrics.execution_window_seconds is not None:
            summary += f", active execution {self._format_duration(metrics.execution_window_seconds)}"
        if (
            metrics.estimated_requested_vcpu_seconds is not None
            and metrics.estimated_requested_memory_gib_seconds is not None
        ):
            summary += (
                f", requested compute footprint {metrics.estimated_requested_vcpu_seconds:.1f} vCPU-s "
                f"and {metrics.estimated_requested_memory_gib_seconds:.1f} GiB-s"
            )
        summary += f" on {backend}."
        await self._sandbox_repository.create_sandbox_run_step(
            sandbox_run_id=sandbox_run.id,
            step_name="execution-metrics",
            status=status,
            command=None,
            summary=summary,
            artifact_id=None,
            exit_code=0 if status is SandboxRunStatus.SUCCEEDED else 1,
            finished=True,
        )

    def _build_execution_metrics(
        self,
        *,
        sandbox_run: SandboxRunRecord,
        backend: str,
        finished_at: datetime,
        attempt_started_at: datetime | None,
    ) -> SandboxExecutionMetrics:
        queue_wait_seconds = 0.0
        execution_window_seconds = None
        if attempt_started_at is not None:
            queue_wait_seconds = max(0.0, (attempt_started_at - sandbox_run.created_at).total_seconds())
            execution_window_seconds = max(0.0, (finished_at - attempt_started_at).total_seconds())
        total_elapsed_seconds = max(0.0, (finished_at - sandbox_run.created_at).total_seconds())
        estimated_requested_vcpu_seconds = None
        estimated_requested_memory_gib_seconds = None
        if backend == "kubernetes" and execution_window_seconds is not None:
            estimated_requested_vcpu_seconds = DEFAULT_SANDBOX_REQUEST_CPU_CORES * execution_window_seconds
            estimated_requested_memory_gib_seconds = DEFAULT_SANDBOX_REQUEST_MEMORY_GIB * execution_window_seconds
        return SandboxExecutionMetrics(
            backend=backend,
            queue_wait_seconds=queue_wait_seconds,
            total_elapsed_seconds=total_elapsed_seconds,
            execution_window_seconds=execution_window_seconds,
            estimated_requested_vcpu_seconds=estimated_requested_vcpu_seconds,
            estimated_requested_memory_gib_seconds=estimated_requested_memory_gib_seconds,
        )

    def _format_duration(self, seconds: float) -> str:
        if seconds >= 60:
            return f"{seconds / 60:.1f}m"
        if seconds >= 10:
            return f"{seconds:.1f}s"
        return f"{seconds:.2f}s"

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    def _resolve_repository_branch(
        self,
        *,
        repository_branch: str | None,
        repository_upstream_branch: str | None,
        fallback_branch: str,
    ) -> str:
        if repository_upstream_branch:
            normalized = repository_upstream_branch.strip()
            if normalized:
                if "/" in normalized:
                    _remote_name, branch_name = normalized.split("/", 1)
                    if branch_name:
                        return branch_name
                return normalized
        if repository_branch:
            normalized = repository_branch.strip()
            if normalized and normalized != "HEAD":
                return normalized
        return fallback_branch

    def _store_repository_archive(
        self,
        *,
        repository_root: Path,
        baseline_commit_sha: str | None,
        sandbox_run_id: str,
    ) -> str | None:
        if baseline_commit_sha is None:
            return None
        root = repository_root.resolve()
        if not root.exists():
            return None
        git_dir = root / ".git"
        if not git_dir.exists():
            return None
        try:
            archive = subprocess.run(
                ["git", "archive", "--format=tar.gz", baseline_commit_sha],
                cwd=root,
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        if not archive.stdout:
            return None
        object_key = f"sandbox-runs/{sandbox_run_id}/repository-baseline.tar.gz"
        try:
            self._artifact_storage.put_bytes(
                object_key=object_key,
                content=archive.stdout,
                content_type="application/gzip",
            )
            return self._artifact_storage.generate_download_url(object_key=object_key, expires_in_seconds=3600)
        except APIError:
            return None

    async def _get_repo_profile_for_project(self, project_id: str) -> RepoProfileRecord:
        repo_profile = await self._control_plane_repository.get_active_repo_profile(project_id)
        if repo_profile is None:
            raise APIError(
                f"No active repo profile is configured for project {project_id}.",
                status_code=404,
                code="repo_profile_not_found",
            )
        return repo_profile

    async def _resolve_service_context(self, incident) -> ResolvedSandboxServiceContext:
        if self._control_plane_repository is None:
            repo_profile = await self._get_repo_profile_for_project(incident.project_id)
            return ResolvedSandboxServiceContext(
                incident_id=incident.id,
                project_service=None,
                repo_profile=repo_profile,
                dependency_services=[],
            )

        project_service = None
        if incident.project_service_id and hasattr(self._control_plane_repository, "get_project_service"):
            project_service = await self._control_plane_repository.get_project_service(incident.project_service_id)
        if project_service is None and hasattr(self._control_plane_repository, "resolve_project_service"):
            project_service = await self._control_plane_repository.resolve_project_service(
                project_id=incident.project_id,
                service_name=incident.service,
            )
        repo_profile = None
        if project_service is not None and project_service.repo_profile_id is not None:
            repo_profile = await self._control_plane_repository.get_repo_profile(project_service.repo_profile_id)
        if repo_profile is None and incident.repo_profile_id:
            repo_profile = await self._control_plane_repository.get_repo_profile(incident.repo_profile_id)
        if repo_profile is None:
            repo_profile = await self._control_plane_repository.get_active_repo_profile(incident.project_id)
        if repo_profile is None:
            raise APIError(
                f"No repo profile is configured for project {incident.project_id}.",
                status_code=404,
                code="repo_profile_not_found",
            )
        if project_service is not None and (
            incident.project_service_id != project_service.id or incident.repo_profile_id != repo_profile.id
        ):
            await self._incident_repository.resolve_incident_service(
                incident.id,
                project_service_id=project_service.id,
                repo_profile_id=repo_profile.id,
            )
        dependency_records = (
            await self._control_plane_repository.list_project_service_dependencies(project_service.id)
            if project_service is not None
            and hasattr(self._control_plane_repository, "list_project_service_dependencies")
            else []
        )
        dependency_services: list[ProjectServiceRecord] = []
        for dependency in dependency_records:
            service = (
                await self._control_plane_repository.get_project_service(dependency.depends_on_service_id)
                if hasattr(self._control_plane_repository, "get_project_service")
                else None
            )
            if service is not None and service.active:
                dependency_services.append(service)
        dependency_services.sort(key=lambda item: (item.startup_priority, item.created_at))
        return ResolvedSandboxServiceContext(
            incident_id=incident.id,
            project_service=project_service,
            repo_profile=repo_profile,
            dependency_services=dependency_services,
        )

    async def _require_repo_profile(self, repo_profile_id: str) -> RepoProfileRecord:
        repo_profile = await self._control_plane_repository.get_repo_profile(repo_profile_id)
        if repo_profile is None:
            raise APIError(
                f"Repo profile {repo_profile_id} was not found.",
                status_code=404,
                code="repo_profile_not_found",
            )
        return repo_profile

    async def _find_run_by_async_job(
        self,
        async_job_id: str,
        incident_id: str,
    ) -> SandboxRunRecord | None:
        runs = await self._sandbox_repository.list_sandbox_runs(incident_id, limit=50)
        return next((run for run in runs if run.async_job_id == async_job_id), None)

    async def _resolve_patch_run(
        self,
        *,
        incident_id: str,
        patch_run_id: str | None,
        refresh_patch: bool,
        event_limit: int,
    ) -> PatchRunRecord:
        if patch_run_id is not None:
            patch_run = await self._patch_repository.get_patch_run(patch_run_id)
            if patch_run is None or patch_run.incident_id != incident_id:
                raise APIError(
                    f"Patch run {patch_run_id} was not found for incident {incident_id}.",
                    status_code=404,
                    code="patch_run_not_found",
                )
            return patch_run
        return await self._patch_generation.get_or_generate_patch(
            incident_id,
            refresh=refresh_patch,
            event_limit=event_limit,
        )

    async def _store_log_artifact(
        self,
        *,
        incident_id: str,
        patch_run_id: str,
        sandbox_run_id: str,
        object_key: str,
        content: str,
        content_type: str,
        artifact_type: ArtifactType,
    ) -> str | None:
        try:
            uri, size_bytes, checksum = self._artifact_storage.put_text(
                object_key=object_key,
                content=content,
                content_type=content_type,
            )
        except APIError:
            return None
        artifact = await self._artifact_repository.create_artifact(
            incident_id=incident_id,
            patch_run_id=patch_run_id,
            sandbox_run_id=sandbox_run_id,
            artifact_type=artifact_type,
            storage_backend=ArtifactStorageBackend.S3,
            bucket_name=self._artifact_storage.bucket_name,  # type: ignore[attr-defined]
            object_key=object_key,
            uri=uri,
            content_type=content_type,
            size_bytes=size_bytes,
            checksum_sha256=checksum,
        )
        return artifact.id

    async def _store_artifact_content(
        self,
        *,
        incident_id: str,
        patch_run_id: str,
        sandbox_run_id: str,
        object_key: str,
        content: str,
        content_type: str,
        artifact_type: ArtifactType,
    ) -> str | None:
        try:
            uri, size_bytes, checksum = self._artifact_storage.put_text(
                object_key=object_key,
                content=content,
                content_type=content_type,
            )
        except APIError:
            return None
        await self._artifact_repository.create_artifact(
            incident_id=incident_id,
            patch_run_id=patch_run_id,
            sandbox_run_id=sandbox_run_id,
            artifact_type=artifact_type,
            storage_backend=ArtifactStorageBackend.S3,
            bucket_name=self._artifact_storage.bucket_name,  # type: ignore[attr-defined]
            object_key=object_key,
            uri=uri,
            content_type=content_type,
            size_bytes=size_bytes,
            checksum_sha256=checksum,
        )
        return uri

    async def _resolve_secret_bindings(
        self,
        repo_profile_id: str,
    ) -> list[RepoProfileSecretBindingRecord]:
        return await self._control_plane_repository.list_repo_profile_secret_bindings(repo_profile_id)

    def _resolve_network_allowlist_cidrs(self, network_allowlist: list[str]) -> list[str]:
        resolved: set[str] = set()
        for entry in network_allowlist:
            normalized = entry.strip()
            if not normalized:
                continue
            try:
                network = ipaddress.ip_network(normalized, strict=False)
            except ValueError:
                try:
                    address = ipaddress.ip_address(normalized)
                except ValueError:
                    try:
                        addrinfo = socket.getaddrinfo(normalized, None)
                    except OSError:
                        continue
                    for item in addrinfo:
                        address_text = item[4][0]
                        try:
                            address = ipaddress.ip_address(address_text)
                        except ValueError:
                            continue
                        resolved.add(f"{address}/32" if address.version == 4 else f"{address}/128")
                else:
                    resolved.add(f"{address}/32" if address.version == 4 else f"{address}/128")
            else:
                resolved.add(str(network))
        return sorted(resolved)

    def _redact_manifest(
        self,
        manifest: dict[str, object],
        *,
        secret_bindings: list[RepoProfileSecretBindingRecord],
    ) -> str:
        secrets_by_name = {
            f"STIMPACT_SECRET_BINDING_{index}_MOUNT_AS": binding.mount_as
            for index, binding in enumerate(secret_bindings)
        }
        secrets_by_name.update(
            {
                f"STIMPACT_SECRET_BINDING_{index}_EXTERNAL_REF": "***REDACTED***"
                for index, binding in enumerate(secret_bindings)
                if binding.secret_ref.external_ref
            }
        )
        secrets_by_name["STIMPACT_PROVIDER_ACCESS_SECRET_ARN"] = "***REDACTED***"

        def _redact_job(job_manifest: dict[str, object]) -> dict[str, object]:
            spec = job_manifest.get("spec")
            if not isinstance(spec, dict):
                return job_manifest
            template = spec.get("template")
            if not isinstance(template, dict):
                return job_manifest
            pod_spec = template.get("spec")
            if not isinstance(pod_spec, dict):
                return job_manifest
            containers = pod_spec.get("containers")
            init_containers = pod_spec.get("initContainers")
            if not isinstance(containers, list):
                return job_manifest

            def _redact_container_list(raw_containers: list[object]) -> list[object]:
                redacted_containers: list[object] = []
                for container in raw_containers:
                    if not isinstance(container, dict):
                        redacted_containers.append(container)
                        continue
                    copied_container = dict(container)
                    env_entries = copied_container.get("env")
                    if isinstance(env_entries, list):
                        copied_container["env"] = [
                            (
                                {
                                    **entry,
                                    "value": secrets_by_name.get(str(entry.get("name")), entry.get("value")),
                                }
                                if isinstance(entry, dict)
                                else entry
                            )
                            for entry in env_entries
                        ]
                    redacted_containers.append(copied_container)
                return redacted_containers

            redacted_containers = _redact_container_list(containers)
            redacted_init_containers = (
                _redact_container_list(init_containers)
                if isinstance(init_containers, list)
                else init_containers
            )

            redacted_manifest = dict(job_manifest)
            redacted_spec = dict(spec)
            redacted_template = dict(template)
            redacted_pod_spec = dict(pod_spec)
            redacted_pod_spec["containers"] = redacted_containers
            if isinstance(redacted_init_containers, list):
                redacted_pod_spec["initContainers"] = redacted_init_containers
            redacted_template["spec"] = redacted_pod_spec
            redacted_spec["template"] = redacted_template
            redacted_manifest["spec"] = redacted_spec
            return redacted_manifest

        if manifest.get("kind") == "List" and isinstance(manifest.get("items"), list):
            redacted = dict(manifest)
            redacted["items"] = [
                _redact_job(item) if isinstance(item, dict) and item.get("kind") == "Job" else item
                for item in manifest["items"]
            ]
            return str(redacted)
        return str(_redact_job(manifest))
