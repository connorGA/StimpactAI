from __future__ import annotations

import argparse
import asyncio
import fcntl
import logging
import signal
import tempfile
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from openai import AsyncOpenAI

from api.core.config import (
    get_kubernetes_monitor_interval_seconds,
    get_openai_api_key,
    get_openai_patch_model,
    get_worker_idle_seconds,
    validate_runtime_configuration,
)
from api.core.errors import APIError
from api.db.postgres import PostgresConnectionManager
from api.events.redis_bus import build_outbox_signal_bus
from api.observability import configure_logging, get_metrics_registry
from api.repositories.artifact_repository import ArtifactRepository
from api.repositories.async_job_repository import AsyncJobRepository
from api.repositories.autonomous_repository import AutonomousRunRepository
from api.repositories.control_plane_repository import ControlPlaneRepository
from api.repositories.incident_repository import IncidentRepository
from api.repositories.outbox_repository import OutboxRepository
from api.repositories.patch_repository import PatchRepository
from api.repositories.sandbox_repository import SandboxRepository
from services.autonomous_runs import AutonomousRunService
from services.aws_secrets_manager import AwsSecretsManagerReader, AwsSecretsManagerWriter
from services.code_context import CodeContextService
from services.failure_classifier import FailureClassifier
from services.incident_creation import IncidentCreationService
from services.patch_generation import PatchGenerationService
from services.provider_integration_service import ProviderIntegrationService
from services.sandbox_verification import SandboxVerificationService
from workers.autonomous_job_dispatcher import AutonomousJobDispatcher
from workers.kubernetes_monitor_dispatcher import KubernetesMonitorDispatcher
from workers.outbox_dispatcher import OutboxDispatcher
from workers.sandbox_job_dispatcher import SandboxJobDispatcher

logger = logging.getLogger(__name__)


def _worker_lock_path(worker_name: str) -> Path:
    return Path(tempfile.gettempdir()) / f"stimpact-{worker_name}.lock"


@contextmanager
def _worker_lock(worker_name: str):
    lock_path = _worker_lock_path(worker_name)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit(
                f"Another '{worker_name}' worker is already running (lock: {lock_path}). "
                "Stop the existing worker before starting a new one."
            ) from exc
        lock_file.write(str(lock_path))
        lock_file.flush()
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


class _UnavailablePatchGenerationService:
    async def get_or_generate_patch(self, incident_id: str, *, refresh: bool = False, event_limit: int = 50):
        _ = (incident_id, refresh, event_limit)
        raise APIError(
            "OPENAI_API_KEY is required for patch generation.",
            status_code=503,
            code="openai_unconfigured",
        )


@asynccontextmanager
async def _postgres_manager():
    manager = PostgresConnectionManager()
    await manager.connect()
    try:
        yield manager
    finally:
        await manager.close()


def _build_patch_generation_service(
    *,
    incident_repository: IncidentRepository,
    patch_repository: PatchRepository,
) -> PatchGenerationService | _UnavailablePatchGenerationService:
    api_key = get_openai_api_key()
    if api_key is None:
        return _UnavailablePatchGenerationService()
    return PatchGenerationService(
        incident_repository,
        patch_repository,
        classifier=FailureClassifier(),
        code_context=CodeContextService(),
        client=AsyncOpenAI(api_key=api_key),
        model=get_openai_patch_model(),
    )


async def _run_loop(
    *,
    process_once: Callable[[], Awaitable[int]],
    idle_seconds: float,
    stop_event: asyncio.Event,
    worker_name: str,
) -> None:
    while not stop_event.is_set():
        started_at = asyncio.get_running_loop().time()
        try:
            processed = await process_once()
        except Exception:
            get_metrics_registry().increment(
                "stimpact_worker_errors_total",
                labels={"worker": worker_name},
            )
            logger.exception("Worker loop iteration failed.", extra={"worker": worker_name})
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=idle_seconds)
            except asyncio.TimeoutError:
                continue
            continue
        get_metrics_registry().increment(
            "stimpact_worker_iterations_total",
            value=max(1, processed),
            labels={"worker": worker_name},
        )
        get_metrics_registry().observe(
            "stimpact_worker_iteration_latency_seconds",
            asyncio.get_running_loop().time() - started_at,
            labels={"worker": worker_name},
        )
        if processed == 0:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=idle_seconds)
            except asyncio.TimeoutError:
                continue


async def _run_outbox_worker(stop_event: asyncio.Event) -> None:
    async with _postgres_manager() as manager:
        outbox_signal_bus = build_outbox_signal_bus()
        try:
            repository = OutboxRepository(manager.pool)
            incident_repository = IncidentRepository(manager.pool)
            control_plane_repository = ControlPlaneRepository(manager.pool)
            dispatcher = OutboxDispatcher(
                repository,
                IncidentCreationService(
                    incident_repository,
                    control_plane_repository=control_plane_repository,
                ),
                signal_bus=outbox_signal_bus,
            )

            async def _process() -> int:
                return await dispatcher.run_once_or_wait()

            await _run_loop(
                process_once=_process,
                idle_seconds=get_worker_idle_seconds(),
                stop_event=stop_event,
                worker_name="outbox",
            )
        finally:
            await outbox_signal_bus.close()


