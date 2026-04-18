from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from api.core.errors import APIError
from api.schemas.autonomous import AutonomousRunDetailResponse
from harness.schemas.autonomous import (
    AutonomousSolutionReview,
    AutonomousSolutionReviewRisk,
    AutonomousSolutionReviewRiskSeverity,
    AutonomousSolutionReviewVerdict,
)
from models.patch import PatchRunRecord
from models.sandbox import SandboxRunRecord

logger = logging.getLogger(__name__)


class SolutionReviewService:
    def __init__(self, *, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    async def review_solution(
        self,
        *,
        detail: AutonomousRunDetailResponse,
        patch_run: PatchRunRecord | None,
        sandbox_run: SandboxRunRecord,
    ) -> AutonomousSolutionReview:
        prompt_payload = {
            "run": {
                "id": detail.run.id,
                "objective": detail.run.objective,
                "service_name": detail.run.service_name,
                "incident_title": detail.run.incident_title,
                "incident_fingerprint": detail.run.incident_fingerprint,
                "latest_telemetry_error_message": detail.run.latest_telemetry_error_message,
                "execution_mode": detail.run.execution_mode.value,
                "attempt_count": detail.run.loop_state.repair_attempt_count,
            },
            "sandbox": {
                "status": sandbox_run.status.value,
                "summary": sandbox_run.summary,
                "reproduction_succeeded": sandbox_run.reproduction_succeeded,
                "patch_applied": sandbox_run.patch_applied,
                "verification_succeeded": sandbox_run.verification_succeeded,
                "verify_command": sandbox_run.verify_command,
                "execution_log_excerpt": _truncate_text(sandbox_run.execution_log, 6_000),
            },
            "patch": (
                {
                    "patch_summary": patch_run.patch_summary,
                    "rationale": patch_run.rationale,
                    "target_files": [_target_file_payload(item) for item in patch_run.target_files],
                    "diff_line_count": patch_run.diff_line_count,
                    "file_count": patch_run.file_count,
                    "unified_diff_excerpt": _truncate_text(patch_run.unified_diff, 10_000),
                    "verification_steps": patch_run.verification_steps,
                }
                if patch_run is not None
                else None
            ),
        }

        completion = await self._client.chat.completions.create(
            model=self._model,
            temperature=0.1,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a cautious solution reviewer for an autonomous repair system. "
                        "Your job is to assess whether the proposed patch appears clean, safe, and aligned with the incident. "
                        "Use only the grounded evidence provided. "
                        "Prefer NEEDS_CHANGES when the fix seems plausible but there is meaningful regression risk, excessive blast radius, "
                        "or missing confidence about side effects. Prefer UNCERTAIN if the evidence is insufficient. "
                        "Return raw JSON with keys: verdict, summary, risks, requested_checks, feedback_for_repair. "
                        "Each risk must include area, severity, reasoning. "
                        "Severity must be one of low, medium, high. "
                        "Verdict must be one of approve, needs_changes, uncertain. "
                        "feedback_for_repair should be short, concrete bullet-style sentences the repair agent can act on next."
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
            raise APIError("OpenAI returned an empty solution review.", code="empty_solution_review")

        try:
            payload = json.loads(_extract_json_object(content))
            return AutonomousSolutionReview(
                verdict=AutonomousSolutionReviewVerdict(str(payload["verdict"]).strip().lower()),
                summary=str(payload["summary"]).strip(),
                risks=[
                    AutonomousSolutionReviewRisk(
                        area=str(item["area"]).strip(),
                        severity=AutonomousSolutionReviewRiskSeverity(str(item["severity"]).strip().lower()),
                        reasoning=str(item["reasoning"]).strip(),
                    )
                    for item in payload.get("risks", [])
                    if isinstance(item, dict)
                ],
                requested_checks=[
                    str(item).strip()
                    for item in payload.get("requested_checks", [])
                    if str(item).strip()
                ][:12],
                feedback_for_repair=[
                    str(item).strip()
                    for item in payload.get("feedback_for_repair", [])
                    if str(item).strip()
                ][:12],
                reviewed_at=detail.run.updated_at,
                model_name=self._model,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to parse solution review: %s\nRaw content: %s", exc, content[:2000])
            raise APIError(
                "OpenAI returned an invalid solution review response.",
                code="invalid_solution_review",
            ) from exc


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


def _target_file_payload(item: object) -> dict[str, object]:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    return {
        "path": getattr(item, "path", ""),
        "reason": getattr(item, "reason", ""),
    }
