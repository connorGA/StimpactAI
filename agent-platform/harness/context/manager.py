from __future__ import annotations

from harness.schemas.context import (
    ActiveContextWindow,
    CompressedMemoryEntry,
    ContextEvent,
    ContextEventKind,
    DETAIL_TURN_LIMIT,
    PromptReadyContextPacket,
)


class HarnessContextManager:
    def __init__(self, *, detail_turn_limit: int = DETAIL_TURN_LIMIT) -> None:
        self._detail_turn_limit = max(1, detail_turn_limit)
        self._history: list[ContextEvent] = []
        self._active_context = ActiveContextWindow()

    @property
    def raw_history(self) -> list[ContextEvent]:
        return list(self._history)

    def set_current_objective(self, objective: str | None) -> None:
        self._active_context.current_objective = self._normalize_optional_text(objective)

    def set_current_repo_state(self, repo_state: str | None) -> None:
        self._active_context.current_repo_state = self._normalize_optional_text(repo_state)

    def record_event(self, event: ContextEvent) -> None:
        self._history.append(event)
        self._update_active_context(event)

    def get_compressed_memory(self) -> list[CompressedMemoryEntry]:
        if len(self._history) <= self._detail_turn_limit:
            return []
        compressed_events = self._history[: -self._detail_turn_limit]
        return [
            CompressedMemoryEntry(turn_id=event.turn_id, summary=self._compress_event(event))
            for event in compressed_events
        ]

    def get_detailed_recent_turns(self) -> list[ContextEvent]:
        return list(self._history[-self._detail_turn_limit :])

    def get_active_context_window(self) -> ActiveContextWindow:
        return self._active_context.model_copy(deep=True)

    def build_prompt_ready_context(self) -> PromptReadyContextPacket:
        compressed_memory = self.get_compressed_memory()
        detailed_recent_turns = self.get_detailed_recent_turns()
        packet = PromptReadyContextPacket(
            current_objective=self._active_context.current_objective,
            current_repo_state=self._active_context.current_repo_state,
            compressed_memory=[entry.summary for entry in compressed_memory],
            detailed_recent_turns=detailed_recent_turns,
            recent_actions=list(self._active_context.recent_actions),
            recent_file_interactions=list(self._active_context.recent_file_interactions),
            recent_tool_outputs=list(self._active_context.recent_tool_outputs),
        )
        packet.rendered_context = self._render_context(packet)
        return packet

    def _update_active_context(self, event: ContextEvent) -> None:
        if event.repo_state is not None:
            self._active_context.current_repo_state = event.repo_state

        if event.kind in {ContextEventKind.ACTION, ContextEventKind.EDIT, ContextEventKind.GIT_OPERATION}:
            self._append_unique(self._active_context.recent_actions, event.summary)

        for file_path in event.file_paths:
            self._append_unique(self._active_context.recent_file_interactions, file_path)

        if event.tool_output:
            self._append_unique(self._active_context.recent_tool_outputs, event.tool_output)

        self._trim_recent_lists()

    def _append_unique(self, values: list[str], value: str) -> None:
        normalized = value.strip()
        if not normalized:
            return
        if normalized in values:
            values.remove(normalized)
        values.append(normalized)

    def _trim_recent_lists(self) -> None:
        self._active_context.recent_actions = self._active_context.recent_actions[-5:]
        self._active_context.recent_file_interactions = self._active_context.recent_file_interactions[-10:]
        self._active_context.recent_tool_outputs = self._active_context.recent_tool_outputs[-5:]

    def _compress_event(self, event: ContextEvent) -> str:
        parts = [f"turn {event.turn_id}", f"[{event.kind.value}]"]
        parts.append(event.summary)
        if event.file_paths:
            parts.append(f"files={','.join(event.file_paths[:3])}")
        if event.tool_name:
            parts.append(f"tool={event.tool_name}")
        if event.repo_state:
            parts.append(f"repo={event.repo_state}")
        compressed = " ".join(parts)
        return compressed[:500]

    def _render_context(self, packet: PromptReadyContextPacket) -> str:
        lines: list[str] = []
        lines.append(f"Current objective: {packet.current_objective or 'none'}")
        lines.append(f"Current repo state: {packet.current_repo_state or 'unknown'}")
        lines.append("Compressed memory:")
        if packet.compressed_memory:
            lines.extend(f"- {entry}" for entry in packet.compressed_memory)
        else:
            lines.append("- none")
        lines.append("Recent detailed turns:")
        if packet.detailed_recent_turns:
            for event in packet.detailed_recent_turns:
                lines.append(f"- turn {event.turn_id} [{event.kind.value}] {event.summary}")
        else:
            lines.append("- none")
        lines.append("Recent actions:")
        lines.extend(f"- {action}" for action in packet.recent_actions) if packet.recent_actions else lines.append("- none")
        lines.append("Recent file interactions:")
        (
            lines.extend(f"- {file_path}" for file_path in packet.recent_file_interactions)
            if packet.recent_file_interactions
            else lines.append("- none")
        )
        lines.append("Recent tool outputs:")
        lines.extend(f"- {output}" for output in packet.recent_tool_outputs) if packet.recent_tool_outputs else lines.append("- none")
        return "\n".join(lines)

    def _normalize_optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None
