from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from harness.autonomous.decision_engine import AutonomousDecisionEngine
from harness.autonomous.events import InMemoryAutonomousRunEventStream
from harness.git_ops.checkpoints import GitCheckpointManager
from harness.orchestrator.service import HarnessSessionOrchestrator
from harness.schemas.autonomous import (
    AutonomousDecision,
    AutonomousDecisionAction,
    AutonomousExecutionMode,
    AutonomousEventType,
    AutonomousPromotionStatus,
    AutonomousRepairRunRecord,
    AutonomousRunEvent,
    AutonomousToolFailure,
    AutonomousToolFailureClass,
    AutonomousRunPhase,
    AutonomousRunSnapshot,
    AutonomousRunStatus,
    AutonomousVerificationEvidence,
)
from harness.schemas.initializer import FeatureSeed
from harness.schemas.orchestrator import (
    GenerateInitializerOutputRequest,
    OrchestratorSessionStartRequest,
    ToolInvocationRequest,
)
from harness.schemas.profile import HarnessRepositoryProfile
from harness.schemas.runtime import HarnessAgentRole
from harness.schemas.verification import VerificationKind, VerificationStatus


class AutonomousRepairRunner:
    _RECENT_EVENT_LIMIT = 8
    _RECENT_TOOL_HISTORY_LIMIT = 12
    _MAX_EXCEPTION_RECOVERIES = 2
    _MAX_CONSECUTIVE_FAILURES = 4
    _MAX_STAGNATION_BEFORE_RECOVERY = 2
    _EVENT_SUMMARY_LIMIT = 1_000
    _RUN_ERROR_LIMIT = 4_000

    def __init__(
        self,
        *,
        orchestrator: HarnessSessionOrchestrator | None = None,
        event_stream: InMemoryAutonomousRunEventStream | None = None,
    ) -> None:
        self._orchestrator = orchestrator or HarnessSessionOrchestrator()
        self._event_stream = event_stream or InMemoryAutonomousRunEventStream()

    def bootstrap_run(
        self,
        *,
        incident_id: str | None = None,
        async_job_id: str | None = None,
        repo_profile_id: str | None = None,
        repository_root: str,
        objective: str,
        initializer_summary: str,
        execution_mode=None,
        approval_status=None,
        promotion_status=None,
        policy=None,
        repository_profile_override: HarnessRepositoryProfile | None = None,
        feature_seeds: list[FeatureSeed] | None = None,
    ) -> AutonomousRunSnapshot:
        now = datetime.now(UTC)
        run_id = str(uuid4())
        run = AutonomousRepairRunRecord(
            id=run_id,
            incident_id=incident_id,
            async_job_id=async_job_id,
            repo_profile_id=repo_profile_id,
            repository_root=repository_root,
            objective=objective,
            status=AutonomousRunStatus.RUNNING,
            phase=AutonomousRunPhase.INITIALIZER,
            execution_mode=execution_mode or AutonomousRepairRunRecord.model_fields["execution_mode"].default,
            approval_status=approval_status or AutonomousRepairRunRecord.model_fields["approval_status"].default,
            promotion_status=promotion_status or AutonomousRepairRunRecord.model_fields["promotion_status"].default,
            policy=policy or AutonomousRepairRunRecord.model_fields["policy"].default_factory(),
            created_at=now,
            updated_at=now,
        )
        self._persist_run(run)
        self._emit_event(
            run_id=run_id,
            event_type=AutonomousEventType.RUN_STARTED,
            phase=run.phase,
            summary="Autonomous repair run started.",
            decision=AutonomousDecision(
                summary="Bootstrap initializer and coding sessions before autonomous tool selection begins.",
                rationale="The runner must load the repo profile, generate initializer artifacts, and hand off a coding-ready context.",
            ),
            payload={"repository_root": repository_root, "objective": objective},
        )

        initializer_snapshot = self._orchestrator.initialize_session(
            OrchestratorSessionStartRequest(
                role=HarnessAgentRole.INITIALIZER,
                repository_root=repository_root,
                objective=objective,
                repository_profile_override=repository_profile_override,
            )
        )
        run = run.model_copy(
            update={
                "initializer_session_id": initializer_snapshot.session.id,
                "updated_at": datetime.now(UTC),
            }
        )
        self._persist_run(run)
        self._emit_event(
            run_id=run_id,
            event_type=AutonomousEventType.SESSION_INITIALIZED,
            phase=run.phase,
            summary="Initializer session created.",
            payload={"session_id": initializer_snapshot.session.id, "role": HarnessAgentRole.INITIALIZER.value},
        )

        initializer_output = self._orchestrator.generate_initializer_output(
            initializer_snapshot.session.id,
            GenerateInitializerOutputRequest(
                summary=initializer_summary,
                feature_seeds=feature_seeds or [],
            ),
        )
        self._emit_event(
            run_id=run_id,
            event_type=AutonomousEventType.INITIALIZER_OUTPUT_GENERATED,
            phase=run.phase,
            summary="Initializer output generated.",
            payload={
                "feature_count": len(initializer_output.feature_catalog.features),
                "recommended_commands": initializer_output.recommended_commands,
            },
        )

        persisted_initializer = self._orchestrator.persist_initializer_output(
            initializer_snapshot.session.id,
            initializer_output,
        )
        self._emit_event(
            run_id=run_id,
            event_type=AutonomousEventType.INITIALIZER_OUTPUT_PERSISTED,
            phase=run.phase,
            summary="Initializer artifacts persisted to disk.",
            payload={
                "init_script_path": initializer_output.init_script.path,
                "feature_catalog_path": ".stimpactai/features.json",
                "feature_ids": [feature.id for feature in persisted_initializer.feature_catalog.features]
                if persisted_initializer.feature_catalog is not None
                else [],
            },
        )

        run = run.model_copy(update={"phase": AutonomousRunPhase.CODING, "updated_at": datetime.now(UTC)})
        self._persist_run(run)
        self._emit_event(
            run_id=run_id,
            event_type=AutonomousEventType.PHASE_CHANGED,
            phase=run.phase,
            summary="Run moved into coding phase.",
            payload={"phase": run.phase.value},
        )

        coding_snapshot = self._orchestrator.initialize_session(
            OrchestratorSessionStartRequest(
                role=HarnessAgentRole.CODING,
                repository_root=repository_root,
                objective=objective,
                initializer_session_id=initializer_snapshot.session.id,
                repository_profile_override=repository_profile_override,
            )
        )
        run = run.model_copy(
            update={
                "coding_session_id": coding_snapshot.session.id,
                "updated_at": datetime.now(UTC),
            }
        )
        self._persist_run(run)
        self._emit_event(
            run_id=run_id,
            event_type=AutonomousEventType.CODING_SESSION_READY,
            phase=run.phase,
            summary="Coding session is ready for autonomous decisions.",
            payload={
                "session_id": coding_snapshot.session.id,
                "available_tools": [tool.name for tool in coding_snapshot.available_tools.tools],
                "feature_ids": [feature.id for feature in coding_snapshot.feature_catalog.features]
                if coding_snapshot.feature_catalog is not None
                else [],
            },
        )

        return self._event_stream.get_snapshot(run_id)

    def get_snapshot(self, run_id: str) -> AutonomousRunSnapshot:
        return self._event_stream.get_snapshot(run_id)

    def ensure_sessions(
        self,
        *,
        run_id: str,
        repository_root: str,
        objective: str,
        initializer_summary: str,
        repository_profile_override: HarnessRepositoryProfile | None = None,
        feature_seeds: list[FeatureSeed] | None = None,
    ) -> AutonomousRunSnapshot:
        run = self.get_snapshot(run_id).run
        if run.initializer_session_id is not None and run.coding_session_id is not None:
            try:
                self._orchestrator.restore_session(run.initializer_session_id)
                self._orchestrator.restore_session(run.coding_session_id)
                return self.get_snapshot(run_id)
            except KeyError:
                pass

        initializer_snapshot = self._orchestrator.initialize_session(
            OrchestratorSessionStartRequest(
                role=HarnessAgentRole.INITIALIZER,
                repository_root=repository_root,
                objective=objective,
                repository_profile_override=repository_profile_override,
            )
        )
        run = run.model_copy(
            update={
                "initializer_session_id": initializer_snapshot.session.id,
                "updated_at": datetime.now(UTC),
            }
        )
        self._persist_run(run)
        self._emit_event(
            run_id=run_id,
            event_type=AutonomousEventType.SESSION_INITIALIZED,
            phase=run.phase,
            summary="Initializer session restored for async execution.",
            payload={"session_id": initializer_snapshot.session.id, "role": HarnessAgentRole.INITIALIZER.value},
        )

        initializer_output = self._orchestrator.generate_initializer_output(
            initializer_snapshot.session.id,
            GenerateInitializerOutputRequest(
                summary=initializer_summary,
                feature_seeds=feature_seeds or [],
            ),
        )
        self._orchestrator.persist_initializer_output(
            initializer_snapshot.session.id,
            initializer_output,
        )

        coding_snapshot = self._orchestrator.initialize_session(
            OrchestratorSessionStartRequest(
                role=HarnessAgentRole.CODING,
                repository_root=repository_root,
                objective=objective,
                initializer_session_id=initializer_snapshot.session.id,
                repository_profile_override=repository_profile_override,
            )
        )
        run = run.model_copy(
            update={
                "coding_session_id": coding_snapshot.session.id,
                "updated_at": datetime.now(UTC),
            }
        )
        self._persist_run(run)
        self._emit_event(
            run_id=run_id,
            event_type=AutonomousEventType.CODING_SESSION_READY,
            phase=run.phase,
            summary="Coding session restored for async execution.",
            payload={
                "session_id": coding_snapshot.session.id,
                "available_tools": [tool.name for tool in coding_snapshot.available_tools.tools],
                "feature_ids": [feature.id for feature in coding_snapshot.feature_catalog.features]
                if coding_snapshot.feature_catalog is not None
                else [],
            },
        )
        return self.get_snapshot(run_id)

    async def run_until_stop(
        self,
        *,
        incident_id: str | None = None,
        repository_root: str,
        objective: str,
        initializer_summary: str,
        decision_engine: AutonomousDecisionEngine,
        repository_profile_override: HarnessRepositoryProfile | None = None,
        feature_seeds: list[FeatureSeed] | None = None,
        max_steps: int = 20,
    ) -> AutonomousRunSnapshot:
        snapshot = self.bootstrap_run(
            incident_id=incident_id,
            repository_root=repository_root,
            objective=objective,
            initializer_summary=initializer_summary,
            repository_profile_override=repository_profile_override,
            feature_seeds=feature_seeds,
        )
        return await self.continue_run(
            run_id=snapshot.run.id,
            decision_engine=decision_engine,
            max_steps=max_steps,
        )

    async def continue_run(
        self,
        *,
        run_id: str,
        decision_engine: AutonomousDecisionEngine,
        max_steps: int = 20,
    ) -> AutonomousRunSnapshot:
        run = self.get_snapshot(run_id).run
        updated_loop_state = run.loop_state.model_copy(update={"max_steps": max_steps})
        self._persist_run(run.model_copy(update={"loop_state": updated_loop_state, "updated_at": datetime.now(UTC)}))
        baseline_checkpoint_failed = self._ensure_baseline_checkpoint(run_id)
        if baseline_checkpoint_failed is not None:
            return baseline_checkpoint_failed

        self._auto_install_dependencies(run_id)

        for step_index in range(1, max_steps + 1):
            current_snapshot = self.get_snapshot(run_id)
            run = current_snapshot.run
            if self._ready_for_automatic_completion(run):
                return self._complete_run(run_id)
            coding_session_id = run.coding_session_id
            if coding_session_id is None:
                return self._fail_run(run_id, "Coding session was not initialized.")

            coding_snapshot = self._orchestrator.restore_session(coding_session_id)
            try:
                decision = await decision_engine.decide(
                    run=run,
                    coding_session=coding_snapshot,
                    available_tools=[tool.model_dump(mode="json") for tool in coding_snapshot.available_tools.tools],
                    last_tool_result=run.loop_state.last_tool_result or None,
                    recent_events=self._scope_recent_events_to_current_session(
                        current_snapshot.events,
                        coding_session_id,
                        self._RECENT_EVENT_LIMIT,
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                return self._fail_run(run_id, f"Decision engine failed: {exc}")
            self._emit_event(
                run_id=run_id,
                event_type=AutonomousEventType.DECISION_MADE,
                phase=self._phase_for_decision(decision),
                summary=decision.summary,
                decision=decision,
                payload={"step_index": step_index},
            )

            if decision.action is AutonomousDecisionAction.COMPLETE:
                if self._all_features_verified(coding_snapshot):
                    requires_code_change = self._repair_mode_requires_code_change(run)
                    has_changes = self._has_changes_since_checkpoint(run)
                    has_fresh_evidence = self._has_fresh_verification_evidence(run)
                    if requires_code_change and (not has_changes or not has_fresh_evidence):
                        if self._can_invalidate_stale_verification(run, step_index):
                            self._invalidate_feature_catalog(
                                run_id=run_id,
                                coding_session_id=coding_session_id,
                                reason=(
                                    "no_diff_since_checkpoint"
                                    if not has_changes
                                    else "no_fresh_verification_evidence"
                                ),
                            )
                            continue
                        if self._reject_and_continue_on_premature_completion(
                            run_id=run_id,
                            run=run,
                            reason=(
                                "no_diff_since_checkpoint"
                                if not has_changes
                                else "no_fresh_verification_evidence"
                            ),
                        ):
                            continue
                        if not has_changes:
                            return self._fail_run(
                                run_id,
                                "Autonomous repair cannot complete without producing a code change relative to the baseline checkpoint.",
                            )
                        return self._fail_run(
                            run_id,
                            "Autonomous repair cannot complete without fresh verification evidence from an explicit post-fix verification step.",
                        )
                    return self._complete_run(run_id)
                if self._reject_and_continue_on_premature_completion(
                    run_id=run_id,
                    run=run,
                    reason="features_not_yet_verified",
                ):
                    continue
                return self._fail_run(
                    run_id,
                    "Decision engine repeatedly attempted to complete the run before verification requirements were satisfied.",
                )

            if decision.action is AutonomousDecisionAction.FAIL:
                return self._fail_run(run_id, decision.summary)

            if not decision.selected_tool:
                return self._fail_run(run_id, "Decision engine selected invoke_tool without a tool name.")

            try:
                invocation_result = self._execute_decision_tool(
                    run_id=run_id,
                    run=run,
                    decision=decision,
                )
            except Exception as exc:  # noqa: BLE001
                recovered = self._recover_from_execution_failure(
                    run_id=run_id,
                    run=run,
                    decision=decision,
                    error_message=str(exc),
                )
                if recovered:
                    continue
                return self._fail_run(run_id, f"Tool execution failed: {exc}")

            updated_snapshot = self.get_snapshot(run_id)
            updated_run = updated_snapshot.run
            verification_evidence = self._build_verification_evidence(decision, invocation_result)
            failure = None
            recent_failure_signatures: list[str] = []
            stagnation_count = 0
            last_tool_result = self._build_tool_result_payload(invocation_result)
            if invocation_result.ok:
                last_tool_result.pop("failure", None)
            else:
                failure = self._classify_tool_failure(decision, invocation_result, updated_run.loop_state)
                recent_failure_signatures = self._append_recent_failure_signature(
                    updated_run.loop_state.recent_failure_signatures,
                    failure.signature,
                )
                stagnation_count = self._trailing_duplicate_count(recent_failure_signatures)
                if stagnation_count >= self._MAX_STAGNATION_BEFORE_RECOVERY:
                    failure = failure.model_copy(
                        update={
                            "failure_class": AutonomousToolFailureClass.STAGNATION,
                            "hint": (
                                "The runner has repeated the same failed tool pattern. "
                                "Inspect the failure, change strategy, or recover to the checkpoint before trying again."
                            ),
                            "repeated_count": stagnation_count,
                        }
                    )
                else:
                    failure = failure.model_copy(update={"repeated_count": stagnation_count or 1})
                last_tool_result["failure"] = failure.model_dump(mode="json")
            loop_updates: dict[str, object] = {
                "step_index": step_index,
                "last_tool_name": decision.selected_tool,
                "last_tool_ok": invocation_result.ok,
                "last_tool_result": last_tool_result,
                "recent_tool_names": self._append_recent_tool_name(
                    updated_run.loop_state.recent_tool_names,
                    decision.selected_tool,
                ),
                "consecutive_failures": 0 if invocation_result.ok else updated_run.loop_state.consecutive_failures + 1,
                "stagnation_count": 0 if invocation_result.ok else stagnation_count,
                "last_failure": failure,
                "recent_failure_signatures": recent_failure_signatures,
            }
            if decision.selected_tool == "checkpoint" and invocation_result.ok:
                checkpoint_ref = str(invocation_result.result.get("checkpoint", {}).get("tag_name") or "")
                if checkpoint_ref:
                    loop_updates["checkpoint_ref"] = checkpoint_ref
            updated_loop_state = updated_run.loop_state.model_copy(
                update=loop_updates,
            )
            run_updates: dict[str, object] = {
                "loop_state": updated_loop_state,
                "updated_at": datetime.now(UTC),
            }
            if verification_evidence is not None:
                run_updates["latest_verification"] = verification_evidence
            self._persist_run(updated_run.model_copy(update=run_updates))

            if invocation_result.feature_state is not None:
                self._emit_event(
                    run_id=run_id,
                    event_type=AutonomousEventType.VERIFICATION_STATE_UPDATED,
                    phase=AutonomousRunPhase.VERIFICATION,
                    summary=f"Feature verification status is now {invocation_result.feature_state.status.value}.",
                    payload={
                        "tool_name": invocation_result.tool_name,
                        "feature_status": invocation_result.feature_state.status.value,
                        "completion_blockers": invocation_result.feature_state.completion_blockers,
                        "verification_evidence": verification_evidence.model_dump(mode="json")
                        if verification_evidence is not None
                        else None,
                    },
                )

            current_run = self.get_snapshot(run_id).run
            if invocation_result.ok and self._ready_for_automatic_completion(current_run):
                return self._complete_run(run_id)

            if not invocation_result.ok:
                current_run = self.get_snapshot(run_id).run
                recovered = self._recover_from_failed_tool_result(
                    run_id=run_id,
                    run=current_run,
                    decision=decision,
                    failure=current_run.loop_state.last_failure,
                )
                if recovered:
                    continue
                if current_run.loop_state.consecutive_failures >= self._max_consecutive_failures(current_run):
                    failure_message = (
                        current_run.loop_state.last_failure.message
                        if current_run.loop_state.last_failure is not None
                        else f"Repeated tool failures exhausted the retry budget for {decision.selected_tool}."
                    )
                    return self._fail_run(run_id, failure_message)

        current_run = self.get_snapshot(run_id).run
        if self._ready_for_automatic_completion(current_run):
            return self._complete_run(run_id)
        return self._fail_run(run_id, f"Run exceeded the max step budget of {max_steps}.")

    def _persist_run(self, run: AutonomousRepairRunRecord) -> None:
        self._event_stream.upsert_run(run)

    def _emit_event(
        self,
        *,
        run_id: str,
        event_type: AutonomousEventType,
        phase: AutonomousRunPhase,
        summary: str,
        payload: dict[str, object] | None = None,
        decision: AutonomousDecision | None = None,
    ) -> None:
        self._event_stream.append_event(
            AutonomousRunEvent(
                id=str(uuid4()),
                run_id=run_id,
                event_type=event_type,
                phase=phase,
                summary=self._truncate(summary, self._EVENT_SUMMARY_LIMIT),
                decision=decision,
                payload=payload or {},
                created_at=datetime.now(UTC),
            )
        )

    def _execute_decision_tool(
        self,
        *,
        run_id: str,
        run: AutonomousRepairRunRecord,
        decision: AutonomousDecision,
    ):
        assert decision.selected_tool is not None
        self._emit_event(
            run_id=run_id,
            event_type=AutonomousEventType.TOOL_CALL_STARTED,
            phase=self._phase_for_decision(decision),
            summary=f"Starting tool call {decision.selected_tool}.",
            decision=decision,
            payload={"tool_name": decision.selected_tool, "arguments": decision.arguments},
        )
        try:
            invocation_result = self._orchestrator.invoke_tool(
                run.coding_session_id,
                ToolInvocationRequest(
                    tool_name=decision.selected_tool,
                    arguments=decision.arguments,
                    summary=decision.summary,
                    feature_id=decision.feature_id,
                    verification_kind=self._coerce_verification_kind(decision.verification_kind),
                ),
            )
        except Exception as exc:
            self._emit_event(
                run_id=run_id,
                event_type=AutonomousEventType.TOOL_CALL_COMPLETED,
                phase=self._phase_for_decision(decision),
                summary=f"Tool call {decision.selected_tool} failed before completion.",
                payload={
                    "tool_name": decision.selected_tool,
                    "ok": False,
                    "error": str(exc),
                },
            )
            raise
        self._emit_event(
            run_id=run_id,
            event_type=AutonomousEventType.TOOL_CALL_COMPLETED,
            phase=self._phase_for_decision(decision),
            summary=f"Completed tool call {decision.selected_tool}.",
            payload={
                "tool_name": decision.selected_tool,
                "ok": invocation_result.ok,
                "result": invocation_result.result,
            },
        )
        if decision.selected_tool == "checkpoint" and invocation_result.ok:
            self._emit_event(
                run_id=run_id,
                event_type=AutonomousEventType.GIT_CHECKPOINT_CREATED,
                phase=AutonomousRunPhase.RECOVERY,
                summary="Created a git checkpoint.",
                payload={"checkpoint": invocation_result.result.get("checkpoint")},
            )
        if decision.selected_tool in {"revert_to_checkpoint", "reset_failed_attempt", "discard_failed_work"}:
            self._emit_event(
                run_id=run_id,
                event_type=AutonomousEventType.RECOVERY_INVOKED,
                phase=AutonomousRunPhase.RECOVERY,
                summary=f"Invoked git recovery tool {decision.selected_tool}.",
                payload={"tool_name": decision.selected_tool, "result": invocation_result.result},
            )
        return invocation_result

    def _coerce_verification_kind(self, value: str | None) -> VerificationKind | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            return None
        try:
            return VerificationKind(normalized)
        except ValueError:
            return None

    def _complete_run(self, run_id: str) -> AutonomousRunSnapshot:
        run = self.get_snapshot(run_id).run
        completed = run.model_copy(
            update={
                "status": AutonomousRunStatus.SUCCEEDED,
                "phase": AutonomousRunPhase.COMPLETED,
                "updated_at": datetime.now(UTC),
            }
        )
        self._persist_run(completed)
        self._emit_event(
            run_id=run_id,
            event_type=AutonomousEventType.RUN_COMPLETED,
            phase=AutonomousRunPhase.COMPLETED,
            summary="Autonomous repair run completed successfully.",
            payload={"status": AutonomousRunStatus.SUCCEEDED.value},
        )
        return self.get_snapshot(run_id)

    def prepare_for_retry(
        self,
        *,
        run_id: str,
        retry_context: dict[str, Any] | None = None,
    ) -> AutonomousRunSnapshot:
        run = self.get_snapshot(run_id).run
        checkpoint_ref = run.loop_state.checkpoint_ref
        if checkpoint_ref is None:
            return self._fail_run(run_id, "Autonomous retry requires a baseline checkpoint.")
        try:
            GitCheckpointManager().discard_failed_work(
                repository_root=run.repository_root,
                checkpoint_ref=checkpoint_ref,
            )
        except Exception as exc:  # noqa: BLE001
            return self._fail_run(run_id, f"Autonomous retry reset failed: {exc}")

        updated_loop_state = run.loop_state.model_copy(
            update={
                "step_index": 0,
                "checkpoint_ref": checkpoint_ref,
                "recovery_attempts": 0,
                "consecutive_failures": 0,
                "stagnation_count": 0,
                "last_tool_name": "discard_failed_work",
                "recent_tool_names": [],
                "last_tool_ok": True,
                "last_tool_result": {
                    "recovery_tool": "discard_failed_work",
                    "checkpoint_ref": checkpoint_ref,
                    "retry_context": retry_context or {},
                },
                "last_failure": None,
                "recent_failure_signatures": [],
                "last_retry_context": retry_context or {},
            }
        )
        retried_run = run.model_copy(
            update={
                "status": AutonomousRunStatus.QUEUED,
                "phase": AutonomousRunPhase.CODING,
                "initializer_session_id": None,
                "coding_session_id": None,
                "patch_run_id": None,
                "sandbox_run_id": None,
                "promotion_branch_name": None,
                "promotion_url": None,
                "promotion_status": AutonomousPromotionStatus.NOT_REQUESTED,
                "last_error": None,
                "latest_verification": None,
                "latest_review": None,
                "loop_state": updated_loop_state,
                "updated_at": datetime.now(UTC),
            }
        )
        self._persist_run(retried_run)
        self._emit_event(
            run_id=run_id,
            event_type=AutonomousEventType.RECOVERY_INVOKED,
            phase=AutonomousRunPhase.RECOVERY,
            summary="Reset the autonomous run to the baseline checkpoint for a fresh retry attempt.",
            payload={
                "checkpoint_ref": checkpoint_ref,
                "retry_context": retry_context or {},
            },
        )
        self._emit_event(
            run_id=run_id,
            event_type=AutonomousEventType.PHASE_CHANGED,
            phase=AutonomousRunPhase.CODING,
            summary="Run returned to coding phase for a fresh retry attempt.",
            payload={"phase": AutonomousRunPhase.CODING.value},
        )
        return self.get_snapshot(run_id)

    def _fail_run(self, run_id: str, error_message: str) -> AutonomousRunSnapshot:
        run = self.get_snapshot(run_id).run
        truncated_error = self._truncate(error_message, self._RUN_ERROR_LIMIT)
        loop_state = run.loop_state
        if loop_state.last_failure is None:
            failure_class = self._classify_run_failure(truncated_error)
            if failure_class is not None:
                tool_name = loop_state.last_tool_name or "runner"
                loop_state = loop_state.model_copy(
                    update={
                        "last_failure": AutonomousToolFailure(
                            tool_name=tool_name,
                            failure_class=failure_class,
                            message=truncated_error,
                            hint=self._failure_hint_for_class(failure_class),
                            signature=self._failure_signature(tool_name, failure_class, truncated_error),
                            repeated_count=1,
                        ),
                    }
                )
        failed = run.model_copy(
            update={
                "status": AutonomousRunStatus.FAILED,
                "phase": AutonomousRunPhase.FAILED,
                "last_error": truncated_error,
                "loop_state": loop_state,
                "updated_at": datetime.now(UTC),
            }
        )
        self._persist_run(failed)
        self._emit_event(
            run_id=run_id,
            event_type=AutonomousEventType.RUN_FAILED,
            phase=AutonomousRunPhase.FAILED,
            summary=truncated_error,
            payload={"status": AutonomousRunStatus.FAILED.value, "error": truncated_error},
        )
        return self.get_snapshot(run_id)

    def _truncate(self, value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return f"{value[: limit - 3]}..."

    def _all_features_verified(self, coding_snapshot) -> bool:
        catalog = coding_snapshot.feature_catalog
        if catalog is None or not catalog.features:
            return False
        return all(
            feature.verification_state.status is VerificationStatus.FULLY_VERIFIED
            for feature in catalog.features
        )

    def _ready_for_automatic_completion(self, run: AutonomousRepairRunRecord) -> bool:
        if not self._repair_mode_requires_code_change(run):
            return False
        if run.coding_session_id is None:
            return False
        coding_snapshot = self._orchestrator.restore_session(run.coding_session_id)
        if not self._all_features_verified(coding_snapshot):
            return False
        if not self._has_changes_since_checkpoint(run):
            return False
        return self._has_fresh_verification_evidence(run)

    def _phase_for_decision(self, decision: AutonomousDecision) -> AutonomousRunPhase:
        if decision.selected_tool in {"checkpoint", "revert_to_checkpoint", "reset_failed_attempt", "discard_failed_work"}:
            return AutonomousRunPhase.RECOVERY
        if decision.verification_kind is not None or decision.selected_tool in {
            "browser_open",
            "browser_click",
            "browser_type",
            "browser_wait_for",
            "browser_assert_text",
            "browser_snapshot_dom",
            "browser_screenshot",
            "browser_get_url",
            "dom_snapshot",
            "take_screenshot",
            "capture_console_logs",
            "capture_network_summary",
            "current_page_state",
            "browser_close",
        }:
            return AutonomousRunPhase.VERIFICATION
        return AutonomousRunPhase.CODING

    def _ensure_baseline_checkpoint(self, run_id: str) -> AutonomousRunSnapshot | None:
        run = self.get_snapshot(run_id).run
        if run.coding_session_id is None or run.loop_state.checkpoint_ref:
            return None

        checkpoint_decision = AutonomousDecision(
            summary="Create an automatic baseline checkpoint before autonomous edits begin.",
            rationale="The runner should always keep a last-known-good rollback point even if the model forgets to create one.",
            action=AutonomousDecisionAction.INVOKE_TOOL,
            selected_tool="checkpoint",
            arguments={"label": "autonomous-baseline"},
            arguments_summary="label=autonomous-baseline",
        )
        try:
            invocation_result = self._execute_decision_tool(
                run_id=run_id,
                run=run,
                decision=checkpoint_decision,
            )
        except Exception as exc:  # noqa: BLE001
            return self._fail_run(run_id, f"Automatic baseline checkpoint failed: {exc}")

        if not invocation_result.ok:
            return self._fail_run(run_id, "Automatic baseline checkpoint did not succeed.")

        checkpoint_ref = str(invocation_result.result.get("checkpoint", {}).get("tag_name") or "")
        updated_loop_state = run.loop_state.model_copy(
            update={
                "checkpoint_ref": checkpoint_ref or run.loop_state.checkpoint_ref,
                "last_tool_name": "checkpoint",
                "last_tool_ok": invocation_result.ok,
                "last_tool_result": invocation_result.result,
                "recent_tool_names": self._append_recent_tool_name(run.loop_state.recent_tool_names, "checkpoint"),
            }
        )
        self._persist_run(run.model_copy(update={"loop_state": updated_loop_state, "updated_at": datetime.now(UTC)}))
        return None

    def _auto_install_dependencies(self, run_id: str) -> None:
        run = self.get_snapshot(run_id).run
        install_command = run.install_command
        if not install_command:
            return
        repo_root = Path(run.repository_root)
        if (repo_root / "node_modules").exists() or (repo_root / ".venv").exists():
            return

        commands_to_try = [install_command]
        if install_command.strip() == "npm ci":
            commands_to_try.append("npm install")

        for cmd in commands_to_try:
            install_decision = AutonomousDecision(
                summary=f"Auto-install project dependencies: {cmd}",
                rationale="Pre-install dependencies so the agent can focus on investigation and repair.",
                action=AutonomousDecisionAction.INVOKE_TOOL,
                selected_tool="run_command",
                arguments={"command": cmd, "timeout_seconds": 300},
                arguments_summary=f"command={cmd}",
            )
            try:
                result = self._execute_decision_tool(run_id=run_id, run=run, decision=install_decision)
                if result.ok:
                    self._emit_event(
                        run_id=run_id,
                        event_type=AutonomousEventType.TOOL_CALL_COMPLETED,
                        phase=AutonomousRunPhase.CODING,
                        summary=f"Auto-install succeeded with: {cmd}",
                        payload={"tool_name": "run_command", "ok": True},
                    )
                    return
                if cmd != commands_to_try[-1]:
                    self._emit_event(
                        run_id=run_id,
                        event_type=AutonomousEventType.TOOL_CALL_COMPLETED,
                        phase=AutonomousRunPhase.CODING,
                        summary=f"Auto-install with '{cmd}' failed, trying fallback.",
                        payload={"tool_name": "run_command", "ok": False},
                    )
                    continue
                self._emit_event(
                    run_id=run_id,
                    event_type=AutonomousEventType.TOOL_CALL_COMPLETED,
                    phase=AutonomousRunPhase.CODING,
                    summary=f"Auto-install failed with: {cmd} (agent can retry manually).",
                    payload={"tool_name": "run_command", "ok": False},
                )
            except Exception:  # noqa: BLE001
                if cmd == commands_to_try[-1]:
                    self._emit_event(
                        run_id=run_id,
                        event_type=AutonomousEventType.TOOL_CALL_COMPLETED,
                        phase=AutonomousRunPhase.CODING,
                        summary="Auto-install raised an exception (agent can install manually).",
                    )

    def _recover_from_execution_failure(
        self,
        *,
        run_id: str,
        run: AutonomousRepairRunRecord,
        decision: AutonomousDecision,
        error_message: str,
    ) -> bool:
        checkpoint_ref = run.loop_state.checkpoint_ref
        if (
            run.coding_session_id is None
            or checkpoint_ref is None
            or run.loop_state.recovery_attempts >= self._max_recovery_attempts(run)
        ):
            return False

        recovery_decision = AutonomousDecision(
            summary="Discard failed work and return to the baseline checkpoint after an execution failure.",
            rationale="An unexpected tool exception may leave the workspace or browser session in an unreliable state.",
            action=AutonomousDecisionAction.INVOKE_TOOL,
            selected_tool="discard_failed_work",
            arguments={"checkpoint_ref": checkpoint_ref},
            arguments_summary=f"checkpoint_ref={checkpoint_ref}",
        )
        try:
            recovery_result = self._execute_decision_tool(
                run_id=run_id,
                run=run,
                decision=recovery_decision,
            )
        except Exception:
            return False

        updated_loop_state = run.loop_state.model_copy(
            update={
                "recovery_attempts": run.loop_state.recovery_attempts + 1,
                "consecutive_failures": run.loop_state.consecutive_failures + 1,
                "stagnation_count": 0,
                "last_tool_name": decision.selected_tool,
                "last_tool_ok": False,
                "last_tool_result": {
                    "_tool_call": {
                        "ok": False,
                        "tool_name": decision.selected_tool,
                    },
                    "error": error_message,
                    "recovered": recovery_result.ok,
                    "recovery_tool": "discard_failed_work",
                    "checkpoint_ref": checkpoint_ref,
                },
                "last_failure": AutonomousToolFailure(
                    tool_name=decision.selected_tool or "unknown",
                    failure_class=AutonomousToolFailureClass.EXCEPTION,
                    message=error_message,
                    hint="Inspect the exception and adapt the next tool call before retrying.",
                    signature=self._failure_signature(
                        decision.selected_tool or "unknown",
                        AutonomousToolFailureClass.EXCEPTION,
                        error_message,
                    ),
                    repeated_count=1,
                ),
                "recent_failure_signatures": self._append_recent_failure_signature(
                    run.loop_state.recent_failure_signatures,
                    self._failure_signature(
                        decision.selected_tool or "unknown",
                        AutonomousToolFailureClass.EXCEPTION,
                        error_message,
                    ),
                ),
                "recent_tool_names": self._append_recent_tool_name(
                    self._append_recent_tool_name(run.loop_state.recent_tool_names, decision.selected_tool),
                    "discard_failed_work",
                ),
            }
        )
        self._persist_run(run.model_copy(update={"loop_state": updated_loop_state, "updated_at": datetime.now(UTC)}))
        return recovery_result.ok

    def _append_recent_tool_name(self, recent_tool_names: list[str], tool_name: str | None) -> list[str]:
        if not tool_name:
            return list(recent_tool_names)
        updated = [*recent_tool_names, tool_name]
        return updated[-self._RECENT_TOOL_HISTORY_LIMIT :]

    def _repair_mode_requires_code_change(self, run: AutonomousRepairRunRecord) -> bool:
        return run.execution_mode is not AutonomousExecutionMode.INVESTIGATE_ONLY

    def _max_recovery_attempts(self, run: AutonomousRepairRunRecord) -> int:
        if run.policy.max_retry_budget > 0:
            return run.policy.max_retry_budget
        return self._MAX_EXCEPTION_RECOVERIES

    def _max_consecutive_failures(self, run: AutonomousRepairRunRecord) -> int:
        if run.policy.max_retry_budget > 0:
            return max(2, run.policy.max_retry_budget)
        return self._MAX_CONSECUTIVE_FAILURES

    def _recover_from_failed_tool_result(
        self,
        *,
        run_id: str,
        run: AutonomousRepairRunRecord,
        decision: AutonomousDecision,
        failure: AutonomousToolFailure | None,
    ) -> bool:
        if failure is None:
            return False
        if failure.failure_class not in {
            AutonomousToolFailureClass.STAGNATION,
            AutonomousToolFailureClass.TOOL_ERROR,
        }:
            return False
        if run.loop_state.recovery_attempts >= self._max_recovery_attempts(run):
            return False
        if failure.failure_class is AutonomousToolFailureClass.TOOL_ERROR and run.loop_state.consecutive_failures < 2:
            return False
        checkpoint_ref = run.loop_state.checkpoint_ref
        if checkpoint_ref is None or run.coding_session_id is None:
            return False

        recovery_decision = AutonomousDecision(
            summary="Recover to the baseline checkpoint after repeated tool failure.",
            rationale="The runner detected a repeated or environment-level tool failure and should restore a clean baseline before retrying.",
            action=AutonomousDecisionAction.INVOKE_TOOL,
            selected_tool="discard_failed_work",
            arguments={"checkpoint_ref": checkpoint_ref},
            arguments_summary=f"checkpoint_ref={checkpoint_ref}",
        )
        try:
            recovery_result = self._execute_decision_tool(
                run_id=run_id,
                run=run,
                decision=recovery_decision,
            )
        except Exception:
            return False
        updated_loop_state = run.loop_state.model_copy(
            update={
                "recovery_attempts": run.loop_state.recovery_attempts + 1,
                "stagnation_count": 0,
                "last_tool_result": {
                    **(run.loop_state.last_tool_result or {}),
                    "recovered": recovery_result.ok,
                    "recovery_tool": "discard_failed_work",
                    "checkpoint_ref": checkpoint_ref,
                },
            }
        )
        self._persist_run(run.model_copy(update={"loop_state": updated_loop_state, "updated_at": datetime.now(UTC)}))
        return recovery_result.ok

    def _build_tool_result_payload(self, invocation_result) -> dict[str, Any]:
        payload = dict(invocation_result.result)
        payload["_tool_call"] = {
            "tool_name": invocation_result.tool_name,
            "ok": invocation_result.ok,
            "turn_id": invocation_result.turn_id,
        }
        return payload

    def _build_verification_evidence(
        self,
        decision: AutonomousDecision,
        invocation_result,
    ) -> AutonomousVerificationEvidence | None:
        if decision.verification_kind is None:
            return None
        if invocation_result.ok:
            summary = (
                self._extract_success_message(invocation_result.result)
                or f"{decision.verification_kind} verification passed via {invocation_result.tool_name}."
            )
        else:
            summary = self._extract_failure_message(invocation_result.result, invocation_result.tool_name)
        return AutonomousVerificationEvidence(
            source="tool",
            kind=decision.verification_kind,
            summary=self._truncate(summary, 1_000),
            passed=invocation_result.ok,
            command=str(decision.arguments.get("command")) if isinstance(decision.arguments.get("command"), str) else None,
            recorded_at=datetime.now(UTC),
            metadata={
                "tool_name": invocation_result.tool_name,
                "turn_id": invocation_result.turn_id,
                "feature_id": decision.feature_id,
            },
        )

    def _classify_tool_failure(
        self,
        decision: AutonomousDecision,
        invocation_result,
        loop_state,
    ) -> AutonomousToolFailure:
        message = self._extract_failure_message(invocation_result.result, invocation_result.tool_name)
        if decision.verification_kind is not None:
            failure_class = AutonomousToolFailureClass.VERIFICATION
        elif self._looks_like_validation_failure(invocation_result.result, message):
            failure_class = AutonomousToolFailureClass.VALIDATION
        elif invocation_result.tool_name in {"run_command", "browser_open", "browser_assert_text", "browser_click"}:
            failure_class = AutonomousToolFailureClass.TOOL_ERROR
        else:
            failure_class = AutonomousToolFailureClass.UNKNOWN
        signature = self._failure_signature(invocation_result.tool_name, failure_class, message)
        repeated_count = loop_state.recent_failure_signatures.count(signature) + 1
        return AutonomousToolFailure(
            tool_name=invocation_result.tool_name,
            failure_class=failure_class,
            message=self._truncate(message, 2_000),
            hint=self._failure_hint_for_class(failure_class),
            signature=signature,
            repeated_count=repeated_count,
            details={
                "tool_result": invocation_result.result,
                "verification_kind": decision.verification_kind,
            },
        )

    def _looks_like_validation_failure(self, result: dict[str, Any], message: str) -> bool:
        if "validation error" in message.lower():
            return True
        lowered = message.lower()
        validation_markers = [
            "field required",
            "extra inputs",
            "input should",
            "missing",
            "unexpected keyword",
            "arguments_schema",
        ]
        if any(marker in lowered for marker in validation_markers):
            return True
        error_payload = result.get("error")
        if isinstance(error_payload, dict):
            code = str(error_payload.get("code") or "").lower()
            if code in {"validation_error", "invalid_request", "no_matching_text"}:
                return True
        return False

    def _failure_hint_for_class(self, failure_class: AutonomousToolFailureClass) -> str:
        if failure_class is AutonomousToolFailureClass.VALIDATION:
            return "Match the next tool call to the published arguments_schema and usage_notes instead of repeating the same shape."
        if failure_class is AutonomousToolFailureClass.VERIFICATION:
            return "Inspect the verification output, then change code or environment before rerunning the verification step."
        if failure_class is AutonomousToolFailureClass.STAGNATION:
            return "Change strategy or recover to the checkpoint before retrying the same action."
        if failure_class is AutonomousToolFailureClass.TOOL_ERROR:
            return "Inspect the tool output for environment or path issues and recover if the workspace may now be unreliable."
        return "Inspect the tool output and adapt the next step."

    def _extract_failure_message(self, result: dict[str, Any], tool_name: str) -> str:
        for key in ("message", "output", "stderr"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        error_payload = result.get("error")
        if isinstance(error_payload, dict):
            for key in ("message", "code"):
                value = error_payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        validation_payload = result.get("validation_failure")
        if isinstance(validation_payload, dict):
            message = validation_payload.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        return f"{tool_name} returned ok=false without a detailed error message."

    def _extract_success_message(self, result: dict[str, Any]) -> str | None:
        for key in ("message", "output", "stdout"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _classify_run_failure(self, error_message: str) -> AutonomousToolFailureClass | None:
        lowered = error_message.lower()
        if self._looks_like_validation_failure({}, error_message):
            return AutonomousToolFailureClass.VALIDATION
        if "decision engine failed" in lowered or "automatic baseline checkpoint failed" in lowered:
            return AutonomousToolFailureClass.EXCEPTION
        if "tool execution failed" in lowered:
            return AutonomousToolFailureClass.TOOL_ERROR
        if "exceeded the max step budget" in lowered:
            return AutonomousToolFailureClass.STAGNATION
        if "verification" in lowered:
            return AutonomousToolFailureClass.VERIFICATION
        return None

    def _failure_signature(
        self,
        tool_name: str,
        failure_class: AutonomousToolFailureClass,
        message: str,
    ) -> str:
        normalized = " ".join(message.lower().split())[:240]
        return f"{tool_name}:{failure_class.value}:{normalized}"

    def _append_recent_failure_signature(self, signatures: list[str], signature: str) -> list[str]:
        updated = [*signatures, signature]
        return updated[-8:]

    def _trailing_duplicate_count(self, items: list[str]) -> int:
        if not items:
            return 0
        target = items[-1]
        count = 0
        for item in reversed(items):
            if item != target:
                break
            count += 1
        return count

    def _has_fresh_verification_evidence(self, run: AutonomousRepairRunRecord) -> bool:
        evidence = run.latest_verification
        if evidence is None or not evidence.passed:
            return False
        return evidence.recorded_at >= run.created_at

    def _can_invalidate_stale_verification(
        self,
        run: AutonomousRepairRunRecord,
        step_index: int,
    ) -> bool:
        # When the decision engine decides COMPLETE at the very first step of a
        # continue_run loop without performing any tool calls in this loop, the
        # feature catalog's "fully_verified" status is inherited from a previous
        # attempt. In that case, resetting the catalog lets the run actually do
        # the work rather than terminating as if the job were done.
        if step_index > 1:
            return False
        return not run.loop_state.recent_tool_names or (
            len(run.loop_state.recent_tool_names) == 1
            and run.loop_state.recent_tool_names[0] == "discard_failed_work"
        )

    _MAX_PREMATURE_COMPLETIONS = 2
    _PREMATURE_COMPLETION_MARKER = "__premature_completion__"

    def _scope_recent_events_to_current_session(
        self,
        events: list[AutonomousRunEvent],
        coding_session_id: str | None,
        limit: int,
    ) -> list[AutonomousRunEvent]:
        """Return only events that belong to the current coding session.

        When an autonomous run is resumed or retried after a previous attempt,
        the persistent event stream still contains events emitted during prior
        attempts (e.g. ``verification_state_updated -> fully_verified``).
        Feeding those stale signals to the decision engine makes it conclude the
        objective is already done even though the current session has a fresh,
        unverified feature catalog. Scoping the window to events emitted after
        the current session's ``coding_session_ready`` boundary keeps the model
        honest about what it has actually done in this attempt.
        """
        if coding_session_id is None or not events:
            return events[-limit:]
        boundary_index: int | None = None
        for idx in range(len(events) - 1, -1, -1):
            event = events[idx]
            if event.event_type is not AutonomousEventType.CODING_SESSION_READY:
                continue
            payload = event.payload if isinstance(event.payload, dict) else {}
            if payload.get("session_id") == coding_session_id:
                boundary_index = idx
                break
        scoped = events if boundary_index is None else events[boundary_index:]
        return scoped[-limit:]

    def _count_premature_completions(self, run: AutonomousRepairRunRecord) -> int:
        return sum(
            1
            for signature in run.loop_state.recent_failure_signatures
            if signature.startswith(self._PREMATURE_COMPLETION_MARKER)
        )

    def _reject_and_continue_on_premature_completion(
        self,
        *,
        run_id: str,
        run: AutonomousRepairRunRecord,
        reason: str,
    ) -> bool:
        """Steer the decision engine back to work instead of failing.

        The decision engine sometimes emits ``complete`` before the current
        session has actually verified the repair (e.g. because the event
        history or feature catalog inherited stale evidence from a prior
        attempt). Instead of turning that into a terminal failure, inject a
        tool-result style feedback payload and let the loop iterate again. The
        loop keeps a short-circuit breaker so a truly stuck agent still fails
        rather than spinning forever.
        """
        premature_count = self._count_premature_completions(run) + 1
        if premature_count > self._MAX_PREMATURE_COMPLETIONS:
            return False

        signature = f"{self._PREMATURE_COMPLETION_MARKER}:{reason}:{premature_count}"
        feedback_message = (
            "The previous `complete` action was rejected because the current "
            "session has not produced verifiable evidence of the repair yet "
            f"(reason={reason}). Investigate the reported incident, apply a "
            "code change that addresses it, then run the configured "
            "verification command before attempting to complete again."
        )
        updated_loop_state = run.loop_state.model_copy(
            update={
                "last_tool_name": None,
                "last_tool_ok": False,
                "last_tool_result": {
                    "premature_completion": {
                        "reason": reason,
                        "attempt": premature_count,
                        "feedback": feedback_message,
                    }
                },
                "consecutive_failures": run.loop_state.consecutive_failures + 1,
                "recent_failure_signatures": self._append_recent_failure_signature(
                    run.loop_state.recent_failure_signatures,
                    signature,
                ),
                "last_failure": AutonomousToolFailure(
                    tool_name="complete",
                    failure_class=AutonomousToolFailureClass.STAGNATION,
                    message=feedback_message,
                    hint=(
                        "Run the configured verification command (or apply a "
                        "code change first if no repair has been made in this "
                        "attempt) before deciding to complete."
                    ),
                    signature=signature,
                    repeated_count=premature_count,
                ),
            }
        )
        self._persist_run(
            run.model_copy(
                update={
                    "loop_state": updated_loop_state,
                    "updated_at": datetime.now(UTC),
                }
            )
        )
        self._emit_event(
            run_id=run_id,
            event_type=AutonomousEventType.VERIFICATION_STATE_UPDATED,
            phase=AutonomousRunPhase.CODING,
            summary=(
                "Rejected a premature completion decision; the current "
                "session has not yet verified the repair."
            ),
            payload={"reason": reason, "attempt": premature_count},
        )
        return True

    def _invalidate_feature_catalog(
        self,
        *,
        run_id: str,
        coding_session_id: str,
        reason: str,
    ) -> None:
        try:
            self._orchestrator.invalidate_feature_catalog(coding_session_id)
        except Exception:  # noqa: BLE001
            return
        self._emit_event(
            run_id=run_id,
            event_type=AutonomousEventType.VERIFICATION_STATE_UPDATED,
            phase=AutonomousRunPhase.CODING,
            summary=(
                "Reset stale feature verification state inherited from a prior attempt "
                "so the runner can actually reproduce and repair the incident."
            ),
            payload={"reason": reason},
        )
        current = self.get_snapshot(run_id).run
        refreshed = current.model_copy(
            update={
                "latest_verification": None,
                "updated_at": datetime.now(UTC),
                "loop_state": current.loop_state.model_copy(
                    update={"last_tool_result": {}},
                ),
            }
        )
        self._persist_run(refreshed)

    def _has_changes_since_checkpoint(self, run: AutonomousRepairRunRecord) -> bool:
        checkpoint_ref = run.loop_state.checkpoint_ref
        if checkpoint_ref is None:
            return False
        diff_result = GitCheckpointManager().diff_since_checkpoint(
            repository_root=run.repository_root,
            checkpoint_ref=checkpoint_ref,
        )
        diff = diff_result.diff
        if diff is None:
            return False
        return bool(diff.changed_files or diff.patch.strip())
