from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from harness.context.manager import HarnessContextManager
from harness.runtime.session import HarnessRuntime, RuntimePrimitives
from harness.schemas.browser import BrowserAction
from harness.schemas.context import ContextEvent, ContextEventKind
from harness.schemas.editing import EditFileRequest, EditFileResponse
from harness.schemas.git import GitAction, GitActionResult
from harness.schemas.initializer import FeatureCatalog, FeatureRecord
from harness.schemas.orchestrator import (
    CodingHandoffResult,
    GenerateInitializerOutputRequest,
    HarnessSessionSnapshot,
    OrchestratorSessionStartRequest,
    ToolCategory,
    ToolDescriptor,
    ToolInvocationRequest,
    ToolInvocationResult,
    ToolRegistrySnapshot,
    UpdateObjectiveRequest,
)
from harness.schemas.runtime import HarnessAgentRole, InitializerOutputContract, RuntimeSessionRecord
from harness.schemas.search import FindFileRequest, SearchDirRequest, SearchFileRequest
from harness.schemas.verification import FeatureVerificationState
from harness.schemas.viewer import FileViewAtLineRequest, FileViewRequest
from harness.tools import search_tools


@dataclass(slots=True)
class _RegisteredTool:
    descriptor: ToolDescriptor
    handler: Callable[[RuntimeSessionRecord, RuntimePrimitives, dict[str, Any]], BaseModel]


