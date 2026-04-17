from __future__ import annotations

import atexit
import json
import logging
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from openai import AsyncOpenAI

from api.core.config import (
    get_openai_api_key,
    get_openai_autonomous_model,
    get_openai_rca_model,
    get_repository_root,
)
from api.core.errors import APIError
from api.repositories.async_job_repository import AsyncJobRepository
from api.repositories.autonomous_repository import AutonomousRunRepository
from api.repositories.control_plane_repository import ControlPlaneRepository
from api.repositories.incident_repository import IncidentRepository
from api.repositories.patch_repository import PatchRepository
from api.schemas.autonomous import (
    AutonomousRunApprovalRequest,
    AutonomousRunCreateRequest,
    AutonomousRunDetailResponse,
)
from harness.git_ops.checkpoints import GitCheckpointManager
from harness.autonomous import OpenAIAutonomousDecisionEngine
from harness.autonomous.events import (
    AutonomousRunSubscriber,
    PersistentAutonomousRunEventStream,
)
from harness.autonomous.runner import AutonomousRepairRunner
from harness.autonomous.storage import AutonomousRunArtifactStore
from harness.schemas.autonomous import (
    AutonomousApprovalStatus,
    AutonomousExecutionMode,
    AutonomousToolFailureClass,
    AutonomousPromotionStatus,
    AutonomousRepairRunRecord,
    AutonomousRunPhase,
    AutonomousRunOutcome,
    AutonomousRunStatus,
    AutonomousRunSnapshot,
    AutonomousVerificationEvidence,
)
from harness.schemas.initializer import FeatureSeed
from harness.schemas.verification import VerificationKind
from models.async_job import AsyncJobStatus, AsyncJobType
from models.incident import IncidentStatus
from models.patch import PatchProposal, PatchTargetFile
from models.sandbox import SandboxRunRecord, SandboxRunStatus
from services.autonomous_policy import AutonomousPolicyService
from services.harness_profile_adapter import HarnessControlPlaneProfileAdapter
from services.provider_integration_service import ProviderIntegrationService
from services.resolution_narrative import ResolutionNarrativeService
from services.repository_provider import get_provider_adapter
from services.root_cause_analysis import (
    RootCauseAnalysisService,
    RootCauseAnalyzer,
    RootCauseReasoner,
)
from services.sandbox_verification import SandboxVerificationService
from services.failure_classifier import FailureClassifier


@dataclass(slots=True)
class ResolvedAutonomousServiceContext:
    incident: object
    project_service: object | None
    repo_profile: object | None
    project_policy: object | None


logger = logging.getLogger(__name__)

_active_workspaces: dict[str, Path] = {}


