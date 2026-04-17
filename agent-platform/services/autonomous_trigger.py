from __future__ import annotations

import logging

from api.schemas.autonomous import AutonomousRunCreateRequest
from harness.schemas.autonomous import AutonomousExecutionMode
from models.incident import IncidentProcessingResult

logger = logging.getLogger(__name__)


async def trigger_autonomous_run_for_new_incident(
    *,
    incident_id: str,
    autonomous_run_service,
    processing_result: IncidentProcessingResult | None = None,
) -> None:
    try:
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
