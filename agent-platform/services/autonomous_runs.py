from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from openai import AsyncOpenAI

from api.core.config import get_openai_api_key, get_repository_root
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
    AutonomousPromotionStatus,
    AutonomousRepairRunRecord,
    AutonomousRunPhase,
    AutonomousRunStatus,
    AutonomousRunSnapshot,
    AutonomousVerificationEvidence,
)
from harness.schemas.initializer import FeatureSeed
from harness.schemas.verification import VerificationKind
from models.async_job import AsyncJobStatus, AsyncJobType
from models.patch import PatchProposal, PatchTargetFile
from models.sandbox import SandboxRunRecord, SandboxRunStatus
from services.autonomous_policy import AutonomousPolicyService
from services.harness_profile_adapter import HarnessControlPlaneProfileAdapter
from services.provider_integration_service import ProviderIntegrationService
from services.repository_provider import get_provider_adapter
from services.sandbox_verification import SandboxVerificationService


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

    async def start_run(
        self,
        incident_id: str,
        request: AutonomousRunCreateRequest,
    ) -> AutonomousRunDetailResponse:
        incident = await self._require_incident(incident_id)
        repo_profile = await self._get_active_repo_profile(incident.project_id)
        feature_seeds = request.feature_seeds or self._derive_feature_seeds(
            incident=incident,
            repo_profile=repo_profile,
            requested_mode=request.execution_mode,
        )
        policy, approval_status = self._policy_service.evaluate(
            incident=incident,
            repo_profile=repo_profile,
            request=request,
        )
        repository_root = request.repository_root or str(self._repository_root)
        repository_profile_override = self._profile_adapter.build_profile(
            repository_root=repository_root,
            repo_profile=repo_profile,
        )
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
                "repo_profile_id": repo_profile.id if repo_profile is not None else None,
                "execution_mode": request.execution_mode,
                "approval_status": approval_status,
                "benchmark_scenario_id": request.benchmark_scenario_id,
                "benchmark_bug_class": request.benchmark_bug_class,
                "policy": policy,
                "loop_state": snapshot.run.loop_state.model_copy(update={"max_steps": request.max_steps}),
            }
        )
        self._event_stream.upsert_run(run)

        async_job_id = None
        if (
            approval_status is AutonomousApprovalStatus.NOT_REQUIRED
            and policy.auto_run_allowed
            and self._async_job_repository is not None
        ):
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
        repository_profile_override = (
            self._profile_adapter.build_profile(
                repository_root=detail.run.repository_root,
                repo_profile=repo_profile,
            )
            if repo_profile is not None
            else None
        )
        ensured_snapshot = self._runner.ensure_sessions(
            run_id=run_id,
            repository_root=detail.run.repository_root,
            objective=detail.run.objective,
            initializer_summary=(
                persisted_record.initializer_summary
                if persisted_record is not None
                else "Prepare the repository, verification state, and repair context for autonomous incident resolution."
            ),
            repository_profile_override=repository_profile_override,
            feature_seeds=persisted_record.feature_seeds if persisted_record is not None else [],
        )
        active_run = ensured_snapshot.run
        if self._autonomous_repository is not None:
            await self._autonomous_repository.create_attempt(
                autonomous_run_id=run_id,
                async_job_id=job.id,
                attempt_number=job.attempts,
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
                repo_profile_id=snapshot.run.repo_profile_id,
                run=snapshot.run.model_copy(update={"async_job_id": job.id}),
                outcome=outcome,
            )
            await self._autonomous_repository.create_attempt(
                autonomous_run_id=run_id,
                async_job_id=job.id,
                attempt_number=job.attempts,
                status=job.status.value if snapshot.run.status is AutonomousRunStatus.RUNNING else snapshot.run.status.value,
                error_message=snapshot.run.last_error,
                finished=True,
            )
        return self.get_run_detail_sync(incident_id, run_id)

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
                repo_profile_id=updated_run.repo_profile_id,
                run=updated_run,
                outcome=outcome,
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
            await self._autonomous_repository.update_run(
                run_id,
                async_job_id=updated_run.async_job_id,
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

    def _derive_feature_seeds(
        self,
        *,
        incident,
        repo_profile,
        requested_mode: AutonomousExecutionMode,
    ) -> list[FeatureSeed]:
        required_verification = [VerificationKind.INTEGRATION]
        browser_required = False
        verification_method = "Run the configured verification command."
        if repo_profile is not None and repo_profile.startup_commands:
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

    def _hydrate_event_stream(self, detail: AutonomousRunDetailResponse) -> None:
        if self._event_stream.has_run(detail.run.id):
            return
        self._event_stream.upsert_run(detail.run)
        for event in detail.events:
            self._event_stream.append_event(event)

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

        patch_proposal = PatchProposal(
            patch_summary="Autonomous repair candidate generated from the harness working tree.",
            rationale="The autonomous harness produced a diff relative to its last known good checkpoint.",
            target_files=[
                PatchTargetFile(
                    path=changed_file.path,
                    reason=f"Autonomous harness modified this file as part of the repair attempt ({changed_file.status.value}).",
                )
                for changed_file in diff.changed_files
            ],
            unified_diff=diff.patch,
            verification_steps=["Run the configured sandbox reproduce and verify commands."],
            confidence=0.9,
        )
        patch_run = await self._patch_repository.create_patch_run(
            incident_id=run.incident_id or "",
            repo_profile_id=run.repo_profile_id,
            proposal=patch_proposal,
            model_name="autonomous-harness",
            based_on_commit_sha=diff_result.branch_info.head_sha if diff_result.branch_info is not None else None,
            diff_line_count=sum(1 for line in diff.patch.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))),
            file_count=max(1, len(diff.changed_files)),
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
            outcome = self._artifact_store.get_outcome(run.incident_id or "", run.id)
            await self._autonomous_repository.update_run(
                run.id,
                async_job_id=updated_run.async_job_id,
                repo_profile_id=updated_run.repo_profile_id,
                run=updated_run,
                outcome=outcome,
            )
        return self._event_stream.get_snapshot(run.id)

    def _build_decision_engine(self) -> OpenAIAutonomousDecisionEngine:
        api_key = get_openai_api_key()
        if api_key is None:
            raise APIError(
                "OPENAI_API_KEY is not configured for autonomous runs.",
                status_code=503,
                code="openai_unconfigured",
            )
        return OpenAIAutonomousDecisionEngine(client=AsyncOpenAI(api_key=api_key))
