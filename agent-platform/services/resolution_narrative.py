from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from api.core.errors import APIError
from api.repositories.incident_repository import IncidentRepository
from api.repositories.patch_repository import PatchRepository
from api.schemas.autonomous import AutonomousRunDetailResponse
from models.root_cause import RootCauseAnalysis
from services.root_cause_analysis import RootCauseAnalysisService

logger = logging.getLogger(__name__)


class ResolutionNarrativeService:
    def __init__(
        self,
        incident_repository: IncidentRepository,
        *,
        patch_repository: PatchRepository | None,
        root_cause_service: RootCauseAnalysisService,
        client: AsyncOpenAI,
        model: str,
    ) -> None:
        self._incident_repository = incident_repository
        self._patch_repository = patch_repository
        self._root_cause_service = root_cause_service
        self._client = client
        self._model = model

    async def build(
        self,
        *,
        incident_id: str,
        detail: AutonomousRunDetailResponse,
    ) -> tuple[str, str]:
        incident = await self._incident_repository.get_incident(incident_id)
        if incident is None:
            raise APIError(
                f"Incident {incident_id} was not found.",
                status_code=404,
                code="incident_not_found",
            )

        patch_run = None
        if detail.run.patch_run_id is not None and self._patch_repository is not None:
            patch_run = await self._patch_repository.get_patch_run(detail.run.patch_run_id)

        root_cause = await self._root_cause_service.analyze_incident(incident_id, event_limit=50)
        prompt_payload = {
            "incident": {
                "id": incident.id,
                "title": incident.title,
                "service": incident.service,
                "environment": incident.environment.value,
                "severity": incident.severity.value,
                "status": incident.status.value,
            },
            "run": {
                "id": detail.run.id,
                "status": detail.run.status.value,
                "phase": detail.run.phase.value,
                "objective": detail.run.objective,
                "promotion_url": detail.run.promotion_url,
                "promotion_branch_name": detail.run.promotion_branch_name,
                "latest_verification": (
                    detail.run.latest_verification.model_dump(mode="json")
                    if detail.run.latest_verification is not None
                    else None
                ),
            },
            "outcome": detail.outcome.model_dump(mode="json") if detail.outcome is not None else None,
            "patch": (
                {
                    "patch_summary": patch_run.patch_summary,
                    "rationale": patch_run.rationale,
                    "target_files": [item.model_dump(mode="json") for item in patch_run.target_files],
                    "verification_steps": patch_run.verification_steps,
                    "unified_diff_excerpt": _truncate_text(patch_run.unified_diff, 8_000),
                }
                if patch_run is not None
                else None
            ),
            "root_cause": root_cause.model_dump(mode="json"),
            "recent_events": [
                {
                    "event_type": event.event_type.value,
                    "phase": event.phase.value,
                    "summary": event.summary,
                    "decision": event.decision.model_dump(mode="json") if event.decision is not None else None,
                }
                for event in detail.events[-12:]
            ],
        }

        completion = await self._client.chat.completions.create(
            model=self._model,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You summarize successful autonomous incident repairs for end users. "
                        "Use only the provided grounded evidence. "
                        "Return raw JSON with keys: root_cause_explanation, solution_description. "
                        "Each value should be a concise natural-language paragraph, clear to a product user, "
                        "while still naming the relevant technical cause and the fix strategy."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt_payload, indent=2, sort_keys=True),
                },
            ],
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content
        if not content:
            raise APIError("OpenAI returned an empty resolution narrative.", code="empty_resolution_narrative")

        try:
            payload = json.loads(_extract_json_object(content))
            root_cause_explanation = str(payload["root_cause_explanation"]).strip()
            solution_description = str(payload["solution_description"]).strip()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to parse resolution narrative: %s\nRaw content: %s", exc, content[:2000])
            raise APIError(
                "OpenAI returned an invalid resolution narrative response.",
                code="invalid_resolution_narrative",
            ) from exc

        if not root_cause_explanation or not solution_description:
            raise APIError(
                "OpenAI returned an incomplete resolution narrative response.",
                code="incomplete_resolution_narrative",
            )

        return root_cause_explanation, solution_description


def _extract_json_object(content: str) -> str:
    normalized = content.strip()
    if normalized.startswith("{") and normalized.endswith("}"):
        return normalized
    start = normalized.find("{")
    end = normalized.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response.")
    return normalized[start : end + 1]


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}\n... [truncated]"
