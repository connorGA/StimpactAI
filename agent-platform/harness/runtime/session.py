from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from harness.context.manager import HarnessContextManager
from harness.git_ops.checkpoints import GitCheckpointManager
from harness.prompts.templates import get_system_prompt_for_role
from harness.runtime.initializer import InitializerOutputBuilder
from harness.runtime.profile import HarnessProfileLoader
from harness.runtime.verification import VerificationRulesEngine
from harness.schemas.profile import HarnessRepositoryProfile
from harness.schemas.runtime import (
    AgentPermissions,
    CodingAgentInputContract,
    HarnessAgentRole,
    InitializerOutputContract,
    RuntimeSessionRecord,
    RuntimeSessionStatus,
)
from harness.tools.browser import BrowserToolSessionManager
from harness.tools.file_editor import GuardedFileEditor
from harness.tools.file_viewer import FileViewerSessionManager


@dataclass(slots=True)
class RuntimePrimitives:
    context_manager: HarnessContextManager
    file_viewer: FileViewerSessionManager
    file_editor: GuardedFileEditor
    browser_tools: BrowserToolSessionManager
    repository_profile: HarnessRepositoryProfile
    initializer_output_builder: InitializerOutputBuilder
    git_checkpoint_manager: GitCheckpointManager
    verification_rules_engine: VerificationRulesEngine


class HarnessRuntime:
    def __init__(self) -> None:
        self._sessions: dict[str, RuntimeSessionRecord] = {}
        self._contexts: dict[str, HarnessContextManager] = {}
        self._viewers: dict[str, FileViewerSessionManager] = {}
        self._editors: dict[str, GuardedFileEditor] = {}
        self._browser_tools: dict[str, BrowserToolSessionManager] = {}
        self._profile_loader = HarnessProfileLoader()
        self._profiles: dict[str, HarnessRepositoryProfile] = {}
        self._initializer_builders: dict[str, InitializerOutputBuilder] = {}
        self._git_checkpoint_managers: dict[str, GitCheckpointManager] = {}
        self._verification_rules_engines: dict[str, VerificationRulesEngine] = {}

    def start_session(
        self,
        *,
        role: HarnessAgentRole,
        repository_root: str,
        objective: str | None = None,
        initializer_output: InitializerOutputContract | None = None,
    ) -> RuntimeSessionRecord:
        now = datetime.now(UTC)
        session_id = str(uuid4())
        repository_profile = self._profile_loader.load_profile(repository_root=repository_root)
        record = RuntimeSessionRecord(
            id=session_id,
            role=role,
            status=RuntimeSessionStatus.ACTIVE,
            repository_root=repository_root,
            repository_profile=repository_profile,
            objective=objective,
            prompt_template=get_system_prompt_for_role(role),
            permissions=self._permissions_for_role(role),
            initializer_output=initializer_output,
            created_at=now,
            updated_at=now,
        )
        self._sessions[session_id] = record
        self._contexts[session_id] = HarnessContextManager()
        self._contexts[session_id].set_current_objective(objective)
        self._contexts[session_id].set_current_repo_state("unknown")
        self._viewers[session_id] = FileViewerSessionManager()
        self._editors[session_id] = GuardedFileEditor()
        self._browser_tools[session_id] = BrowserToolSessionManager()
        self._profiles[session_id] = repository_profile
        self._initializer_builders[session_id] = InitializerOutputBuilder(profile_loader=self._profile_loader)
        self._git_checkpoint_managers[session_id] = GitCheckpointManager()
        self._verification_rules_engines[session_id] = VerificationRulesEngine()
        return record

    def get_session(self, session_id: str) -> RuntimeSessionRecord | None:
        record = self._sessions.get(session_id)
        return record.model_copy(deep=True) if record is not None else None

    def get_runtime_primitives(self, session_id: str) -> RuntimePrimitives:
        return RuntimePrimitives(
            context_manager=self._contexts[session_id],
            file_viewer=self._viewers[session_id],
            file_editor=self._editors[session_id],
            browser_tools=self._browser_tools[session_id],
            repository_profile=self._profiles[session_id],
            initializer_output_builder=self._initializer_builders[session_id],
            git_checkpoint_manager=self._git_checkpoint_managers[session_id],
            verification_rules_engine=self._verification_rules_engines[session_id],
        )

    def persist_initializer_output(
        self,
        session_id: str,
        initializer_output: InitializerOutputContract,
    ) -> RuntimeSessionRecord:
        record = self._require_session(session_id)
        updated = record.model_copy(
            update={
                "initializer_output": initializer_output,
                "updated_at": datetime.now(UTC),
            }
        )
        self._sessions[session_id] = updated
        return updated.model_copy(deep=True)

    def build_coding_agent_input(
        self,
        *,
        initializer_session_id: str,
        coding_session_id: str,
    ) -> CodingAgentInputContract:
        initializer_session = self._require_session(initializer_session_id)
        coding_session = self._require_session(coding_session_id)
        if initializer_session.initializer_output is None:
            raise ValueError("Initializer session does not have persisted initializer output.")

        context_packet = self._contexts[coding_session_id].build_prompt_ready_context()
        return CodingAgentInputContract(
            session_id=coding_session.id,
            repository_root=coding_session.repository_root,
            repository_profile=coding_session.repository_profile,
            current_objective=coding_session.objective,
            initializer_output=initializer_session.initializer_output,
            context_packet=context_packet,
        )

    def pause_session(self, session_id: str) -> RuntimeSessionRecord:
        return self._update_status(session_id, RuntimeSessionStatus.PAUSED)

    def complete_session(self, session_id: str) -> RuntimeSessionRecord:
        return self._update_status(session_id, RuntimeSessionStatus.COMPLETED)

    def update_objective(self, session_id: str, objective: str | None) -> RuntimeSessionRecord:
        record = self._require_session(session_id)
        self._contexts[session_id].set_current_objective(objective)
        updated = record.model_copy(update={"objective": objective, "updated_at": datetime.now(UTC)})
        self._sessions[session_id] = updated
        return updated.model_copy(deep=True)

    def _update_status(self, session_id: str, status: RuntimeSessionStatus) -> RuntimeSessionRecord:
        record = self._require_session(session_id)
        updated = record.model_copy(update={"status": status, "updated_at": datetime.now(UTC)})
        self._sessions[session_id] = updated
        return updated.model_copy(deep=True)

    def _require_session(self, session_id: str) -> RuntimeSessionRecord:
        record = self._sessions.get(session_id)
        if record is None:
            raise KeyError(f"Session {session_id} was not found.")
        return record

    def _permissions_for_role(self, role: HarnessAgentRole) -> AgentPermissions:
        if role is HarnessAgentRole.INITIALIZER:
            return AgentPermissions(
                can_scaffold_environment=True,
                can_modify_files=False,
                can_run_verification=False,
                can_manage_git_recovery=False,
            )
        return AgentPermissions(
            can_scaffold_environment=False,
            can_modify_files=True,
            can_run_verification=True,
            can_manage_git_recovery=True,
        )
