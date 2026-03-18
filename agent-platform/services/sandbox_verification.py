from __future__ import annotations

from pathlib import Path

from api.core.config import (
    get_repository_root,
    get_sandbox_execution_backend,
    get_sandbox_timeout_seconds,
)
from api.core.errors import APIError
from api.repositories.artifact_repository import ArtifactRepository
from api.repositories.async_job_repository import AsyncJobRepository
from api.repositories.control_plane_repository import ControlPlaneRepository
from api.repositories.incident_repository import IncidentRepository
from api.repositories.sandbox_repository import SandboxRepository
from models.artifact import ArtifactStorageBackend, ArtifactType
from models.async_job import AsyncJobRecord, AsyncJobStatus, AsyncJobType
from models.control_plane import RepoProfileRecord
from models.sandbox import SandboxRunRecord, SandboxRunStatus
from sandbox.kubernetes_runner import KubernetesSandboxRunner
from sandbox.runner import LocalSandboxRunner, SandboxCommandSet
from services.artifact_storage import ArtifactStorage, S3ArtifactStorage
from services.aws_secrets_manager import AwsSecretsManagerReader, AwsSecretsManagerWriter
from services.patch_generation import PatchGenerationService
from services.provider_integration_service import ProviderIntegrationService
from services.repository_provider import get_provider_adapter