def _prepare_repository_workspace(
    *,
    run_id: str,
    clone_url: str,
    default_branch: str,
) -> Path:
    """Clone the connected repo into a temporary workspace for the agent.

    The workspace is kept alive for the lifetime of the run and cleaned up
    after the run completes (or when the process exits).
    """
    if run_id in _active_workspaces and _active_workspaces[run_id].exists():
        return _active_workspaces[run_id]

    workspace_dir = Path(tempfile.mkdtemp(prefix=f"stimpact-agent-{run_id[:8]}-"))
    repo_dir = workspace_dir / "repo"
    logger.info(
        "Cloning connected repo for autonomous run",
        extra={"run_id": run_id, "clone_url": clone_url, "target": str(repo_dir)},
    )
    subprocess.run(
        [
            "git", "clone", "--quiet", "--depth", "50",
            "--single-branch", "--branch", default_branch,
            clone_url, str(repo_dir),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    _active_workspaces[run_id] = repo_dir
    return repo_dir


def _cleanup_workspace(run_id: str) -> None:
    repo_dir = _active_workspaces.pop(run_id, None)
    if repo_dir is None:
        return
    workspace_dir = repo_dir.parent
    try:
        shutil.rmtree(workspace_dir, ignore_errors=True)
        logger.info("Cleaned up agent workspace", extra={"run_id": run_id, "path": str(workspace_dir)})
    except Exception:  # noqa: BLE001
        logger.warning("Failed to clean up agent workspace", extra={"run_id": run_id, "path": str(workspace_dir)})


def _cleanup_all_workspaces() -> None:
    for run_id in list(_active_workspaces):
        _cleanup_workspace(run_id)


atexit.register(_cleanup_all_workspaces)


class AutonomousRunService:
    def __init__(
        self,
        incident_repository: IncidentRepository,
        *,
        async_job_repository: AsyncJobRepository | None = None,
        autonomous_repository: AutonomousRunRepository | None = None,
        control_plane_repository: ControlPlaneRepository | None = None,
        patch_repository: PatchRepository | None = None,
        sandbox_verification_service: SandboxVerificationService | None = None,
        repository_root: Path | None = None,
        artifact_store: AutonomousRunArtifactStore | None = None,
        event_stream: PersistentAutonomousRunEventStream | None = None,
        runner: AutonomousRepairRunner | None = None,
        decision_engine_factory: Callable[[], OpenAIAutonomousDecisionEngine] | None = None,
        policy_service: AutonomousPolicyService | None = None,
        profile_adapter: HarnessControlPlaneProfileAdapter | None = None,
        provider_integration_service: ProviderIntegrationService | None = None,
        resolution_narrative_service: ResolutionNarrativeService | None = None,
    ) -> None:
        self._incident_repository = incident_repository
        self._async_job_repository = async_job_repository
        self._autonomous_repository = autonomous_repository
        self._control_plane_repository = control_plane_repository
        self._patch_repository = patch_repository
        self._sandbox_verification_service = sandbox_verification_service
        self._repository_root = repository_root or get_repository_root()
        self._artifact_store = artifact_store or AutonomousRunArtifactStore()
        self._event_stream = event_stream or PersistentAutonomousRunEventStream(artifact_store=self._artifact_store)
        self._runner = runner or AutonomousRepairRunner(event_stream=self._event_stream)
        self._decision_engine_factory = decision_engine_factory or self._build_decision_engine
        self._policy_service = policy_service or AutonomousPolicyService()
        self._profile_adapter = profile_adapter or HarnessControlPlaneProfileAdapter()
        self._provider_integration_service = provider_integration_service
        self._resolution_narrative_service = (
            resolution_narrative_service
            if resolution_narrative_service is not None
            else self._build_resolution_narrative_service()
        )

    async def start_run(
        self,
        incident_id: str,
        request: AutonomousRunCreateRequest,
    ) -> AutonomousRunDetailResponse:
        service_context = await self._resolve_incident_service_context(incident_id)
        incident = service_context.incident
        if incident.status is IncidentStatus.ACKNOWLEDGED:
            incident = await self._incident_repository.update_incident_status(
                incident_id,
                IncidentStatus.OPEN,
            )
        repo_profile = service_context.repo_profile
        repository_root = request.repository_root or str(self._repository_root)
        latest_telemetry = await self._incident_repository.get_telemetry(incident.latest_telemetry_id)
        dependency_service_slugs: list[str] = []
        if (
            service_context.project_service is not None
            and self._control_plane_repository is not None
            and hasattr(self._control_plane_repository, "list_project_service_dependencies")
            and hasattr(self._control_plane_repository, "get_project_service")
        ):
            dependency_records = await self._control_plane_repository.list_project_service_dependencies(
                service_context.project_service.id
            )
            for dependency in dependency_records:
                dependency_service = await self._control_plane_repository.get_project_service(
                    dependency.depends_on_service_id
                )
                if dependency_service is not None:
                    dependency_service_slugs.append(dependency_service.slug)
        provider_repository = None
        if repo_profile is not None and self._control_plane_repository is not None:
            provider_repository = await self._control_plane_repository.get_provider_repository(
                repo_profile.provider_repository_id
            )
        if (
            request.repository_root is None
            and provider_repository is not None
            and self._provider_integration_service is not None
        ):
            repository_root = str(await self._clone_connected_repo(
                incident_id=incident_id,
                provider_repository=provider_repository,
            ))
        repository_profile_override = self._profile_adapter.build_profile(
            repository_root=repository_root,
            repo_profile=repo_profile,
        )
        browser_verification_supported = self._supports_browser_verification(repository_profile_override)
        feature_seeds = request.feature_seeds or self._derive_feature_seeds(
            incident=incident,
            repo_profile=repo_profile,
            requested_mode=request.execution_mode,
            browser_verification_supported=browser_verification_supported,
        )
        policy, approval_status = self._policy_service.evaluate(
            incident=incident,
            repo_profile=repo_profile,
            project_service=service_context.project_service,
            project_policy=service_context.project_policy,
            request=request,
            browser_verification_supported=browser_verification_supported,
        )
        policy_block_reason = self._policy_block_reason(policy)
        snapshot = self._runner.bootstrap_run(
            incident_id=incident_id,
            repo_profile_id=repo_profile.id if repo_profile is not None else None,
            repository_root=repository_root,
            objective=request.objective
            or f"Investigate, repair, and verify incident '{incident.title}' for service {incident.service}.",
            initializer_summary=request.initializer_summary
            or "Prepare the repository, verification state, and repair context for autonomous incident resolution.",
            execution_mode=request.execution_mode,
            approval_status=approval_status,
            promotion_status=AutonomousPromotionStatus.NOT_REQUESTED,
            policy=policy,
            repository_profile_override=repository_profile_override,
            feature_seeds=feature_seeds,
        )
        run = snapshot.run.model_copy(
            update={
                "status": AutonomousRunStatus.QUEUED,
                "phase": snapshot.run.phase,
                "project_id": incident.project_id,
                "repo_profile_id": repo_profile.id if repo_profile is not None else None,
                "incident_title": incident.title,
                "incident_fingerprint": incident.fingerprint,
                "service_name": incident.service,
                "environment": incident.environment.value,
                "latest_telemetry_id": incident.latest_telemetry_id,
                "latest_telemetry_commit_sha": latest_telemetry.commit_sha,
                "latest_telemetry_error_message": latest_telemetry.error_message,
                "runtime_kind": repo_profile.runtime_kind.value if repo_profile is not None else None,
                "provider_repository_owner": provider_repository.owner if provider_repository is not None else None,
                "provider_repository_name": provider_repository.name if provider_repository is not None else None,
                "install_command": repo_profile.install_command if repo_profile is not None else None,
                "reproduce_command": repo_profile.reproduce_command if repo_profile is not None else None,
                "verify_command": repo_profile.verify_command if repo_profile is not None else None,
                "success_criteria": repo_profile.success_criteria if repo_profile is not None else None,
                "network_allowlist": list(repo_profile.network_allowlist) if repo_profile is not None else [],
                "dependency_service_slugs": dependency_service_slugs,
                "browser_verification_urls": [
                    entrypoint.url for entrypoint in repository_profile_override.browser_verification_entrypoints
                ],
                "execution_mode": request.execution_mode,
                "approval_status": approval_status,
                "benchmark_scenario_id": request.benchmark_scenario_id,
                "benchmark_bug_class": request.benchmark_bug_class,
                "policy": policy,
                "policy_block_reason": policy_block_reason,
                "loop_state": snapshot.run.loop_state.model_copy(update={"max_steps": request.max_steps}),
            }
        )
        self._event_stream.upsert_run(run)

        async_job_id = None
        if policy.auto_run_allowed and self._async_job_repository is not None:
            job = await self._async_job_repository.create_job(
                job_type=AsyncJobType.AUTONOMOUS_REPAIR,
                payload={"incident_id": incident_id, "autonomous_run_id": run.id},
                dedupe_key=f"autonomous:{incident_id}:{run.id}",
                status=AsyncJobStatus.QUEUED,
            )
            async_job_id = job.id
            run = run.model_copy(update={"async_job_id": async_job_id})
            self._event_stream.upsert_run(run)

        if self._autonomous_repository is not None:
            await self._autonomous_repository.create_run(
                incident_id=incident_id,
                project_service_id=service_context.project_service.id
                if service_context.project_service is not None
                else None,
                repo_profile_id=repo_profile.id if repo_profile is not None else None,
                async_job_id=async_job_id,
                feature_seeds=feature_seeds,
                initializer_summary=request.initializer_summary
                or "Prepare the repository, verification state, and repair context for autonomous incident resolution.",
                max_steps=request.max_steps,
                run=run,
                outcome=None,
            )
        return AutonomousRunDetailResponse(
            run=run,
            events=snapshot.events,
            outcome=None,
            artifact_paths=self._artifact_store.get_artifact_paths(incident_id, run.id),
        )

    async def list_runs(self, incident_id: str) -> list[AutonomousRepairRunRecord]:
        await self._require_incident(incident_id)
        if self._autonomous_repository is not None:
            return [record.run for record in await self._autonomous_repository.list_runs(incident_id)]
        return self._artifact_store.list_runs(incident_id)

    async def get_latest_run_detail(self, incident_id: str) -> AutonomousRunDetailResponse:
        await self._require_incident(incident_id)
        run_id = None
        if self._autonomous_repository is not None:
            records = await self._autonomous_repository.list_runs(incident_id)
            if records:
                run_id = records[0].id
        if run_id is None:
            run_id = self._artifact_store.get_latest_run_id(incident_id)
        if run_id is None:
            raise APIError(
                f"No autonomous repair run has been recorded yet for incident {incident_id}.",
                status_code=404,
                code="autonomous_run_not_found",
            )
        return self.get_run_detail_sync(incident_id, run_id)

    async def get_run_detail(self, incident_id: str, run_id: str) -> AutonomousRunDetailResponse:
        await self._require_incident(incident_id)
        return self.get_run_detail_sync(incident_id, run_id)

    def get_run_detail_sync(self, incident_id: str, run_id: str) -> AutonomousRunDetailResponse:
        snapshot = self._load_snapshot(incident_id, run_id)
        if snapshot.run.incident_id not in {None, incident_id}:
            raise APIError(
                f"Autonomous run {run_id} was not found for incident {incident_id}.",
                status_code=404,
                code="autonomous_run_not_found",
            )
        return AutonomousRunDetailResponse(
            run=snapshot.run,
            events=snapshot.events,
            outcome=self._artifact_store.get_outcome(incident_id, run_id),
            artifact_paths=self._artifact_store.get_artifact_paths(incident_id, run_id),
        )

    def subscribe(self, run_id: str, subscriber: AutonomousRunSubscriber) -> None:
        self._event_stream.subscribe(run_id, subscriber)

    def unsubscribe(self, run_id: str, subscriber: AutonomousRunSubscriber) -> None:
        self._event_stream.unsubscribe(run_id, subscriber)

    def is_terminal(self, run: AutonomousRepairRunRecord) -> bool:
        return run.status in {
            AutonomousRunStatus.SUCCEEDED,
            AutonomousRunStatus.FAILED,
            AutonomousRunStatus.CANCELLED,
        }

    async def mark_run_failed(self, *, incident_id: str, run_id: str, error: str) -> None:
        """Mark a run as failed so the UI no longer shows it as stuck in 'Repairing'."""
        try:
            snapshot = self._load_snapshot(incident_id, run_id)
            failed_run = snapshot.run.model_copy(
                update={
                    "status": AutonomousRunStatus.FAILED,
                    "last_error": error,
                }
            )
            self._event_stream.upsert_run(failed_run)
            if self._autonomous_repository is not None:
                await self._autonomous_repository.update_run(
                    run_id,
                    async_job_id=failed_run.async_job_id,
                    project_service_id=None,
                    repo_profile_id=failed_run.repo_profile_id,
                    run=failed_run,
                    outcome=None,
                )
            logger.info("Marked autonomous run %s as failed: %s", run_id, error[:200])
        except Exception:
            logger.exception("Could not mark autonomous run %s as failed", run_id)

    def _load_snapshot(self, incident_id: str, run_id: str):
        event_stream_snapshot = None
        if self._event_stream.has_run(run_id):
            event_stream_snapshot = self._event_stream.get_snapshot(run_id)
        artifact_snapshot = None
        try:
            artifact_snapshot = self._artifact_store.get_snapshot(incident_id, run_id)
        except KeyError as exc:
            if event_stream_snapshot is not None:
                return event_stream_snapshot
            raise APIError(
                f"Autonomous run {run_id} was not found for incident {incident_id}.",
                status_code=404,
                code="autonomous_run_not_found",
            ) from exc
        if event_stream_snapshot is None:
            return artifact_snapshot
        if artifact_snapshot.run.updated_at >= event_stream_snapshot.run.updated_at:
            return artifact_snapshot
        return event_stream_snapshot

    async def approve_run(
        self,
        incident_id: str,
        run_id: str,
        request: AutonomousRunApprovalRequest,
    ) -> AutonomousRunDetailResponse:
        await self._require_incident(incident_id)
        detail = self.get_run_detail_sync(incident_id, run_id)
        persisted_record = (
            await self._autonomous_repository.get_run(run_id)
            if self._autonomous_repository is not None
            else None
        )
        updated_run = detail.run.model_copy(update={"approval_status": request.approval_status})
        if request.approval_status is AutonomousApprovalStatus.REJECTED:
            updated_run = updated_run.model_copy(
                update={
                    "status": AutonomousRunStatus.CANCELLED,
                    "last_error": "Autonomous run was rejected before execution.",
                }
            )
        elif (
            request.approval_status is AutonomousApprovalStatus.APPROVED
            and updated_run.async_job_id is None
            and self._async_job_repository is not None
            and updated_run.policy.auto_run_allowed
        ):
            job = await self._async_job_repository.create_job(
                job_type=AsyncJobType.AUTONOMOUS_REPAIR,
                payload={"incident_id": incident_id, "autonomous_run_id": run_id},
                dedupe_key=f"autonomous:{incident_id}:{run_id}",
                status=AsyncJobStatus.QUEUED,
            )
            updated_run = updated_run.model_copy(update={"async_job_id": job.id, "status": AutonomousRunStatus.QUEUED})

        self._event_stream.upsert_run(updated_run)
        if self._autonomous_repository is not None:
            await self._autonomous_repository.update_run(
                run_id,
                async_job_id=updated_run.async_job_id,
                project_service_id=getattr(persisted_record, "project_service_id", None),
                repo_profile_id=updated_run.repo_profile_id,
                run=updated_run,
                outcome=detail.outcome,
            )
        return AutonomousRunDetailResponse(
            run=updated_run,
            events=detail.events,
            outcome=detail.outcome,
            artifact_paths=detail.artifact_paths,
        )

    async def process_async_job(self, job) -> AutonomousRunDetailResponse:
        if job.job_type is not AsyncJobType.AUTONOMOUS_REPAIR:
            raise APIError(
                f"Unsupported async job type {job.job_type.value}.",
                code="unsupported_async_job",
            )
        incident_id = str(job.payload["incident_id"])
        run_id = str(job.payload["autonomous_run_id"])
        detail = self.get_run_detail_sync(incident_id, run_id)
        self._hydrate_event_stream(detail)
        persisted_record = (
            await self._autonomous_repository.get_run(run_id)
            if self._autonomous_repository is not None
            else None
        )
        repo_profile = (
            await self._require_repo_profile(detail.run.repo_profile_id)
            if detail.run.repo_profile_id is not None
            else None
        )
        repository_root = detail.run.repository_root
        if not Path(repository_root).exists() and repo_profile is not None and self._control_plane_repository is not None:
            provider_repository = await self._control_plane_repository.get_provider_repository(
                repo_profile.provider_repository_id
            )
            if provider_repository is not None and self._provider_integration_service is not None:
                repository_root = str(await self._clone_connected_repo(
                    incident_id=incident_id,
                    provider_repository=provider_repository,
                ))
                detail = detail.model_copy(
                    update={"run": detail.run.model_copy(update={"repository_root": repository_root})}
                )
        repository_profile_override = (
            self._profile_adapter.build_profile(
                repository_root=repository_root,
                repo_profile=repo_profile,
            )
            if repo_profile is not None
            else None
        )
        initializer_summary = (
            persisted_record.initializer_summary
            if persisted_record is not None
            else "Prepare the repository, verification state, and repair context for autonomous incident resolution."
        )
        feature_seeds = persisted_record.feature_seeds if persisted_record is not None else []
        attempt_budget = max(1, detail.run.policy.max_repair_attempts)

        try:
            for attempt_number in range(1, attempt_budget + 1):
                ensured_snapshot = self._runner.ensure_sessions(
                    run_id=run_id,
                    repository_root=repository_root,
                    objective=detail.run.objective,
                    initializer_summary=initializer_summary,
                    repository_profile_override=repository_profile_override,
                    feature_seeds=feature_seeds,
                )
                active_run = ensured_snapshot.run
                if self._autonomous_repository is not None:
                    await self._autonomous_repository.create_attempt(
                        autonomous_run_id=run_id,
                        async_job_id=job.id,
                        attempt_number=attempt_number,
                        status=AsyncJobStatus.RUNNING.value,
                        error_message=None,
                        finished=False,
                    )
                running_run = active_run.model_copy(
                    update={
                        "status": AutonomousRunStatus.RUNNING,
                        "async_job_id": job.id,
                    }
                )
                self._event_stream.upsert_run(running_run)
                decision_engine = self._decision_engine_factory()
                snapshot = await self._runner.continue_run(
                    run_id=run_id,
                    decision_engine=decision_engine,
                    max_steps=active_run.loop_state.max_steps,
                )
                snapshot = await self._postprocess_completed_run(snapshot)
                outcome = self._artifact_store.get_outcome(incident_id, run_id)
                if self._autonomous_repository is not None:
                    await self._autonomous_repository.update_run(
                        run_id,
                        async_job_id=job.id,
                        project_service_id=getattr(persisted_record, "project_service_id", None),
                        repo_profile_id=snapshot.run.repo_profile_id,
                        run=snapshot.run.model_copy(update={"async_job_id": job.id}),
                        outcome=outcome,
                    )
                    await self._autonomous_repository.create_attempt(
                        autonomous_run_id=run_id,
                        async_job_id=job.id,
                        attempt_number=attempt_number,
                        status=(
                            job.status.value
                            if snapshot.run.status is AutonomousRunStatus.RUNNING
                            else snapshot.run.status.value
                        ),
                        error_message=snapshot.run.last_error,
                        finished=True,
                    )
                if not self._should_retry_run(snapshot.run, attempt_number=attempt_number, attempt_budget=attempt_budget):
                    await self._maybe_generate_resolution_narrative(
                        self.get_run_detail_sync(incident_id, run_id)
                    )
                    return self.get_run_detail_sync(incident_id, run_id)

                retry_context = self._build_retry_context(snapshot.run, next_attempt_number=attempt_number + 1)
                reset_snapshot = self._runner.prepare_for_retry(
                    run_id=run_id,
                    retry_context=retry_context,
                )
                if self._autonomous_repository is not None:
                    await self._autonomous_repository.update_run(
                        run_id,
                        async_job_id=job.id,
                        project_service_id=getattr(persisted_record, "project_service_id", None),
                        repo_profile_id=reset_snapshot.run.repo_profile_id,
                        run=reset_snapshot.run.model_copy(update={"async_job_id": job.id}),
                        outcome=None,
                    )
            return self.get_run_detail_sync(incident_id, run_id)
        finally:
            _cleanup_workspace(run_id)

    async def record_sandbox_result(self, sandbox_run: SandboxRunRecord) -> None:
        if self._autonomous_repository is None:
            return
        records = await self._autonomous_repository.find_runs_by_patch_run(sandbox_run.patch_run_id)
        for record in records:
            detail = self.get_run_detail_sync(record.incident_id, record.id)
            sandbox_verification = AutonomousVerificationEvidence(
                source="sandbox",
                kind="sandbox",
                summary=sandbox_run.summary,
                passed=bool(sandbox_run.verification_succeeded),
                command=sandbox_run.verify_command,
                recorded_at=sandbox_run.updated_at,
                metadata={
                    "sandbox_run_id": sandbox_run.id,
                    "executor_backend": sandbox_run.executor_backend,
                    "reproduction_succeeded": sandbox_run.reproduction_succeeded,
                    "patch_applied": sandbox_run.patch_applied,
                },
            )
            updated_run = detail.run.model_copy(
                update={
                    "sandbox_run_id": sandbox_run.id,
                    "latest_verification": sandbox_verification,
                }
            )
            if (
                sandbox_run.status is SandboxRunStatus.SUCCEEDED
                and sandbox_run.verification_succeeded
                and sandbox_run.patch_applied
            ):
                updated_run = updated_run.model_copy(
                    update={
                        "status": AutonomousRunStatus.SUCCEEDED,
                        "phase": AutonomousRunPhase.COMPLETED,
                        "promotion_status": (
                            AutonomousPromotionStatus.READY
                            if detail.run.execution_mode is AutonomousExecutionMode.REPAIR_AND_PROPOSE
                            and detail.run.approval_status is not AutonomousApprovalStatus.REJECTED
                            else detail.run.promotion_status
                        ),
                    }
                )
            elif sandbox_run.status is SandboxRunStatus.FAILED:
                updated_run = updated_run.model_copy(
                    update={
                        "status": AutonomousRunStatus.FAILED,
                        "phase": AutonomousRunPhase.FAILED,
                        "last_error": sandbox_run.summary,
                        "promotion_status": AutonomousPromotionStatus.BLOCKED,
                    }
                )
            self._event_stream.upsert_run(updated_run)
            snapshot = self._event_stream.get_snapshot(updated_run.id)
            outcome = self._artifact_store.build_outcome(snapshot)
            self._artifact_store.persist_outcome(snapshot)
            await self._autonomous_repository.update_run(
                updated_run.id,
                async_job_id=updated_run.async_job_id,
                project_service_id=getattr(record, "project_service_id", None),
                repo_profile_id=updated_run.repo_profile_id,
                run=updated_run,
                outcome=outcome,
            )
            if (
                sandbox_run.status is SandboxRunStatus.SUCCEEDED
                and sandbox_run.verification_succeeded
                and sandbox_run.patch_applied
                and updated_run.status is AutonomousRunStatus.SUCCEEDED
            ):
                marked = await self._incident_repository.mark_resolved_by_autonomous_agent(record.incident_id)
                if marked is not None:
                    logger.info(
                        "Marked incident resolved by autonomous agent after sandbox verification",
                        extra={"incident_id": record.incident_id, "run_id": updated_run.id},
                    )
            await self._maybe_generate_resolution_narrative(
                self.get_run_detail_sync(record.incident_id, updated_run.id)
            )

    async def promote_run(self, incident_id: str, run_id: str) -> AutonomousRunDetailResponse:
        incident = await self._require_incident(incident_id)
        detail = self.get_run_detail_sync(incident_id, run_id)
        run = detail.run
        if run.approval_status is AutonomousApprovalStatus.PENDING:
            raise APIError(
                "This autonomous run still requires approval before promotion.",
                status_code=409,
                code="autonomous_run_requires_approval",
            )
        if run.sandbox_run_id is None or run.repo_profile_id is None:
            raise APIError(
                "This autonomous run does not have a verified sandbox result to promote.",
                status_code=409,
                code="autonomous_run_not_promotable",
            )
        if run.patch_run_id is None:
            raise APIError(
                "This autonomous run does not have a canonical patch artifact to promote.",
                status_code=409,
                code="autonomous_run_patch_missing",
            )
        if self._control_plane_repository is None:
            raise APIError(
                "Control-plane repository access is not configured for promotion.",
                status_code=503,
                code="promotion_unconfigured",
            )
        if self._provider_integration_service is None:
            raise APIError(
                "Provider write-back is not configured for promotion.",
                status_code=503,
                code="provider_writeback_unconfigured",
            )
        if self._patch_repository is None:
            raise APIError(
                "Patch repository access is not configured for promotion.",
                status_code=503,
                code="patch_repository_unconfigured",
            )
        repo_profile = await self._control_plane_repository.get_repo_profile(run.repo_profile_id)
        if repo_profile is None:
            raise APIError(
                f"Repo profile {run.repo_profile_id} was not found.",
                status_code=404,
                code="repo_profile_not_found",
            )
        provider_repository = await self._control_plane_repository.get_provider_repository(
            repo_profile.provider_repository_id
        )
        if provider_repository is None:
            raise APIError(
                f"Provider repository {repo_profile.provider_repository_id} was not found.",
                status_code=404,
                code="provider_repository_not_found",
            )
        patch_run = await self._patch_repository.get_patch_run(run.patch_run_id)
        if patch_run is None:
            raise APIError(
                f"Patch run {run.patch_run_id} was not found.",
                status_code=404,
                code="patch_run_not_found",
            )
        adapter = get_provider_adapter(provider_repository.provider)
        branch_name = f"{adapter.build_branch_name(incident_id=incident_id)}-{run_id[:8]}"
        writeback = await self._provider_integration_service.propose_patch_writeback(
            provider_repository_id=provider_repository.id,
            branch_name=branch_name,
            patch_diff=patch_run.unified_diff,
            title=f"Fix incident: {incident.title}",
            description=(
                f"Automated repair proposal for incident `{incident_id}`.\n\n"
                f"- Autonomous run: `{run.id}`\n"
                f"- Patch run: `{run.patch_run_id}`\n"
                f"- Sandbox run: `{run.sandbox_run_id}`"
            ),
            commit_message=f"Fix incident {incident_id}",
        )
        updated_run = run.model_copy(
            update={
                "promotion_status": AutonomousPromotionStatus.PROPOSED,
                "promotion_branch_name": writeback.branch_name,
                "promotion_url": writeback.change_request_url,
            }
        )
        self._event_stream.upsert_run(updated_run)
        if self._autonomous_repository is not None:
            persisted_record = await self._autonomous_repository.get_run(run_id)
            await self._autonomous_repository.update_run(
                run_id,
                async_job_id=updated_run.async_job_id,
                project_service_id=getattr(persisted_record, "project_service_id", None),
                repo_profile_id=updated_run.repo_profile_id,
                run=updated_run,
                outcome=detail.outcome,
            )
        return AutonomousRunDetailResponse(
            run=updated_run,
            events=detail.events,
            outcome=detail.outcome,
            artifact_paths=detail.artifact_paths,
        )

    async def _require_incident(self, incident_id: str):
        incident = await self._incident_repository.get_incident(incident_id)
        if incident is None:
            raise APIError(
                f"Incident {incident_id} was not found.",
                status_code=404,
                code="incident_not_found",
            )
        return incident

    async def _require_repo_profile(self, repo_profile_id: str):
        if self._control_plane_repository is None:
            raise APIError(
                "Control-plane repository access is not configured.",
                status_code=503,
                code="control_plane_unconfigured",
            )
        repo_profile = await self._control_plane_repository.get_repo_profile(repo_profile_id)
        if repo_profile is None:
            raise APIError(
                f"Repo profile {repo_profile_id} was not found.",
                status_code=404,
                code="repo_profile_not_found",
            )
        return repo_profile

    async def _get_active_repo_profile(self, project_id: str):
        if self._control_plane_repository is None:
            return None
        return await self._control_plane_repository.get_active_repo_profile(project_id)

    async def _clone_connected_repo(
        self,
        *,
        incident_id: str,
        provider_repository,
    ) -> Path:
        from services.provider_clients import get_provider_client

        integration = await self._control_plane_repository.get_provider_integration(
            provider_repository.provider_integration_id
        )
        if integration is None:
            raise APIError(
                "No provider integration found for this repository.",
                status_code=404,
                code="provider_integration_not_found",
            )
        client = get_provider_client(integration.provider)
        sandbox_access = await client.build_sandbox_access(
            integration,
            provider_repository,
        )
        clone_url = sandbox_access.secret_value if sandbox_access else provider_repository.clone_url
        return _prepare_repository_workspace(
            run_id=incident_id,
            clone_url=clone_url,
            default_branch=provider_repository.default_branch,
        )

    async def _resolve_incident_service_context(self, incident_id: str) -> ResolvedAutonomousServiceContext:
        incident = await self._require_incident(incident_id)
        if self._control_plane_repository is None:
            return ResolvedAutonomousServiceContext(
                incident=incident,
                project_service=None,
                repo_profile=None,
                project_policy=None,
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
        if project_service is not None and repo_profile is not None and (
            incident.project_service_id != project_service.id or incident.repo_profile_id != repo_profile.id
        ):
            incident = await self._incident_repository.resolve_incident_service(
                incident.id,
                project_service_id=project_service.id,
                repo_profile_id=repo_profile.id,
            )
        project_policy = (
            await self._control_plane_repository.get_or_create_project_policy(incident.project_id)
            if hasattr(self._control_plane_repository, "get_or_create_project_policy")
            else None
        )
        return ResolvedAutonomousServiceContext(
            incident=incident,
            project_service=project_service,
            repo_profile=repo_profile,
            project_policy=project_policy,
        )

    def _derive_feature_seeds(
        self,
        *,
        incident,
        repo_profile,
        requested_mode: AutonomousExecutionMode,
        browser_verification_supported: bool,
    ) -> list[FeatureSeed]:
        required_verification = [VerificationKind.INTEGRATION]
        browser_required = False
        verification_method = "Run the configured verification command."
        if browser_verification_supported:
            required_verification = [VerificationKind.BROWSER]
            browser_required = True
            verification_method = "Start the application and verify the repaired flow in a browser."
        elif requested_mode is AutonomousExecutionMode.INVESTIGATE_ONLY:
            required_verification = []
            verification_method = "Collect evidence without modifying or promoting code."
        description = (
            repo_profile.success_criteria
            if repo_profile is not None and repo_profile.success_criteria
            else f"The incident '{incident.title}' should no longer reproduce, and verification should succeed."
        )
        notes = []
        if repo_profile is not None:
            notes.append(f"Reproduce with: {repo_profile.reproduce_command}")
            notes.append(f"Verify with: {repo_profile.verify_command}")
        return [
            FeatureSeed(
                feature_name=incident.title,
                description=description,
                verification_method=verification_method,
                reproduction_command=repo_profile.reproduce_command if repo_profile is not None else None,
                verification_command=repo_profile.verify_command if repo_profile is not None else None,
                required_verification=required_verification,
                browser_required=browser_required,
                notes=notes,
            )
        ]

    def _supports_browser_verification(self, repository_profile) -> bool:
        return bool(repository_profile.browser_verification_entrypoints)

    def _hydrate_event_stream(self, detail: AutonomousRunDetailResponse) -> None:
        if self._event_stream.has_run(detail.run.id):
            return
        self._event_stream.upsert_run(detail.run)
        for event in detail.events:
            self._event_stream.append_event(event)

    _NON_CODE_FILENAMES = frozenset({
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Pipfile.lock",
        "Gemfile.lock",
        "composer.lock",
    })
    _LOCKFILE_MANIFESTS = {
        "package-lock.json": frozenset({"package.json"}),
        "yarn.lock": frozenset({"package.json"}),
        "pnpm-lock.yaml": frozenset({"package.json"}),
        "poetry.lock": frozenset({"pyproject.toml", "poetry.toml"}),
        "Pipfile.lock": frozenset({"Pipfile"}),
        "Gemfile.lock": frozenset({"Gemfile", "gems.rb"}),
        "composer.lock": frozenset({"composer.json"}),
    }

    async def _postprocess_completed_run(self, snapshot: AutonomousRunSnapshot) -> AutonomousRunSnapshot:
        run = snapshot.run
        if (
            run.status is not AutonomousRunStatus.SUCCEEDED
            or run.execution_mode is AutonomousExecutionMode.INVESTIGATE_ONLY
            or self._patch_repository is None
            or self._sandbox_verification_service is None
        ):
            return snapshot
        checkpoint_ref = run.loop_state.checkpoint_ref
        if checkpoint_ref is None:
            return snapshot

        diff_result = GitCheckpointManager().diff_since_checkpoint(
            repository_root=run.repository_root,
            checkpoint_ref=checkpoint_ref,
        )
        diff = diff_result.diff
        if diff is None or not diff.patch.strip():
            return snapshot

        selected_changes = self._select_sandbox_patch_files(diff.changed_files)
        code_changes = [
            f for f in selected_changes
            if f.path.rsplit("/", 1)[-1] not in self._NON_CODE_FILENAMES
        ]
        if not code_changes:
            logger.info(
                "Skipping sandbox verification — diff only contains lockfile/metadata changes: %s",
                [f.path for f in diff.changed_files],
            )
            return snapshot

        selected_paths = [changed_file.path for changed_file in selected_changes]
        selected_diff_result = GitCheckpointManager().diff_since_checkpoint(
            repository_root=run.repository_root,
            checkpoint_ref=checkpoint_ref,
            paths=selected_paths,
        )
        selected_diff = selected_diff_result.diff
        patch_diff = selected_diff.patch if selected_diff is not None else ""
        if not patch_diff.strip():
            return snapshot
        # region agent log
        with open("/Users/connor/Desktop/StimpactAi/.cursor/debug-31f43d.log", "a", encoding="utf-8") as debug_log:
            debug_log.write(json.dumps({"sessionId": "31f43d", "runId": str(run.id), "hypothesisId": "H1", "location": "agent-platform/services/autonomous_runs.py:994", "message": "autonomous run prepared sandbox patch", "data": {"checkpointRef": checkpoint_ref, "repositoryRoot": str(run.repository_root), "basedOnCommitSha": diff_result.branch_info.head_sha if diff_result.branch_info is not None else None, "changedFiles": [changed_file.path for changed_file in diff.changed_files], "selectedFiles": selected_paths, "codeTargetFiles": [changed_file.path for changed_file in code_changes], "diffFileCount": len(selected_changes), "patchLineCount": sum(1 for line in patch_diff.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))), "patchHeader": patch_diff.splitlines()[:12]}, "timestamp": int(datetime.now(UTC).timestamp() * 1000)}) + "\n")
        # endregion

        patch_proposal = PatchProposal(
            patch_summary="Autonomous repair candidate generated from the harness working tree.",
            rationale="The autonomous harness produced a diff relative to its last known good checkpoint.",
            target_files=[
                PatchTargetFile(
                    path=changed_file.path,
                    reason=f"Autonomous harness modified this file as part of the repair attempt ({changed_file.status.value}).",
                )
                for changed_file in selected_changes
            ],
            unified_diff=patch_diff,
            verification_steps=["Run the configured sandbox reproduce and verify commands."],
            confidence=0.9,
        )
        patch_run = await self._patch_repository.create_patch_run(
            incident_id=run.incident_id or "",
            repo_profile_id=run.repo_profile_id,
            proposal=patch_proposal,
            model_name="autonomous-harness",
            based_on_commit_sha=diff_result.branch_info.head_sha if diff_result.branch_info is not None else None,
            diff_line_count=sum(1 for line in patch_diff.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))),
            file_count=max(1, len(selected_changes)),
        )
        sandbox_run, _job = await self._sandbox_verification_service.queue_sandbox_run(
            run.incident_id or "",
            event_limit=50,
            refresh_patch=False,
            patch_run_id=patch_run.id,
            repository_root=run.repository_root,
            baseline_commit_sha=patch_run.based_on_commit_sha,
            repository_branch=diff_result.branch_info.branch_name if diff_result.branch_info is not None else None,
            repository_upstream_branch=(
                diff_result.branch_info.upstream_branch if diff_result.branch_info is not None else None
            ),
        )
        # region agent log
        with open("/Users/connor/Desktop/StimpactAi/.cursor/debug-31f43d.log", "a", encoding="utf-8") as debug_log:
            debug_log.write(json.dumps({"sessionId": "31f43d", "runId": str(run.id), "hypothesisId": "H2", "location": "agent-platform/services/autonomous_runs.py:1030", "message": "autonomous run queued sandbox verification", "data": {"patchRunId": str(patch_run.id), "sandboxRunId": str(sandbox_run.id), "repositoryRoot": str(run.repository_root), "baselineCommitSha": patch_run.based_on_commit_sha, "repositoryBranch": diff_result.branch_info.branch_name if diff_result.branch_info is not None else None, "repositoryUpstreamBranch": diff_result.branch_info.upstream_branch if diff_result.branch_info is not None else None}, "timestamp": int(datetime.now(UTC).timestamp() * 1000)}) + "\n")
        # endregion
        updated_run = run.model_copy(
            update={
                "patch_run_id": patch_run.id,
                "sandbox_run_id": sandbox_run.id,
                "status": AutonomousRunStatus.RUNNING,
                "phase": AutonomousRunPhase.VERIFICATION,
                "promotion_status": AutonomousPromotionStatus.NOT_REQUESTED,
            }
        )
        self._event_stream.upsert_run(updated_run)
        if self._autonomous_repository is not None:
            persisted_record = await self._autonomous_repository.get_run(run.id)
            outcome = self._artifact_store.get_outcome(run.incident_id or "", run.id)
            await self._autonomous_repository.update_run(
                run.id,
                async_job_id=updated_run.async_job_id,
                project_service_id=getattr(persisted_record, "project_service_id", None),
                repo_profile_id=updated_run.repo_profile_id,
                run=updated_run,
                outcome=outcome,
            )
        return self._event_stream.get_snapshot(run.id)

    def _select_sandbox_patch_files(self, changed_files: list[GitChangedFile]) -> list[GitChangedFile]:
        changed_paths = {changed_file.path for changed_file in changed_files}
        selected_changes: list[GitChangedFile] = []
        for changed_file in changed_files:
            filename = changed_file.path.rsplit("/", 1)[-1]
            related_manifests = self._LOCKFILE_MANIFESTS.get(filename)
            if related_manifests is not None and not any(manifest in changed_paths for manifest in related_manifests):
                continue
            selected_changes.append(changed_file)
        return selected_changes

    def _should_retry_run(
        self,
        run: AutonomousRepairRunRecord,
        *,
        attempt_number: int,
        attempt_budget: int,
    ) -> bool:
        if run.status is not AutonomousRunStatus.FAILED:
            return False
        if attempt_number >= attempt_budget:
            return False
        failure_class = self._failure_class_for_run(run)
        if failure_class in {
            AutonomousToolFailureClass.VALIDATION,
            AutonomousToolFailureClass.TOOL_ERROR,
            AutonomousToolFailureClass.EXCEPTION,
            AutonomousToolFailureClass.STAGNATION,
        }:
            return True
        if self._is_retryable_patch_apply_failure(run):
            return True
        if self._is_retryable_sandbox_failure(run):
            return True
        return False

    def _failure_class_for_run(self, run: AutonomousRepairRunRecord) -> AutonomousToolFailureClass | None:
        if run.loop_state.last_failure is not None:
            return run.loop_state.last_failure.failure_class
        message = (run.last_error or "").strip().lower()
        if not message:
            return None
        if any(marker in message for marker in ("validation error", "input should", "field required", "less than or equal")):
            return AutonomousToolFailureClass.VALIDATION
        if "decision engine failed" in message or "automatic baseline checkpoint failed" in message:
            return AutonomousToolFailureClass.EXCEPTION
        if "tool execution failed" in message:
            return AutonomousToolFailureClass.TOOL_ERROR
        if "exceeded the max step budget" in message:
            return AutonomousToolFailureClass.STAGNATION
        if "verification" in message:
            return AutonomousToolFailureClass.VERIFICATION
        return None

    def _build_retry_context(
        self,
        run: AutonomousRepairRunRecord,
        *,
        next_attempt_number: int,
    ) -> dict[str, object]:
        failure_class = self._failure_class_for_run(run)
        return {
            "next_attempt_number": next_attempt_number,
            "previous_error": run.last_error,
            "previous_failure_class": failure_class.value if failure_class is not None else None,
            "previous_tool_name": run.loop_state.last_tool_name,
            "previous_verification_summary": (
                run.latest_verification.summary if run.latest_verification is not None else None
            ),
            "previous_verification_passed": (
                run.latest_verification.passed if run.latest_verification is not None else None
            ),
            "previous_patch_applied": self._latest_verification_bool(run, "patch_applied"),
            "previous_reproduction_succeeded": self._latest_verification_bool(
                run,
                "reproduction_succeeded",
            ),
            "retry_driver": self._retry_driver_label(run, failure_class),
        }

    @staticmethod
    def _latest_verification_bool(
        run: AutonomousRepairRunRecord,
        key: str,
    ) -> bool | None:
        if run.latest_verification is None:
            return None
        value = run.latest_verification.metadata.get(key)
        return value if isinstance(value, bool) else None

    def _is_retryable_patch_apply_failure(self, run: AutonomousRepairRunRecord) -> bool:
        verification = run.latest_verification
        if verification is None:
            return False
        patch_applied = self._latest_verification_bool(run, "patch_applied")
        reproduction_succeeded = self._latest_verification_bool(
            run,
            "reproduction_succeeded",
        )
        summary = verification.summary.lower()
        message = (run.last_error or "").lower()
        return bool(
            patch_applied is False
            and reproduction_succeeded is True
            and (
                "patch" in summary
                or "patch" in message
                or "apply" in summary
                or "apply" in message
            )
        )

    def _is_retryable_sandbox_failure(self, run: AutonomousRepairRunRecord) -> bool:
        summary = (
            run.latest_verification.summary.lower()
            if run.latest_verification is not None
            else ""
        )
        message = (run.last_error or "").lower()
        retryable_markers = (
            "sandbox install step failed before reproduction",
            "sandbox failed to restore the requested baseline before verification",
            "timed out",
            "timeout",
        )
        blocked_markers = (
            "repository root does not exist",
            "not a git checkout",
            "no active repo profile",
            "policy",
        )
        if any(marker in summary or marker in message for marker in blocked_markers):
            return False
        return any(marker in summary or marker in message for marker in retryable_markers)

    def _retry_driver_label(
        self,
        run: AutonomousRepairRunRecord,
        failure_class: AutonomousToolFailureClass | None,
    ) -> str:
        if self._is_retryable_patch_apply_failure(run):
            return "patch_apply_recovery"
        if self._is_retryable_sandbox_failure(run):
            return "sandbox_recovery"
        return failure_class.value if failure_class is not None else "unknown"

    def _policy_block_reason(self, policy) -> str | None:
        if policy.auto_run_allowed:
            return None
        reasons = [reason.strip() for reason in policy.reasons if reason.strip()]
        if not reasons:
            return "Autonomous execution is currently blocked by policy."
        return " ".join(reasons)

    async def _maybe_generate_resolution_narrative(
        self,
        detail: AutonomousRunDetailResponse,
    ) -> AutonomousRunOutcome | None:
        if (
            self._resolution_narrative_service is None
            or detail.outcome is None
            or detail.run.incident_id is None
            or detail.run.status is not AutonomousRunStatus.SUCCEEDED
            or not detail.outcome.fresh_verification_satisfied
            or detail.outcome.root_cause_explanation is not None
        ):
            return detail.outcome

        try:
            root_cause_explanation, solution_description = await self._resolution_narrative_service.build(
                incident_id=detail.run.incident_id,
                detail=detail,
            )
        except Exception:
            logger.warning(
                "Resolution narrative generation failed; continuing without narrative.",
                exc_info=True,
                extra={"incident_id": detail.run.incident_id, "run_id": detail.run.id},
            )
            return detail.outcome
        updated_outcome = detail.outcome.model_copy(
            update={
                "root_cause_explanation": root_cause_explanation,
                "solution_description": solution_description,
                "narrative_generated_at": datetime.now(UTC),
            }
        )
        self._artifact_store.write_outcome(detail.run.incident_id, detail.run.id, updated_outcome)
        if self._autonomous_repository is not None:
            persisted_record = await self._autonomous_repository.get_run(detail.run.id)
            await self._autonomous_repository.update_run(
                detail.run.id,
                async_job_id=detail.run.async_job_id,
                project_service_id=getattr(persisted_record, "project_service_id", None),
                repo_profile_id=detail.run.repo_profile_id,
                run=detail.run,
                outcome=updated_outcome,
            )
        return updated_outcome

    def _build_resolution_narrative_service(self) -> ResolutionNarrativeService | None:
        api_key = get_openai_api_key()
        if api_key is None or self._patch_repository is None:
            return None
        root_cause_client = AsyncOpenAI(api_key=api_key)
        return ResolutionNarrativeService(
            self._incident_repository,
            patch_repository=self._patch_repository,
            root_cause_service=RootCauseAnalysisService(
                self._incident_repository,
                classifier=FailureClassifier(),
                analyzer=RootCauseAnalyzer(),
                reasoner=RootCauseReasoner(
                    client=root_cause_client,
                    model=get_openai_rca_model(),
                ),
            ),
            client=AsyncOpenAI(api_key=api_key),
            model=get_openai_autonomous_model(),
        )

    def _build_decision_engine(self) -> OpenAIAutonomousDecisionEngine:
        api_key = get_openai_api_key()
        if api_key is None:
            raise APIError(
                "OPENAI_API_KEY is not configured for autonomous runs.",
                status_code=503,
                code="openai_unconfigured",
            )
        return OpenAIAutonomousDecisionEngine(client=AsyncOpenAI(api_key=api_key))
