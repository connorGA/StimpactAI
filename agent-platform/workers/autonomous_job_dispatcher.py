from __future__ import annotations

from api.repositories.async_job_repository import AsyncJobRepository
from models.async_job import AsyncJobStatus, AsyncJobType
from services.autonomous_runs import AutonomousRunService


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
        jobs = await self._repository.lease_jobs(limit=limit, job_type=AsyncJobType.AUTONOMOUS_REPAIR)
        processed = 0

        for job in jobs:
            processed += 1
            try:
                await self._service.process_async_job(job)
                await self._repository.mark_job_status(job.id, status=AsyncJobStatus.SUCCEEDED)
                await self._repository.create_job_attempt(
                    async_job_id=job.id,
                    worker_id=self._worker_id,
                    status=AsyncJobStatus.SUCCEEDED,
                    finished=True,
                )
            except Exception as exc:  # noqa: BLE001
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

        return processed