class SandboxVerificationService:
    def __init__(
        self,
        incident_repository: IncidentRepository,
        sandbox_repository: SandboxRepository,
        *,
        control_plane_repository: ControlPlaneRepository,
        async_job_repository: AsyncJobRepository,
        artifact_repository: ArtifactRepository,
        patch_generation: PatchGenerationService,
        local_runner: LocalSandboxRunner | None = None,
        kubernetes_runner: KubernetesSandboxRunner | None = None,
        artifact_storage: ArtifactStorage | None = None,
        provider_integration_service: ProviderIntegrationService | None = None,
        runner: LocalSandboxRunner | None = None,
        repository_root: Path | None = None,
    ) -> None:
        self._incident_repository = incident_repository
        self._sandbox_repository = sandbox_repository
        self._control_plane_repository = control_plane_repository
        self._async_job_repository = async_job_repository
        self._artifact_repository = artifact_repository
        self._patch_generation = patch_generation
        self._local_runner = local_runner or runner or LocalSandboxRunner()
        self._kubernetes_runner = kubernetes_runner or KubernetesSandboxRunner()
        self._artifact_storage = artifact_storage or S3ArtifactStorage()
        self._repository_root = repository_root or get_repository_root()
        self._provider_integration_service = provider_integration_service or ProviderIntegrationService(
            control_plane_repository,
            secrets_writer=AwsSecretsManagerWriter(),
            secrets_reader=AwsSecretsManagerReader(),
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
    ) -> tuple[SandboxRunRecord, AsyncJobRecord]:
        incident = await self._incident_repository.get_incident(incident_id)
        if incident is None:
            raise APIError(
                f"Incident {incident_id} was not found.",
                status_code=404,
                code="incident_not_found",
            )

        repo_profile = await self._get_repo_profile_for_project(incident.project_id)
        patch_run = await self._patch_generation.get_or_generate_patch(
            incident_id,
            refresh=refresh_patch,
            event_limit=event_limit,
        )

        job = await self._async_job_repository.create_job(
            job_type=AsyncJobType.SANDBOX_RUN,
            payload={
                "incident_id": incident.id,
                "patch_run_id": patch_run.id,
                "repo_profile_id": repo_profile.id,
                "event_limit": event_limit,
                "refresh_patch": refresh_patch,
            },
            dedupe_key=f"sandbox:{incident.id}:{patch_run.id}",
        )
        sandbox_run = await self._sandbox_repository.create_sandbox_run(
            incident_id=incident.id,
            patch_run_id=patch_run.id,
            repo_profile_id=repo_profile.id,
            async_job_id=job.id,
            status=SandboxRunStatus.QUEUED,
            executor_backend=get_sandbox_execution_backend(),
            install_command=repo_profile.install_command,
            reproduce_command=repo_profile.reproduce_command,
            verify_command=repo_profile.verify_command,
            reproduction_succeeded=False,
            patch_applied=False,
            verification_succeeded=False,
            summary="Sandbox run queued for asynchronous execution.",
            execution_log="",
        )
        await self._sandbox_repository.create_sandbox_run_step(
            sandbox_run_id=sandbox_run.id,
            step_name="queue",
            status=SandboxRunStatus.QUEUED,
            command=None,
            summary="Sandbox run was queued.",
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

        patch_run = await self._patch_generation.get_or_generate_patch(
            incident_id,
            refresh=bool(job.payload.get("refresh_patch", False)),
            event_limit=int(job.payload.get("event_limit", 50)),
        )
        repo_profile = await self._require_repo_profile(str(job.payload["repo_profile_id"]))
        await self._sandbox_repository.update_sandbox_run(
            sandbox_run.id,
            status=SandboxRunStatus.RUNNING,
            summary="Sandbox run is starting execution.",
        )
        await self._sandbox_repository.create_sandbox_run_attempt(
            sandbox_run_id=sandbox_run.id,
            async_job_id=job.id,
            attempt_number=job.attempts,
            status=SandboxRunStatus.RUNNING,
            error_message=None,
            finished=False,
        )
        await self._sandbox_repository.create_sandbox_run_step(
            sandbox_run_id=sandbox_run.id,
            step_name="resolve-profile",
            status=SandboxRunStatus.RUNNING,
            command=None,
            summary="Resolved repo profile and execution backend.",
            artifact_id=None,
            exit_code=None,
            finished=True,
        )

        backend = get_sandbox_execution_backend()
        if backend == "kubernetes":
            return await self._submit_kubernetes_run(
                sandbox_run=sandbox_run,
                patch_run=patch_run,
                repo_profile=repo_profile,
            )
        return await self._execute_local_run(
            sandbox_run=sandbox_run,
            patch_diff=patch_run.unified_diff,
            repo_profile=repo_profile,
        )

    async def _execute_local_run(
        self,
        *,
        sandbox_run: SandboxRunRecord,
        patch_diff: str,
        repo_profile: RepoProfileRecord,
    ) -> SandboxRunRecord:
        commands = SandboxCommandSet(
            install_command=repo_profile.install_command,
            reproduce_command=repo_profile.reproduce_command,
            verify_command=repo_profile.verify_command,
            timeout_seconds=get_sandbox_timeout_seconds(),
        )
        execution = self._local_runner.run(
            repository_root=self._repository_root,
            patch_diff=patch_diff,
            commands=commands,
            incident_id=sandbox_run.incident_id,
            patch_run_id=sandbox_run.patch_run_id,
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
        provider_access_secret_arn, provider_access_secret_format = (
            await self._provider_integration_service.build_sandbox_access_secret(
                project_id=repo_profile.project_id,
                sandbox_run_id=sandbox_run.id,
                integration=provider_integration,
                repository=provider_repository,
            )
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
        secret_refs = await self._control_plane_repository.list_repo_profile_secret_refs(repo_profile.id)
        submission = self._kubernetes_runner.submit(
            incident_id=sandbox_run.incident_id,
            sandbox_run_id=sandbox_run.id,
            snapshot=snapshot,
            repo_profile=repo_profile,
            patch_diff_s3_uri=patch_diff_artifact_uri,
            network_allowlist=repo_profile.network_allowlist,
            secret_env_refs=[secret_ref.label for secret_ref in secret_refs],
            provider_access_secret_arn=provider_access_secret_arn,
            provider_access_secret_format=provider_access_secret_format,
        )
        manifest_text = str(submission.manifest)
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
            summary=f"Submitted Kubernetes job {submission.external_job_id}.",
            artifact_id=manifest_artifact_id,
            exit_code=0,
            finished=True,
        )
        return await self._sandbox_repository.update_sandbox_run(
            sandbox_run.id,
            status=SandboxRunStatus.RUNNING,
            external_job_id=submission.external_job_id,
            summary="Sandbox run submitted to Kubernetes and is awaiting completion.",
        )

    async def _get_repo_profile_for_project(self, project_id: str) -> RepoProfileRecord:
        repo_profile = await self._control_plane_repository.get_active_repo_profile(project_id)
        if repo_profile is None:
            raise APIError(
                f"No active repo profile is configured for project {project_id}.",
                status_code=404,
                code="repo_profile_not_found",
            )
        return repo_profile

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
