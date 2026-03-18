from __future__ import annotations

from collections import defaultdict
from typing import Protocol

from harness.autonomous.storage import AutonomousRunArtifactStore
from harness.schemas.autonomous import AutonomousRepairRunRecord, AutonomousRunEvent, AutonomousRunSnapshot


class AutonomousRunSubscriber(Protocol):
    def __call__(self, event: AutonomousRunEvent) -> None: ...


class InMemoryAutonomousRunEventStream:
    def __init__(self) -> None:
        self._runs: dict[str, AutonomousRepairRunRecord] = {}
        self._events: dict[str, list[AutonomousRunEvent]] = defaultdict(list)
        self._subscribers: dict[str, list[AutonomousRunSubscriber]] = defaultdict(list)

    def upsert_run(self, run: AutonomousRepairRunRecord) -> AutonomousRepairRunRecord:
        self._runs[run.id] = run.model_copy(deep=True)
        return self._runs[run.id].model_copy(deep=True)

    def append_event(self, event: AutonomousRunEvent) -> AutonomousRunEvent:
        stored = event.model_copy(deep=True)
        self._events[event.run_id].append(stored)
        for subscriber in self._subscribers.get(event.run_id, []):
            subscriber(stored.model_copy(deep=True))
        return stored.model_copy(deep=True)

    def subscribe(self, run_id: str, subscriber: AutonomousRunSubscriber) -> None:
        self._subscribers[run_id].append(subscriber)

    def unsubscribe(self, run_id: str, subscriber: AutonomousRunSubscriber) -> None:
        subscribers = self._subscribers.get(run_id)
        if not subscribers:
            return
        self._subscribers[run_id] = [existing for existing in subscribers if existing is not subscriber]

    def has_run(self, run_id: str) -> bool:
        return run_id in self._runs

    def get_snapshot(self, run_id: str) -> AutonomousRunSnapshot:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"Autonomous run {run_id} was not found.")
        return AutonomousRunSnapshot(
            run=run.model_copy(deep=True),
            events=[event.model_copy(deep=True) for event in self._events.get(run_id, [])],
        )


class PersistentAutonomousRunEventStream(InMemoryAutonomousRunEventStream):
    def __init__(self, *, artifact_store: AutonomousRunArtifactStore | None = None) -> None:
        super().__init__()
        self._artifact_store = artifact_store or AutonomousRunArtifactStore()

    @property
    def artifact_store(self) -> AutonomousRunArtifactStore:
        return self._artifact_store

    def upsert_run(self, run: AutonomousRepairRunRecord) -> AutonomousRepairRunRecord:
        stored = super().upsert_run(run)
        self._artifact_store.persist_snapshot(self.get_snapshot(run.id))
        self._maybe_persist_outcome(run.id)
        return stored

    def append_event(self, event: AutonomousRunEvent) -> AutonomousRunEvent:
        stored = super().append_event(event)
        run = self._runs.get(event.run_id)
        if run is not None:
            self._artifact_store.append_event(run, stored)
            self._artifact_store.persist_snapshot(self.get_snapshot(event.run_id))
            self._maybe_persist_outcome(event.run_id)
        return stored

    def _maybe_persist_outcome(self, run_id: str) -> None:
        snapshot = self.get_snapshot(run_id)
        if snapshot.run.status.value not in {"succeeded", "failed", "cancelled"}:
            self._artifact_store.clear_outcome(snapshot.run.incident_id, run_id)
            return
        self._artifact_store.persist_outcome(snapshot)