async def _build_autonomous_services(
) -> tuple[PostgresConnectionManager, AutonomousRunService, SandboxVerificationService, AsyncJobRepository]:
    manager = PostgresConnectionManager()
    await manager.connect()
    incident_repository = IncidentRepository(manager.pool)
    async_job_repository = AsyncJobRepository(manager.pool)
    control_plane_repository = ControlPlaneRepository(manager.pool)
    autonomous_repository = AutonomousRunRepository(manager.pool)
    patch_repository = PatchRepository(manager.pool)
    sandbox_repository = SandboxRepository(manager.pool)
    artifact_repository = ArtifactRepository(manager.pool)
    provider_integration_service = ProviderIntegrationService(
        control_plane_repository,
        secrets_writer=AwsSecretsManagerWriter(),
        secrets_reader=AwsSecretsManagerReader(),
    )
    patch_generation = _build_patch_generation_service(
        incident_repository=incident_repository,
        patch_repository=patch_repository,
    )
    sandbox_service = SandboxVerificationService(
        incident_repository,
        sandbox_repository,
        control_plane_repository=control_plane_repository,
        async_job_repository=async_job_repository,
        artifact_repository=artifact_repository,
        patch_repository=patch_repository,
        patch_generation=patch_generation,  # type: ignore[arg-type]
        provider_integration_service=provider_integration_service,
    )
    autonomous_service = AutonomousRunService(
        incident_repository,
        async_job_repository=async_job_repository,
        autonomous_repository=autonomous_repository,
        control_plane_repository=control_plane_repository,
        patch_repository=patch_repository,
        sandbox_verification_service=sandbox_service,
        provider_integration_service=provider_integration_service,
    )
    return manager, autonomous_service, sandbox_service, async_job_repository


async def _run_autonomous_worker(stop_event: asyncio.Event) -> None:
    manager, autonomous_service, sandbox_service, async_job_repository = await _build_autonomous_services()
    try:
        dispatcher = AutonomousJobDispatcher(async_job_repository, autonomous_service)
        await _run_loop(
            process_once=dispatcher.run_once,
            idle_seconds=get_worker_idle_seconds(),
            stop_event=stop_event,
            worker_name="autonomous",
        )
    finally:
        await manager.close()


async def _run_sandbox_worker(stop_event: asyncio.Event) -> None:
    manager, autonomous_service, sandbox_service, async_job_repository = await _build_autonomous_services()
    try:
        dispatcher = SandboxJobDispatcher(
            async_job_repository,
            sandbox_service,
            autonomous_run_service=autonomous_service,
        )
        await _run_loop(
            process_once=dispatcher.run_once,
            idle_seconds=get_worker_idle_seconds(),
            stop_event=stop_event,
            worker_name="sandbox",
        )
    finally:
        await manager.close()


async def _run_kubernetes_monitor_worker(stop_event: asyncio.Event) -> None:
    manager, autonomous_service, sandbox_service, _async_job_repository = await _build_autonomous_services()
    try:
        dispatcher = KubernetesMonitorDispatcher(
            sandbox_service,
            autonomous_run_service=autonomous_service,
        )
        await _run_loop(
            process_once=dispatcher.run_once,
            idle_seconds=get_kubernetes_monitor_interval_seconds(),
            stop_event=stop_event,
            worker_name="kubernetes-monitor",
        )
    finally:
        await manager.close()


def _build_stop_event() -> asyncio.Event:
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda _signum, _frame: stop_event.set())
    return stop_event


async def _main_async(worker_name: str) -> None:
    stop_event = _build_stop_event()
    if worker_name == "outbox":
        await _run_outbox_worker(stop_event)
        return
    if worker_name == "autonomous":
        await _run_autonomous_worker(stop_event)
        return
    if worker_name == "sandbox":
        await _run_sandbox_worker(stop_event)
        return
    if worker_name == "kubernetes-monitor":
        await _run_kubernetes_monitor_worker(stop_event)
        return
    raise SystemExit(f"Unsupported worker {worker_name}.")


def main() -> None:
    configure_logging()
    validate_runtime_configuration(runtime="worker")
    parser = argparse.ArgumentParser(description="Run a Stimpact worker loop.")
    parser.add_argument(
        "worker",
        choices=["outbox", "autonomous", "sandbox", "kubernetes-monitor"],
        help="Worker loop to run.",
    )
    args = parser.parse_args()
    with _worker_lock(args.worker):
        asyncio.run(_main_async(args.worker))


if __name__ == "__main__":
    main()
