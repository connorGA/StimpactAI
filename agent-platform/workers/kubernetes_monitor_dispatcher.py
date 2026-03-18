from __future__ import annotations

from models.sandbox import SandboxRunStatus
from services.autonomous_runs import AutonomousRunService
from services.sandbox_verification import SandboxVerificationService


class KubernetesMonitorDispatcher:
    def __init__(
        self,
        service: SandboxVerificationService,
        *,
        autonomous_run_service: AutonomousRunService | None = None,
    ) -> None:
        self._service = service
        self._autonomous_run_service = autonomous_run_service

    async def run_once(self, *, limit: int = 50) -> int:
        runs = await self._service.poll_kubernetes_runs(limit=limit)
        if self._autonomous_run_service is not None:
            for run in runs:
                if run.status is SandboxRunStatus.RUNNING:
                    continue
                await self._autonomous_run_service.record_sandbox_result(run)
        return len(runs)
