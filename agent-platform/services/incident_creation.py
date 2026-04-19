from __future__ import annotations

import logging
from typing import Any

from api.repositories.control_plane_repository import ControlPlaneRepository
from api.repositories.incident_repository import IncidentRepository
from api.repositories.telemetry_repository import PostgresTelemetryRepository
from models.incident import IncidentProcessingResult, IncidentSeverity, TelemetryRecord
from models.normalized_telemetry import NormalizedTelemetry
from services.telemetry_classifier import (
    Classification,
    ClassificationResult,
    TelemetryClassifier,
)
from shared.events.incident_events import IncidentEvent
from shared.types.telemetry import (
    Environment,
    HttpRequestContext,
    HttpResponseContext,
    TelemetryBreadcrumb,
    TelemetryUserContext,
)

logger = logging.getLogger(__name__)


class IncidentCreationService:
    def __init__(
        self,
        repository: IncidentRepository,
        control_plane_repository: ControlPlaneRepository | None = None,
        *,
        classifier: TelemetryClassifier | None = None,
        telemetry_repository: PostgresTelemetryRepository | None = None,
    ) -> None:
        self._repository = repository
        self._control_plane_repository = control_plane_repository
        self._classifier = classifier
        self._telemetry_repository = telemetry_repository

    async def process_telemetry_received(self, payload: dict[str, Any]) -> IncidentProcessingResult:
        event = IncidentEvent.model_validate(payload)
        telemetry = await self._repository.get_telemetry(event.telemetry_id)

        verdict = await self._run_classifier(telemetry)
        if verdict is not None:
            await self._persist_classification(telemetry.id, verdict)

        if verdict is not None and verdict.classification == Classification.USER_ERROR:
            logger.info(
                "telemetry_suppressed_as_user_error",
                extra={
                    "telemetry_id": telemetry.id,
                    "project_id": telemetry.project_id,
                    "fingerprint": telemetry.fingerprint,
                    "classifier_source": verdict.source,
                    "classifier_reason": verdict.reason,
                },
            )
            return IncidentProcessingResult(
                incident_id=None,
                created_new_incident=False,
                attached_telemetry=False,
                severity=determine_incident_severity(telemetry),
                event_count=0,
                suppressed=True,
                classification=verdict.classification.value,
                classification_reason=verdict.reason,
                classification_source=verdict.source,
            )

        severity = determine_incident_severity(telemetry)
        title = build_incident_title(telemetry)
        project_service_id = None
        repo_profile_id = None
        if self._control_plane_repository is not None:
            resolved_service = await self._control_plane_repository.resolve_project_service(
                project_id=telemetry.project_id,
                service_name=telemetry.service,
                stacktrace=telemetry.stacktrace,
            )
            if resolved_service is not None:
                project_service_id = resolved_service.id
                repo_profile_id = resolved_service.repo_profile_id

        result = await self._repository.attach_to_incident(
            telemetry=telemetry,
            event_type=event.event_type.value,
            event_payload=event.model_dump(mode="json"),
            severity=severity,
            title=title,
            project_service_id=project_service_id,
            repo_profile_id=repo_profile_id,
        )

        if verdict is not None:
            result = result.model_copy(
                update={
                    "classification": verdict.classification.value,
                    "classification_reason": verdict.reason,
                    "classification_source": verdict.source,
                    "requires_human_approval": (
                        verdict.classification == Classification.CODE_AMBIGUOUS
                    ),
                }
            )
        return result

    async def _run_classifier(
        self, telemetry: TelemetryRecord
    ) -> ClassificationResult | None:
        if self._classifier is None:
            return None
        normalized = _telemetry_record_to_normalized(telemetry)
        try:
            verdict = await self._classifier.classify(normalized)
        except Exception:
            logger.exception(
                "telemetry_classifier_failed_open",
                extra={
                    "telemetry_id": telemetry.id,
                    "project_id": telemetry.project_id,
                    "fingerprint": telemetry.fingerprint,
                },
            )
            return None
        logger.info(
            "telemetry_classification",
            extra={
                "telemetry_id": telemetry.id,
                "project_id": telemetry.project_id,
                "fingerprint": telemetry.fingerprint,
                "classification": verdict.classification.value,
                "source": verdict.source,
                "classifier_source": verdict.source,
                "classifier_confidence": verdict.confidence,
                "suppressed": verdict.classification == Classification.USER_ERROR,
                "requires_human_approval": (
                    verdict.classification == Classification.CODE_AMBIGUOUS
                ),
            },
        )
        return verdict

    async def _persist_classification(
        self, telemetry_id: str, verdict: ClassificationResult
    ) -> None:
        if self._telemetry_repository is None:
            return
        try:
            await self._telemetry_repository.update_classification(
                telemetry_id,
                classification=verdict.classification.value,
                reason=verdict.reason,
                source=verdict.source,
            )
        except Exception:
            logger.exception(
                "telemetry_classification_persist_failed",
                extra={"telemetry_id": telemetry_id},
            )


