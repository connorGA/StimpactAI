from __future__ import annotations

from datetime import UTC, datetime

from models.async_job import AsyncJobRecord, AsyncJobStatus, AsyncJobType
from workers.sandbox_job_dispatcher import SandboxJobDispatcher


class StubAsyncJobRepository:
    def __init__(self) -> None:
        now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
        self.job = AsyncJobRecord(
            id="job-1",
            job_type=AsyncJobType.SANDBOX_RUN,
            status=AsyncJobStatus.RUNNING,
            dedupe_key="sandbox:incident-1:patch-1",
            payload={"incident_id": "incident-1", "repo_profile_id": "profile-1"},
            attempts=1,
            available_at=now,
            lease_expires_at=now,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        self.marked_statuses: list[tuple[str, AsyncJobStatus, str | None]] = []
        self.attempts: list[tuple[str, AsyncJobStatus]] = []

    async def lease_jobs(self, *, limit: int = 10, lease_seconds: int = 300) -> list[AsyncJobRecord]:
        assert limit == 10
        _ = lease_seconds
        return [self.job]

    async def mark_job_status(
        self,
        job_id: str,
        *,
        status: AsyncJobStatus,
        last_error: str | None = None,
    ) -> AsyncJobRecord:
        self.marked_statuses.append((job_id, status, last_error))
        return self.job

    async def create_job_attempt(
        self,
        *,
        async_job_id: str,
        worker_id: str,
        status: AsyncJobStatus,
        error_message: str | None = None,
        finished: bool = False,
    ):
        _ = (worker_id, error_message, finished)
        self.attempts.append((async_job_id, status))
        return None


class StubSandboxVerificationService:
    def __init__(self) -> None:
        self.processed_job_ids: list[str] = []

    async def process_async_job(self, job: AsyncJobRecord):
        self.processed_job_ids.append(job.id)
        return None


async def test_sandbox_job_dispatcher_processes_async_jobs() -> None:
    repository = StubAsyncJobRepository()
    service = StubSandboxVerificationService()
    dispatcher = SandboxJobDispatcher(repository, service)

    processed = await dispatcher.run_once()

    assert processed == 1
    assert service.processed_job_ids == ["job-1"]
    assert repository.marked_statuses == [("job-1", AsyncJobStatus.SUCCEEDED, None)]
    assert repository.attempts == [("job-1", AsyncJobStatus.SUCCEEDED)]
