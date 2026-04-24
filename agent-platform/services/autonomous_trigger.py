from __future__ import annotations

import logging

from api.schemas.autonomous import AutonomousRunCreateRequest
from harness.schemas.autonomous import AutonomousApprovalStatus, AutonomousExecutionMode, AutonomousRunStatus
from models.incident import IncidentProcessingResult

logger = logging.getLogger(__name__)


async def trigger_autonomous_run_for_new_incident(
    *,
    incident_id: str,
    autonomous_run_service,
    processing_result: IncidentProcessingResult | None = None,
) -> None:
    try:
        existing_runs = await autonomous_run_service.list_runs(incident_id)
        latest_run = existing_runs[0] if existing_runs else None
        should_skip = bool(
            latest_run is not None
            and (
                latest_run.status in {AutonomousRunStatus.QUEUED, AutonomousRunStatus.RUNNING}
                or latest_run.approval_status is AutonomousApprovalStatus.PENDING
            )
        )
        logger.info(
            "Autonomous trigger evaluated latest run",
            extra={
                "incident_id": incident_id,
                "created_new_incident": (
                    processing_result.created_new_incident if processing_result is not None else None
                ),
                "attached_telemetry": (
                    processing_result.attached_telemetry if processing_result is not None else None
                ),
                "latest_run_id": str(latest_run.id) if latest_run is not None else None,
                "latest_run_status": latest_run.status.value if latest_run is not None else None,
                "latest_approval_status": (
                    latest_run.approval_status.value if latest_run is not None else None
                ),
                "should_skip": should_skip,
            },
        )
        if should_skip:
            logger.info(
                "Skipping autonomous trigger because an active run already exists",
                extra={
                    "incident_id": incident_id,
                    "run_id": latest_run.id if latest_run is not None else None,
                    "run_status": latest_run.status.value if latest_run is not None else None,
                },
            )
            return
        require_human_approval = bool(
            processing_result and processing_result.requires_human_approval
        )
        request = AutonomousRunCreateRequest(
            execution_mode=AutonomousExecutionMode.REPAIR_AND_PROPOSE,
            require_human_approval=require_human_approval or None,
        )
        detail = await autonomous_run_service.start_run(incident_id, request)
        logger.info(
            "Autonomous repair run queued for new incident",
            extra={
                "incident_id": incident_id,
                "run_id": detail.run.id,
                "async_job_id": detail.run.async_job_id,
                "require_human_approval": require_human_approval,
                "classification": processing_result.classification if processing_result else None,
                "classifier_source": (
                    processing_result.classification_source if processing_result else None
                ),
            },
        )
    except Exception:
        logger.exception(
            "Failed to trigger autonomous run for new incident",
            extra={"incident_id": incident_id},
        )