def _telemetry_record_to_normalized(telemetry: TelemetryRecord) -> NormalizedTelemetry:
    request_payload = telemetry.request_payload
    response_payload = telemetry.response_payload
    request_context: HttpRequestContext | None = None
    response_context: HttpResponseContext | None = None
    user_context: TelemetryUserContext | None = None
    breadcrumb_items: list[TelemetryBreadcrumb] = []
    if isinstance(request_payload, dict):
        try:
            request_context = HttpRequestContext.model_validate(request_payload)
        except Exception:
            request_context = None
    if isinstance(response_payload, dict):
        try:
            response_context = HttpResponseContext.model_validate(response_payload)
        except Exception:
            response_context = None
    if isinstance(telemetry.user_payload, dict):
        try:
            user_context = TelemetryUserContext.model_validate(telemetry.user_payload)
        except Exception:
            user_context = None
    if isinstance(telemetry.breadcrumbs_payload, list):
        for item in telemetry.breadcrumbs_payload:
            if not isinstance(item, dict):
                continue
            try:
                breadcrumb_items.append(TelemetryBreadcrumb.model_validate(item))
            except Exception:
                continue
    return NormalizedTelemetry(
        id=telemetry.id,
        project_id=telemetry.project_id,
        environment=telemetry.environment,
        service=telemetry.service,
        error_message=telemetry.error_message,
        stacktrace=telemetry.stacktrace,
        fingerprint=telemetry.fingerprint,
        request=request_context,
        response=response_context,
        commit_sha=telemetry.commit_sha,
        release=telemetry.release,
        dist=telemetry.dist,
        session_id=telemetry.session_id,
        user=user_context,
        tags=telemetry.tags_payload if isinstance(telemetry.tags_payload, dict) else {},
        contexts=telemetry.contexts_payload if isinstance(telemetry.contexts_payload, dict) else {},
        breadcrumbs=breadcrumb_items,
        handled=telemetry.handled,
        occurred_at=telemetry.occurred_at,
        received_at=telemetry.received_at,
    )


def determine_incident_severity(telemetry: TelemetryRecord) -> IncidentSeverity:
    status_code = _extract_response_status_code(telemetry.response_payload)
    request_method = _extract_request_method(telemetry.request_payload)

    if telemetry.environment == Environment.PRODUCTION:
        if status_code is not None and status_code >= 500:
            return IncidentSeverity.CRITICAL
        if request_method in {"POST", "PUT", "PATCH", "DELETE"}:
            return IncidentSeverity.HIGH
        if status_code is not None and status_code >= 400:
            return IncidentSeverity.HIGH
        return IncidentSeverity.MEDIUM

    if telemetry.environment == Environment.STAGING:
        if status_code is not None and status_code >= 500:
            return IncidentSeverity.HIGH
        if status_code is not None and status_code >= 400:
            return IncidentSeverity.MEDIUM
        return IncidentSeverity.LOW

    return IncidentSeverity.LOW


def build_incident_title(telemetry: TelemetryRecord) -> str:
    normalized_message = " ".join(telemetry.error_message.split())
    suffix = normalized_message[:117] + "..." if len(normalized_message) > 120 else normalized_message
    return f"{telemetry.service}: {suffix}"


def _extract_response_status_code(payload: dict[str, Any] | list[Any] | str | None) -> int | None:
    if not isinstance(payload, dict):
        return None

    value = payload.get("status_code")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _extract_request_method(payload: dict[str, Any] | list[Any] | str | None) -> str | None:
    if not isinstance(payload, dict):
        return None

    value = payload.get("method")
    if isinstance(value, str) and value.strip():
        return value.strip().upper()
    return None
