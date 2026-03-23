from __future__ import annotations

from datetime import UTC, datetime

from models.async_job import AsyncJobRecord, AsyncJobStatus, AsyncJobType
from models.sandbox import SandboxRunStatus
from workers.autonomous_job_dispatcher import AutonomousJobDispatcher
from workers.kubernetes_monitor_dispatcher import KubernetesMonitorDispatcher
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
        self.reclaimed_calls: list[tuple[int, AsyncJobType | None]] = []

    async def reclaim_expired_leases(
        self,
        *,
        stale_after_seconds: int = 300,
        job_type: AsyncJobType | None = None,
    ) -> list[AsyncJobRecord]:
        self.reclaimed_calls.append((stale_after_seconds, job_type))
        return []

    async def lease_jobs(
        self,
        *,
        limit: int = 10,
        lease_seconds: int = 300,
        job_type: AsyncJobType | None = None,
    ) -> list[AsyncJobRecord]:
        assert limit == 10
        _ = lease_seconds
        if job_type is not None:
            assert job_type is self.job.job_type
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


class StubAutonomousRunService:
    def __init__(self) -> None:
        self.processed_job_ids: list[str] = []
        self.recorded_sandbox_ids: list[str] = []

    async def process_async_job(self, job: AsyncJobRecord):
        self.processed_job_ids.append(job.id)
        return None

    async def record_sandbox_result(self, sandbox_run) -> None:
        self.recorded_sandbox_ids.append(sandbox_run.id)


class StubKubernetesPollingService:
    def __init__(self, runs) -> None:
        self.runs = runs
        self.polled_limits: list[int] = []

    async def poll_kubernetes_runs(self, *, limit: int = 50):
        self.polled_limits.append(limit)
        return self.runs


async def test_sandbox_job_dispatcher_processes_async_jobs() -> None:
    repository = StubAsyncJobRepository()
    service = StubSandboxVerificationService()
    dispatcher = SandboxJobDispatcher(repository, service)

    processed = await dispatcher.run_once()

    assert processed == 1
    assert service.processed_job_ids == ["job-1"]
    assert repository.marked_statuses == [("job-1", AsyncJobStatus.SUCCEEDED, None)]
    assert repository.attempts == [("job-1", AsyncJobStatus.SUCCEEDED)]
    assert repository.reclaimed_calls == [(300, AsyncJobType.SANDBOX_RUN)]


async def test_autonomous_job_dispatcher_processes_async_jobs() -> None:
    repository = StubAsyncJobRepository()
    repository.job = repository.job.model_copy(
        update={
            "job_type": AsyncJobType.AUTONOMOUS_REPAIR,
            "dedupe_key": "autonomous:incident-1:run-1",
            "payload": {"incident_id": "incident-1", "autonomous_run_id": "run-1"},
        }
    )
    service = StubAutonomousRunService()
    dispatcher = AutonomousJobDispatcher(repository, service)

    processed = await dispatcher.run_once()

    assert processed == 1
    assert service.processed_job_ids == ["job-1"]
    assert repository.marked_statuses == [("job-1", AsyncJobStatus.SUCCEEDED, None)]
    assert repository.attempts == [("job-1", AsyncJobStatus.SUCCEEDED)]
    assert repository.reclaimed_calls == [(300, AsyncJobType.AUTONOMOUS_REPAIR)]


async def test_kubernetes_monitor_dispatcher_records_terminal_runs() -> None:
    running_run = type(
        "SandboxRun",
        (),
        {
            "id": "sandbox-1",
            "status": SandboxRunStatus.RUNNING,
        },
    )()
    finished_run = type(
        "SandboxRun",
        (),
        {
            "id": "sandbox-2",
            "status": SandboxRunStatus.SUCCEEDED,
        },
    )()
    service = StubKubernetesPollingService([running_run, finished_run])
    autonomous_service = StubAutonomousRunService()
    dispatcher = KubernetesMonitorDispatcher(service, autonomous_run_service=autonomous_service)

    processed = await dispatcher.run_once(limit=25)

    assert processed == 2
    assert service.polled_limits == [25]
    assert autonomous_service.recorded_sandbox_ids == ["sandbox-2"]
