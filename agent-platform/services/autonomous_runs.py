from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from openai import AsyncOpenAI

from api.core.config import get_openai_api_key, get_repository_root
from api.core.errors import APIError
from api.schemas.autonomous import AutonomousRunCreateRequest, AutonomousRunDetailResponse
from api.repositories.incident_repository import IncidentRepository
from harness.autonomous import OpenAIAutonomousDecisionEngine
from harness.autonomous.events import (
    AutonomousRunSubscriber,
    PersistentAutonomousRunEventStream,
)
from harness.autonomous.runner import AutonomousRepairRunner
from harness.autonomous.storage import AutonomousRunArtifactStore
from harness.schemas.autonomous import AutonomousRepairRunRecord, AutonomousRunStatus


class AutonomousRunService:
    def __init__(
        self,
        incident_repository: IncidentRepository,
        *,
        repository_root: Path | None = None,
        artifact_store: AutonomousRunArtifactStore | None = None,
        event_stream: PersistentAutonomousRunEventStream | None = None,
        runner: AutonomousRepairRunner | None = None,
        decision_engine_factory: Callable[[], OpenAIAutonomousDecisionEngine] | None = None,
    ) -> None:
        self._incident_repository = incident_repository
        self._repository_root = repository_root or get_repository_root()
        self._artifact_store = artifact_store or AutonomousRunArtifactStore()
        self._event_stream = event_stream or PersistentAutonomousRunEventStream(artifact_store=self._artifact_store)
        self._runner = runner or AutonomousRepairRunner(event_stream=self._event_stream)
        self._decision_engine_factory = decision_engine_factory or self._build_decision_engine
        self._active_tasks: dict[str, asyncio.Task[object]] = {}

    async def start_run(
        self,
        incident_id: str,
        request: AutonomousRunCreateRequest,
    ) -> AutonomousRunDetailResponse:
        incident = await self._require_incident(incident_id)
        if not request.feature_seeds:
            raise APIError(
                "Autonomous runs require at least one feature seed so verification can be tracked deterministically.",
                status_code=422,
                code="autonomous_feature_seeds_required",
            )

        decision_engine = self._decision_engine_factory()
        snapshot = self._runner.bootstrap_run(
            incident_id=incident_id,
            repository_root=request.repository_root or str(self._repository_root),
            objective=request.objective
            or f"Investigate, repair, and verify incident '{incident.title}' for service {incident.service}.",
            initializer_summary=request.initializer_summary
            or "Prepare the repository, verification state, and repair context for autonomous incident resolution.",
            feature_seeds=request.feature_seeds,
        )
        task = asyncio.create_task(
            self._runner.continue_run(
                run_id=snapshot.run.id,
                decision_engine=decision_engine,
                max_steps=request.max_steps,
            )
        )
        self._active_tasks[snapshot.run.id] = task
        task.add_done_callback(
            lambda completed_task, run_id=snapshot.run.id: self._finalize_task(run_id, completed_task)
        )
        return self.get_run_detail_sync(incident_id, snapshot.run.id)

    async def list_runs(self, incident_id: str) -> list[AutonomousRepairRunRecord]:
        await self._require_incident(incident_id)
        return self._artifact_store.list_runs(incident_id)

    async def get_latest_run_detail(self, incident_id: str) -> AutonomousRunDetailResponse:
        await self._require_incident(incident_id)
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
        if self._event_stream.has_run(run_id):
            return self._event_stream.get_snapshot(run_id)
        try:
            return self._artifact_store.get_snapshot(incident_id, run_id)
        except KeyError as exc:
            raise APIError(
                f"Autonomous run {run_id} was not found for incident {incident_id}.",
                status_code=404,
                code="autonomous_run_not_found",
            ) from exc

    async def _require_incident(self, incident_id: str):
        incident = await self._incident_repository.get_incident(incident_id)
        if incident is None:
            raise APIError(
                f"Incident {incident_id} was not found.",
                status_code=404,
                code="incident_not_found",
            )
        return incident

    def _build_decision_engine(self) -> OpenAIAutonomousDecisionEngine:
        api_key = get_openai_api_key()
        if api_key is None:
            raise APIError(
                "OPENAI_API_KEY is not configured for autonomous runs.",
                status_code=503,
                code="openai_unconfigured",
            )
        return OpenAIAutonomousDecisionEngine(client=AsyncOpenAI(api_key=api_key))

    def _finalize_task(self, run_id: str, task: asyncio.Task[object]) -> None:
        self._active_tasks.pop(run_id, None)
        try:
            task.result()
        except Exception:
            # The terminal run state and persisted outcome are already recorded by the runner.
            return
