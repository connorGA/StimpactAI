from __future__ import annotations

import logging

from api.core.config import get_async_job_stale_lease_seconds
from api.repositories.async_job_repository import AsyncJobRepository
from models.async_job import AsyncJobStatus, AsyncJobType
from services.autonomous_runs import AutonomousRunService

logger = logging.getLogger(__name__)


class AutonomousJobDispatcher:
    def __init__(
        self,
        repository: AsyncJobRepository,
        service: AutonomousRunService,
        *,
        worker_id: str = "autonomous-dispatcher",
    ) -> None:
        self._repository = repository
        self._service = service
        self._worker_id = worker_id

    async def run_once(self, *, limit: int = 10) -> int:
        reclaimed = await self._repository.reclaim_expired_leases(
            stale_after_seconds=get_async_job_stale_lease_seconds(),
            job_type=AsyncJobType.AUTONOMOUS_REPAIR,
        )
        if reclaimed:
            logger.info("Reclaimed %d stale autonomous job lease(s)", len(reclaimed))
        jobs = await self._repository.lease_jobs(limit=limit, job_type=AsyncJobType.AUTONOMOUS_REPAIR)
        processed = 0

        for job in jobs:
            processed += 1
            run_id = str(job.payload.get("autonomous_run_id", "?"))
            incident_id = str(job.payload.get("incident_id", "?"))
            logger.info(
                "Processing autonomous job %s (run=%s, incident=%s)",
                job.id, run_id, incident_id,
            )
            try:
                detail = await self._service.process_async_job(job)
                run = detail.run
                run_terminal_error = (
                    f"Worker completed; autonomous run ended with status={run.status.value}"
                    if run.last_error
                    else None
                )
                await self._repository.mark_job_status(job.id, status=AsyncJobStatus.SUCCEEDED)
                await self._repository.create_job_attempt(
                    async_job_id=job.id,
                    worker_id=self._worker_id,
                    status=AsyncJobStatus.SUCCEEDED,
                    error_message=run_terminal_error,
                    finished=True,
                )
                logger.info(
                    "Autonomous job %s completed worker execution",
                    job.id,
                    extra={
                        "run_id": run_id,
                        "incident_id": incident_id,
                        "run_status": run.status.value,
                        "run_phase": run.phase.value,
                        "promotion_status": run.promotion_status.value,
                        "run_last_error": run.last_error,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Autonomous job %s failed (run=%s)", job.id, run_id,
                )
                await self._repository.mark_job_status(
                    job.id,
                    status=AsyncJobStatus.FAILED,
                    last_error=str(exc),
                )
                await self._repository.create_job_attempt(
                    async_job_id=job.id,
                    worker_id=self._worker_id,
                    status=AsyncJobStatus.FAILED,
                    error_message=str(exc),
                    finished=True,
                )
                await self._service.mark_run_failed(
                    incident_id=incident_id,
                    run_id=run_id,
                    error=str(exc),
                )

        if processed:
            logger.info("Processed %d autonomous job(s) this cycle", processed)
        return processed
