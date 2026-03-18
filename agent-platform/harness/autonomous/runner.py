from __future__ import annotations

from datetime import UTC, datetime
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
    AutonomousRepairRunRecord,
    AutonomousRunEvent,
    AutonomousRunPhase,
    AutonomousRunSnapshot,
    AutonomousRunStatus,
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
        max_steps: int = 12,
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
        max_steps: int = 12,
    ) -> AutonomousRunSnapshot:
        run = self.get_snapshot(run_id).run
        updated_loop_state = run.loop_state.model_copy(update={"max_steps": max_steps})
        self._persist_run(run.model_copy(update={"loop_state": updated_loop_state, "updated_at": datetime.now(UTC)}))
        baseline_checkpoint_failed = self._ensure_baseline_checkpoint(run_id)
        if baseline_checkpoint_failed is not None:
            return baseline_checkpoint_failed

        for step_index in range(1, max_steps + 1):
            current_snapshot = self.get_snapshot(run_id)
            run = current_snapshot.run
            coding_session_id = run.coding_session_id
            if coding_session_id is None:
                return self._fail_run(run_id, "Coding session was not initialized.")

            coding_snapshot = self._orchestrator.restore_session(coding_session_id)
            decision = await decision_engine.decide(
                run=run,
                coding_session=coding_snapshot,
                available_tools=[tool.model_dump(mode="json") for tool in coding_snapshot.available_tools.tools],
                last_tool_result=run.loop_state.last_tool_result or None,
                recent_events=current_snapshot.events[-self._RECENT_EVENT_LIMIT :],
            )
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
                    if self._repair_mode_requires_code_change(run) and not self._has_changes_since_checkpoint(run):
                        return self._fail_run(
                            run_id,
                            "Autonomous repair cannot complete without producing a code change relative to the baseline checkpoint.",
                        )
                    return self._complete_run(run_id)
                return self._fail_run(
                    run_id,
                    "Decision engine attempted to complete the run before verification requirements were satisfied.",
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
            loop_updates: dict[str, object] = {
                "step_index": step_index,
                "last_tool_name": decision.selected_tool,
                "last_tool_ok": invocation_result.ok,
                "last_tool_result": invocation_result.result,
                "recent_tool_names": self._append_recent_tool_name(
                    updated_run.loop_state.recent_tool_names,
                    decision.selected_tool,
                ),
                "consecutive_failures": 0 if invocation_result.ok else updated_run.loop_state.consecutive_failures + 1,
            }
            if decision.selected_tool == "checkpoint" and invocation_result.ok:
                checkpoint_ref = str(invocation_result.result.get("checkpoint", {}).get("tag_name") or "")
                if checkpoint_ref:
                    loop_updates["checkpoint_ref"] = checkpoint_ref
            updated_loop_state = updated_run.loop_state.model_copy(
                update=loop_updates,
            )
            self._persist_run(updated_run.model_copy(update={"loop_state": updated_loop_state, "updated_at": datetime.now(UTC)}))

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
                    },
                )

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

    def _fail_run(self, run_id: str, error_message: str) -> AutonomousRunSnapshot:
        run = self.get_snapshot(run_id).run
        truncated_error = self._truncate(error_message, self._RUN_ERROR_LIMIT)
        failed = run.model_copy(
            update={
                "status": AutonomousRunStatus.FAILED,
                "phase": AutonomousRunPhase.FAILED,
                "last_error": truncated_error,
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
            or run.loop_state.recovery_attempts >= self._MAX_EXCEPTION_RECOVERIES
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
                "last_tool_name": decision.selected_tool,
                "last_tool_ok": False,
                "last_tool_result": {
                    "error": error_message,
                    "recovered": recovery_result.ok,
                    "recovery_tool": "discard_failed_work",
                    "checkpoint_ref": checkpoint_ref,
                },
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
