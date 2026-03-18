from __future__ import annotations

import json
from pathlib import Path

from api.core.config import get_repository_root
from harness.schemas.autonomous import (
    AutonomousArtifactPaths,
    AutonomousEventType,
    AutonomousRepairRunRecord,
    AutonomousRunEvent,
    AutonomousRunOutcome,
    AutonomousRunSnapshot,
)


class AutonomousRunArtifactStore:
    def __init__(self, *, base_directory: Path | None = None) -> None:
        repository_root = get_repository_root()
        self._base_directory = base_directory or (repository_root / ".stimpactai" / "autonomous-runs")

    def persist_snapshot(self, snapshot: AutonomousRunSnapshot) -> AutonomousArtifactPaths:
        artifact_paths = self.get_artifact_paths(snapshot.run.incident_id, snapshot.run.id)
        self._write_json(Path(artifact_paths.snapshot_path), snapshot.model_dump(mode="json"))
        return artifact_paths

    def append_event(self, run: AutonomousRepairRunRecord, event: AutonomousRunEvent) -> AutonomousArtifactPaths:
        artifact_paths = self.get_artifact_paths(run.incident_id, run.id)
        events_path = Path(artifact_paths.events_path)
        events_path.parent.mkdir(parents=True, exist_ok=True)
        with events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(mode="json"), sort_keys=True))
            handle.write("\n")
        return artifact_paths

    def persist_outcome(self, snapshot: AutonomousRunSnapshot) -> AutonomousRunOutcome:
        artifact_paths = self.get_artifact_paths(snapshot.run.incident_id, snapshot.run.id)
        outcome = self.build_outcome(snapshot)
        self._write_json(Path(artifact_paths.outcome_path or self._outcome_path(snapshot.run.incident_id, snapshot.run.id)), outcome.model_dump(mode="json"))
        return outcome

    def list_runs(self, incident_id: str) -> list[AutonomousRepairRunRecord]:
        incident_directory = self._incident_directory(incident_id)
        if not incident_directory.exists():
            return []

        runs: list[AutonomousRepairRunRecord] = []
        for snapshot_path in incident_directory.glob("*/snapshot.json"):
            snapshot = self._read_snapshot_file(snapshot_path)
            runs.append(snapshot.run)
        return sorted(runs, key=lambda run: run.updated_at, reverse=True)

    def get_snapshot(self, incident_id: str, run_id: str) -> AutonomousRunSnapshot:
        return self._read_snapshot_file(self._snapshot_path(incident_id, run_id))

    def get_outcome(self, incident_id: str, run_id: str) -> AutonomousRunOutcome | None:
        outcome_path = self._outcome_path(incident_id, run_id)
        if not outcome_path.exists():
            return None
        return AutonomousRunOutcome.model_validate_json(outcome_path.read_text(encoding="utf-8"))

    def get_latest_run_id(self, incident_id: str) -> str | None:
        runs = self.list_runs(incident_id)
        if not runs:
            return None
        return runs[0].id

    def get_artifact_paths(self, incident_id: str | None, run_id: str) -> AutonomousArtifactPaths:
        return AutonomousArtifactPaths(
            snapshot_path=str(self._snapshot_path(incident_id, run_id)),
            events_path=str(self._events_path(incident_id, run_id)),
            outcome_path=str(self._outcome_path(incident_id, run_id)),
        )

    def build_outcome(self, snapshot: AutonomousRunSnapshot) -> AutonomousRunOutcome:
        run = snapshot.run
        events = snapshot.events
        return AutonomousRunOutcome(
            run_id=run.id,
            incident_id=run.incident_id,
            status=run.status,
            phase=run.phase,
            objective=run.objective,
            repository_root=run.repository_root,
            checkpoint_ref=run.loop_state.checkpoint_ref,
            recovery_attempts=run.loop_state.recovery_attempts,
            total_steps=run.loop_state.step_index,
            total_decisions=sum(1 for event in events if event.event_type is AutonomousEventType.DECISION_MADE),
            total_tool_calls=sum(1 for event in events if event.event_type is AutonomousEventType.TOOL_CALL_COMPLETED),
            total_events=len(events),
            last_error=run.last_error,
            created_at=run.created_at,
            completed_at=run.updated_at,
        )

    def _snapshot_path(self, incident_id: str | None, run_id: str) -> Path:
        return self._run_directory(incident_id, run_id) / "snapshot.json"

    def _events_path(self, incident_id: str | None, run_id: str) -> Path:
        return self._run_directory(incident_id, run_id) / "events.jsonl"

    def _outcome_path(self, incident_id: str | None, run_id: str) -> Path:
        return self._run_directory(incident_id, run_id) / "outcome.json"

    def _incident_directory(self, incident_id: str | None) -> Path:
        return self._base_directory / (incident_id or "_unscoped")

    def _run_directory(self, incident_id: str | None, run_id: str) -> Path:
        return self._incident_directory(incident_id) / run_id

    def _read_snapshot_file(self, snapshot_path: Path) -> AutonomousRunSnapshot:
        if not snapshot_path.exists():
            raise KeyError(f"Autonomous run snapshot {snapshot_path} was not found.")
        return AutonomousRunSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))

    def _write_json(self, destination: Path, payload: object) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(f"{destination.suffix}.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(destination)
