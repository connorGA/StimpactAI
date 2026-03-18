from __future__ import annotations

from harness.context.manager import HarnessContextManager
from harness.schemas.context import ContextEvent, ContextEventKind


def _event(
    turn_id: int,
    *,
    kind: ContextEventKind = ContextEventKind.OBSERVATION,
    summary: str,
    details: str | None = None,
    file_paths: list[str] | None = None,
    tool_name: str | None = None,
    tool_output: str | None = None,
    repo_state: str | None = None,
) -> ContextEvent:
    return ContextEvent(
        turn_id=turn_id,
        kind=kind,
        summary=summary,
        details=details,
        file_paths=file_paths or [],
        tool_name=tool_name,
        tool_output=tool_output,
        repo_state=repo_state,
    )


def test_context_manager_keeps_last_five_turns_detailed_and_compresses_older_turns() -> None:
    manager = HarnessContextManager()
    for turn_id in range(1, 8):
        manager.record_event(
            _event(
                turn_id,
                kind=ContextEventKind.ACTION if turn_id % 2 == 0 else ContextEventKind.OBSERVATION,
                summary=f"summary {turn_id}",
                file_paths=[f"file_{turn_id}.py"],
                tool_name="search_file",
                tool_output=f"output {turn_id}",
                repo_state=f"repo state {turn_id}",
            )
        )

    compressed = manager.get_compressed_memory()
    detailed = manager.get_detailed_recent_turns()

    assert [entry.turn_id for entry in compressed] == [1, 2]
    assert [event.turn_id for event in detailed] == [3, 4, 5, 6, 7]
    assert compressed[0].summary == "turn 1 [observation] summary 1 files=file_1.py tool=search_file repo=repo state 1"


def test_context_manager_updates_active_context_from_recent_events() -> None:
    manager = HarnessContextManager()
    manager.set_current_objective("Investigate checkout failure")
    manager.set_current_repo_state("clean main branch")
    manager.record_event(
        _event(
            1,
            kind=ContextEventKind.ACTION,
            summary="Ran search tool",
            file_paths=["src/app.ts"],
            tool_name="search_dir",
            tool_output="Matched 2 files",
            repo_state="working tree clean",
        )
    )
    manager.record_event(
        _event(
            2,
            kind=ContextEventKind.EDIT,
            summary="Edited src/app.ts",
            file_paths=["src/app.ts"],
            tool_output="Replaced lines 10-12",
        )
    )

    active = manager.get_active_context_window()

    assert active.current_objective == "Investigate checkout failure"
    assert active.current_repo_state == "working tree clean"
    assert active.recent_actions == ["Ran search tool", "Edited src/app.ts"]
    assert active.recent_file_interactions == ["src/app.ts"]
    assert active.recent_tool_outputs == ["Matched 2 files", "Replaced lines 10-12"]


def test_prompt_ready_context_packet_includes_rendered_summary() -> None:
    manager = HarnessContextManager()
    manager.set_current_objective("Verify login flow")
    manager.set_current_repo_state("feature branch ahead by 1 commit")
    for turn_id in range(1, 4):
        manager.record_event(
            _event(
                turn_id,
                kind=ContextEventKind.VERIFICATION if turn_id == 3 else ContextEventKind.ACTION,
                summary=f"turn summary {turn_id}",
                file_paths=[f"feature_{turn_id}.tsx"],
                tool_output=f"tool output {turn_id}",
            )
        )

    packet = manager.build_prompt_ready_context()

    assert packet.current_objective == "Verify login flow"
    assert packet.current_repo_state == "feature branch ahead by 1 commit"
    assert len(packet.detailed_recent_turns) == 3
    assert packet.compressed_memory == []
    assert "Current objective: Verify login flow" in packet.rendered_context
    assert "- turn 3 [verification] turn summary 3" in packet.rendered_context