class HarnessSessionOrchestrator:
    def __init__(self, *, runtime: HarnessRuntime | None = None) -> None:
        self._runtime = runtime or HarnessRuntime()
        self._turn_counts: dict[str, int] = {}
        self._tool_history: dict[str, list[str]] = {}
        self._feature_catalogs: dict[str, FeatureCatalog | None] = {}
        self._tool_registry = self._build_tool_registry()

    def initialize_session(self, request: OrchestratorSessionStartRequest) -> HarnessSessionSnapshot:
        inherited_initializer_output = None
        if request.initializer_session_id is not None:
            initializer_session = self._require_session(request.initializer_session_id)
            inherited_initializer_output = initializer_session.initializer_output
            if inherited_initializer_output is None:
                raise ValueError("Initializer session does not have persisted initializer output.")

        session = self._runtime.start_session(
            role=request.role,
            repository_root=request.repository_root,
            objective=request.objective,
            initializer_output=inherited_initializer_output,
        )
        self._turn_counts[session.id] = 0
        self._tool_history[session.id] = []
        self._feature_catalogs[session.id] = (
            inherited_initializer_output.feature_catalog.model_copy(deep=True)
            if inherited_initializer_output is not None
            else None
        )
        return self.restore_session(session.id)

    def restore_session(self, session_id: str) -> HarnessSessionSnapshot:
        session = self._require_session(session_id)
        return self._build_snapshot(session)

    def update_objective(self, session_id: str, request: UpdateObjectiveRequest) -> HarnessSessionSnapshot:
        self._runtime.update_objective(session_id, request.objective)
        return self.restore_session(session_id)

    def list_available_tools(self, session_id: str) -> ToolRegistrySnapshot:
        session = self._require_session(session_id)
        return ToolRegistrySnapshot(
            session_id=session.id,
            role=session.role,
            tools=self._available_descriptors(session),
        )

    def build_prompt_context(self, session_id: str):
        primitives = self._runtime.get_runtime_primitives(session_id)
        return primitives.context_manager.build_prompt_ready_context()

    def generate_initializer_output(
        self,
        session_id: str,
        request: GenerateInitializerOutputRequest,
    ) -> InitializerOutputContract:
        session = self._require_session(session_id)
        primitives = self._runtime.get_runtime_primitives(session_id)
        if session.role is not HarnessAgentRole.INITIALIZER:
            raise PermissionError("Only initializer sessions can generate initializer outputs.")
        return primitives.initializer_output_builder.build_output(
            repository_root=session.repository_root,
            repository_profile=session.repository_profile,
            summary=request.summary,
            feature_seeds=request.feature_seeds or None,
            environment_notes=request.environment_notes,
            known_constraints=request.known_constraints,
        )

    def persist_initializer_output(
        self,
        session_id: str,
        initializer_output: InitializerOutputContract,
    ) -> HarnessSessionSnapshot:
        session = self._require_session(session_id)
        primitives = self._runtime.get_runtime_primitives(session_id)
        primitives.initializer_output_builder.persist_output(
            repository_root=session.repository_root,
            initializer_output=initializer_output,
        )
        updated = self._runtime.persist_initializer_output(session_id, initializer_output)
        self._feature_catalogs[session_id] = initializer_output.feature_catalog.model_copy(deep=True)
        return self._build_snapshot(updated)

    def build_coding_handoff(
        self,
        *,
        initializer_session_id: str,
        coding_session_id: str,
    ) -> CodingHandoffResult:
        coding_input = self._runtime.build_coding_agent_input(
            initializer_session_id=initializer_session_id,
            coding_session_id=coding_session_id,
        )
        return CodingHandoffResult(
            coding_input=coding_input,
            coding_session=self.restore_session(coding_session_id),
            initializer_session=self.restore_session(initializer_session_id),
        )

    def invoke_tool(self, session_id: str, request: ToolInvocationRequest) -> ToolInvocationResult:
        session = self._require_session(session_id)
        primitives = self._runtime.get_runtime_primitives(session_id)
        registered_tool = self._require_registered_tool(session, request.tool_name)
        normalized_arguments = self._normalize_arguments(session, request.tool_name, request.arguments)
        result_model = registered_tool.handler(session, primitives, normalized_arguments)
        feature_state = self._apply_feature_updates(session_id, request, result_model)
        turn_id = self._record_tool_event(
            session_id=session_id,
            request=request,
            result_model=result_model,
            feature_state=feature_state,
        )
        self._tool_history.setdefault(session_id, []).append(request.tool_name)
        return ToolInvocationResult(
            session_id=session_id,
            tool_name=request.tool_name,
            ok=bool(getattr(result_model, "ok", True)),
            turn_id=turn_id,
            result=result_model.model_dump(mode="json"),
            prompt_context=primitives.context_manager.build_prompt_ready_context(),
            feature_state=feature_state.model_copy(deep=True) if feature_state is not None else None,
        )

    def _build_snapshot(self, session: RuntimeSessionRecord) -> HarnessSessionSnapshot:
        prompt_context = self._runtime.get_runtime_primitives(session.id).context_manager.build_prompt_ready_context()
        return HarnessSessionSnapshot(
            session=session,
            prompt_context=prompt_context,
            feature_catalog=self._feature_catalogs.get(session.id),
            available_tools=self.list_available_tools(session.id),
            turn_count=self._turn_counts.get(session.id, 0),
            tool_call_count=len(self._tool_history.get(session.id, [])),
        )

    def _require_session(self, session_id: str) -> RuntimeSessionRecord:
        session = self._runtime.get_session(session_id)
        if session is None:
            raise KeyError(f"Session {session_id} was not found.")
        return session

    def _available_descriptors(self, session: RuntimeSessionRecord) -> list[ToolDescriptor]:
        available: list[ToolDescriptor] = []
        for registered in self._tool_registry.values():
            descriptor = registered.descriptor
            if descriptor.requires_modify_files and not session.permissions.can_modify_files:
                continue
            if descriptor.requires_verification and not session.permissions.can_run_verification:
                continue
            if descriptor.requires_git_recovery and not session.permissions.can_manage_git_recovery:
                continue
            available.append(descriptor)
        available.sort(key=lambda item: (item.category.value, item.name))
        return available

    def _require_registered_tool(self, session: RuntimeSessionRecord, tool_name: str) -> _RegisteredTool:
        registered = self._tool_registry.get(tool_name)
        if registered is None:
            raise KeyError(f"Tool {tool_name} is not registered.")
        descriptor = registered.descriptor
        if descriptor.requires_modify_files and not session.permissions.can_modify_files:
            raise PermissionError(f"Tool {tool_name} requires file modification permissions.")
        if descriptor.requires_verification and not session.permissions.can_run_verification:
            raise PermissionError(f"Tool {tool_name} requires verification permissions.")
        if descriptor.requires_git_recovery and not session.permissions.can_manage_git_recovery:
            raise PermissionError(f"Tool {tool_name} requires git recovery permissions.")
        return registered

    def _normalize_arguments(
        self,
        session: RuntimeSessionRecord,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(arguments)
        if tool_name in {"find_file", "search_dir"} and "root_path" not in normalized:
            normalized["root_path"] = session.repository_root

        for key in ("root_path", "file_path", "output_path"):
            if key in normalized and isinstance(normalized[key], str):
                path_value = normalized[key]
                if not path_value.startswith("/") and not self._looks_like_url(path_value):
                    normalized[key] = str((Path(session.repository_root) / path_value).resolve())
        return normalized

    def _record_tool_event(
        self,
        *,
        session_id: str,
        request: ToolInvocationRequest,
        result_model: BaseModel,
        feature_state: FeatureVerificationState | None,
    ) -> int:
        primitives = self._runtime.get_runtime_primitives(session_id)
        turn_id = self._next_turn_id(session_id)
        ok = bool(getattr(result_model, "ok", True))
        event_kind = self._event_kind_for_request(request)
        summary = request.summary or self._build_summary(request.tool_name, ok, result_model)
        details = self._truncate(json.dumps(result_model.model_dump(mode="json"), default=str), 5000)
        tool_output = self._build_tool_output(result_model, feature_state)
        file_paths = self._extract_file_paths(request, result_model)
        repo_state = self._repo_state_for_tool(request.tool_name, ok)
        primitives.context_manager.record_event(
            ContextEvent(
                turn_id=turn_id,
                kind=event_kind,
                summary=summary,
                details=details,
                file_paths=file_paths,
                tool_name=request.tool_name,
                tool_output=tool_output,
                repo_state=repo_state,
            )
        )
        return turn_id

    def _event_kind_for_request(self, request: ToolInvocationRequest) -> ContextEventKind:
        if request.verification_kind is not None:
            return ContextEventKind.VERIFICATION
        if request.tool_name in {"edit_file"}:
            return ContextEventKind.EDIT
        if request.tool_name in {
            GitAction.CURRENT_BRANCH_INFO.value,
            GitAction.CHECKPOINT.value,
            GitAction.REVERT_TO_CHECKPOINT.value,
            GitAction.RESET_FAILED_ATTEMPT.value,
            GitAction.DISCARD_FAILED_WORK.value,
            GitAction.DIFF_SINCE_CHECKPOINT.value,
        }:
            return ContextEventKind.GIT_OPERATION
        if request.tool_name in {"open_file", "view_next", "view_prev", "view_at_line", "view_centered"}:
            return ContextEventKind.OBSERVATION
        return ContextEventKind.ACTION

    def _build_summary(self, tool_name: str, ok: bool, result_model: BaseModel) -> str:
        verb = "Succeeded" if ok else "Failed"
        message = getattr(result_model, "message", None) or getattr(result_model, "output", None)
        if isinstance(message, str) and message.strip():
            return self._truncate(f"{verb} {tool_name}: {message.strip()}", 500)
        return f"{verb} {tool_name}"

    def _build_tool_output(
        self,
        result_model: BaseModel,
        feature_state: FeatureVerificationState | None,
    ) -> str:
        message = getattr(result_model, "message", None) or getattr(result_model, "output", None)
        if isinstance(message, str) and message.strip():
            output = message.strip()
        else:
            output = self._truncate(json.dumps(result_model.model_dump(mode="json"), default=str), 500)
        if feature_state is not None:
            blockers = ", ".join(feature_state.completion_blockers[:2]) or "none"
            output = f"{output} | feature_status={feature_state.status.value} blockers={blockers}"
        return self._truncate(output, 2000)

    def _extract_file_paths(self, request: ToolInvocationRequest, result_model: BaseModel) -> list[str]:
        paths: list[str] = []
        for key in ("file_path", "root_path", "output_path"):
            value = request.arguments.get(key)
            if isinstance(value, str):
                paths.append(value)
        if isinstance(result_model, EditFileResponse):
            paths.append(result_model.file_path)
        if isinstance(result_model, GitActionResult) and result_model.diff is not None:
            paths.extend(change.path for change in result_model.diff.changed_files[:10])
        deduped: list[str] = []
        for path in paths:
            if path not in deduped:
                deduped.append(path)
        return deduped[:10]

    def _repo_state_for_tool(self, tool_name: str, ok: bool) -> str | None:
        if not ok:
            return None
        if tool_name == "edit_file":
            return "code changed"
        if tool_name in {
            GitAction.CHECKPOINT.value,
            GitAction.REVERT_TO_CHECKPOINT.value,
            GitAction.RESET_FAILED_ATTEMPT.value,
            GitAction.DISCARD_FAILED_WORK.value,
        }:
            return "git recovery updated"
        if tool_name in {
            BrowserAction.ASSERT_TEXT.value,
            BrowserAction.WAIT_FOR.value,
            BrowserAction.CURRENT_PAGE_STATE.value,
        }:
            return "verification evidence captured"
        return None

    def _apply_feature_updates(
        self,
        session_id: str,
        request: ToolInvocationRequest,
        result_model: BaseModel,
    ) -> FeatureVerificationState | None:
        catalog = self._feature_catalogs.get(session_id)
        if catalog is None or request.feature_id is None:
            return None
        feature = self._find_feature(catalog, request.feature_id)
        primitives = self._runtime.get_runtime_primitives(session_id)
        updated_state = feature.verification_state

        if request.tool_name == "edit_file" and bool(getattr(result_model, "ok", False)):
            updated_state = primitives.verification_rules_engine.mark_code_changed(updated_state)

        if request.verification_kind is not None:
            summary = request.summary or getattr(result_model, "message", None) or getattr(result_model, "output", None) or request.tool_name
            updated_state = primitives.verification_rules_engine.record_attempt(
                state=updated_state,
                kind=request.verification_kind,
                passed=bool(getattr(result_model, "ok", False)),
                summary=str(summary),
            )

        feature.verification_state = updated_state
        return updated_state

    def _find_feature(self, catalog: FeatureCatalog, feature_id: str) -> FeatureRecord:
        for feature in catalog.features:
            if feature.id == feature_id:
                return feature
        raise KeyError(f"Feature {feature_id} was not found in the session feature catalog.")

    def _next_turn_id(self, session_id: str) -> int:
        next_turn = self._turn_counts.get(session_id, 0) + 1
        self._turn_counts[session_id] = next_turn
        return next_turn

    def _looks_like_url(self, value: str) -> bool:
        return value.startswith("http://") or value.startswith("https://")

    def _truncate(self, value: str, limit: int) -> str:
        return value if len(value) <= limit else f"{value[: limit - 3]}..."

    def _build_tool_registry(self) -> dict[str, _RegisteredTool]:
        registry: dict[str, _RegisteredTool] = {}

        def register(
            name: str,
            description: str,
            category: ToolCategory,
            handler: Callable[[RuntimeSessionRecord, RuntimePrimitives, dict[str, Any]], BaseModel],
            *,
            requires_modify_files: bool = False,
            requires_verification: bool = False,
            requires_git_recovery: bool = False,
        ) -> None:
            registry[name] = _RegisteredTool(
                descriptor=ToolDescriptor(
                    name=name,
                    description=description,
                    category=category,
                    requires_modify_files=requires_modify_files,
                    requires_verification=requires_verification,
                    requires_git_recovery=requires_git_recovery,
                ),
                handler=handler,
            )

        register(
            "find_file",
            "Find files in repository",
            ToolCategory.SEARCH,
            lambda session, primitives, args: search_tools.find_file(FindFileRequest.model_validate(args)),
        )
        register(
            "search_dir",
            "Search text across directory",
            ToolCategory.SEARCH,
            lambda session, primitives, args: search_tools.search_dir(SearchDirRequest.model_validate(args)),
        )
        register(
            "search_file",
            "Search text within file",
            ToolCategory.SEARCH,
            lambda session, primitives, args: search_tools.search_file(SearchFileRequest.model_validate(args)),
        )
        register(
            "open_file",
            "Open file page",
            ToolCategory.VIEW,
            lambda session, primitives, args: primitives.file_viewer.open_file(FileViewRequest.model_validate(args)),
        )
        register(
            "view_next",
            "View next page",
            ToolCategory.VIEW,
            lambda session, primitives, args: primitives.file_viewer.view_next(FileViewRequest.model_validate(args)),
        )
        register(
            "view_prev",
            "View previous page",
            ToolCategory.VIEW,
            lambda session, primitives, args: primitives.file_viewer.view_prev(FileViewRequest.model_validate(args)),
        )
        register(
            "view_at_line",
            "Jump to line",
            ToolCategory.VIEW,
            lambda session, primitives, args: primitives.file_viewer.view_at_line(
                FileViewAtLineRequest.model_validate(args)
            ),
        )
        register(
            "view_centered",
            "Center on line",
            ToolCategory.VIEW,
            lambda session, primitives, args: primitives.file_viewer.view_centered(
                FileViewAtLineRequest.model_validate(args)
            ),
        )
        register(
            "edit_file",
            "Edit file with validation",
            ToolCategory.EDIT,
            lambda session, primitives, args: primitives.file_editor.edit_file(EditFileRequest.model_validate(args)),
            requires_modify_files=True,
        )
        register(
            "browser_open",
            "Open browser page",
            ToolCategory.BROWSER,
            lambda session, primitives, args: primitives.browser_tools.browser_open(**args),
            requires_verification=True,
        )
        register(
            "browser_click",
            "Click browser element",
            ToolCategory.BROWSER,
            lambda session, primitives, args: primitives.browser_tools.browser_click(**args),
            requires_verification=True,
        )
        register(
            "browser_type",
            "Type into browser element",
            ToolCategory.BROWSER,
            lambda session, primitives, args: primitives.browser_tools.browser_type(**args),
            requires_verification=True,
        )
        register(
            "browser_wait_for",
            "Wait for browser condition",
            ToolCategory.BROWSER,
            lambda session, primitives, args: primitives.browser_tools.browser_wait_for(**args),
            requires_verification=True,
        )
        register(
            "browser_assert_text",
            "Assert browser text",
            ToolCategory.BROWSER,
            lambda session, primitives, args: primitives.browser_tools.browser_assert_text(**args),
            requires_verification=True,
        )
        register(
            "browser_snapshot_dom",
            "Capture browser DOM snapshot",
            ToolCategory.BROWSER,
            lambda session, primitives, args: primitives.browser_tools.browser_snapshot_dom(**args),
            requires_verification=True,
        )
        register(
            "browser_screenshot",
            "Capture browser screenshot",
            ToolCategory.BROWSER,
            lambda session, primitives, args: primitives.browser_tools.browser_screenshot(**args),
            requires_verification=True,
        )
        register(
            "browser_get_url",
            "Get current browser URL",
            ToolCategory.BROWSER,
            lambda session, primitives, args: primitives.browser_tools.browser_get_url(**args),
            requires_verification=True,
        )
        register(
            "dom_snapshot",
            "Capture DOM snapshot",
            ToolCategory.BROWSER,
            lambda session, primitives, args: primitives.browser_tools.dom_snapshot(**args),
            requires_verification=True,
        )
        register(
            "take_screenshot",
            "Capture screenshot",
            ToolCategory.BROWSER,
            lambda session, primitives, args: primitives.browser_tools.take_screenshot(**args),
            requires_verification=True,
        )
        register(
            "capture_console_logs",
            "Capture console logs",
            ToolCategory.BROWSER,
            lambda session, primitives, args: primitives.browser_tools.capture_console_logs(**args),
            requires_verification=True,
        )
        register(
            "capture_network_summary",
            "Capture network summary",
            ToolCategory.BROWSER,
            lambda session, primitives, args: primitives.browser_tools.capture_network_summary(**args),
            requires_verification=True,
        )
        register(
            "current_page_state",
            "Capture current page state",
            ToolCategory.BROWSER,
            lambda session, primitives, args: primitives.browser_tools.current_page_state(**args),
            requires_verification=True,
        )
        register(
            "browser_close",
            "Close browser session",
            ToolCategory.BROWSER,
            lambda session, primitives, args: primitives.browser_tools.browser_close(**args),
            requires_verification=True,
        )
        register(
            GitAction.CURRENT_BRANCH_INFO.value,
            "Inspect current branch state",
            ToolCategory.GIT,
            lambda session, primitives, args: primitives.git_checkpoint_manager.current_branch_info(
                repository_root=session.repository_root
            ),
            requires_git_recovery=True,
        )
        register(
            GitAction.CHECKPOINT.value,
            "Create checkpoint commit",
            ToolCategory.GIT,
            lambda session, primitives, args: primitives.git_checkpoint_manager.create_checkpoint(
                repository_root=session.repository_root,
                label=str(args["label"]),
            ),
            requires_git_recovery=True,
        )
        register(
            GitAction.REVERT_TO_CHECKPOINT.value,
            "Revert to checkpoint",
            ToolCategory.GIT,
            lambda session, primitives, args: primitives.git_checkpoint_manager.revert_to_checkpoint(
                repository_root=session.repository_root,
                checkpoint_ref=args.get("checkpoint_ref"),
            ),
            requires_git_recovery=True,
        )
        register(
            GitAction.RESET_FAILED_ATTEMPT.value,
            "Reset failed attempt",
            ToolCategory.GIT,
            lambda session, primitives, args: primitives.git_checkpoint_manager.reset_failed_attempt(
                repository_root=session.repository_root,
                checkpoint_ref=args.get("checkpoint_ref"),
            ),
            requires_git_recovery=True,
        )
        register(
            GitAction.DISCARD_FAILED_WORK.value,
            "Discard failed work",
            ToolCategory.GIT,
            lambda session, primitives, args: primitives.git_checkpoint_manager.discard_failed_work(
                repository_root=session.repository_root,
                checkpoint_ref=args.get("checkpoint_ref"),
            ),
            requires_git_recovery=True,
        )
        register(
            GitAction.DIFF_SINCE_CHECKPOINT.value,
            "Inspect diff since checkpoint",
            ToolCategory.GIT,
            lambda session, primitives, args: primitives.git_checkpoint_manager.diff_since_checkpoint(
                repository_root=session.repository_root,
                checkpoint_ref=args.get("checkpoint_ref"),
            ),
            requires_git_recovery=True,
        )
        return registry
