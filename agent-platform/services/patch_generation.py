from __future__ import annotations

import json
import re

from openai import AsyncOpenAI

from api.core.errors import APIError
from api.repositories.incident_repository import IncidentRepository
from api.repositories.patch_repository import PatchRepository
from models.failure_classification import FailureClassification
from models.incident import IncidentRecord
from models.patch import PatchProposal, PatchRunRecord, PatchTargetFile
from models.root_cause import RootCauseEvidence
from services.code_context import CodeContextService
from services.failure_classifier import FailureClassifier

_MAX_PATCH_FILES = 3
_MAX_PATCH_LINES = 200


class PatchGenerationService:
    def __init__(
        self,
        incident_repository: IncidentRepository,
        patch_repository: PatchRepository,
        *,
        classifier: FailureClassifier,
        code_context: CodeContextService,
        client: AsyncOpenAI,
        model: str,
    ) -> None:
        self._incident_repository = incident_repository
        self._patch_repository = patch_repository
        self._classifier = classifier
        self._code_context = code_context
        self._client = client
        self._model = model

    async def get_or_generate_patch(
        self,
        incident_id: str,
        *,
        refresh: bool = False,
        event_limit: int = 50,
    ) -> PatchRunRecord:
        incident = await self._incident_repository.get_incident(incident_id)
        if incident is None:
            raise APIError(
                f"Incident {incident_id} was not found.",
                status_code=404,
                code="incident_not_found",
            )

        if not refresh:
            existing = await self._patch_repository.get_latest_patch_run(incident_id)
            if existing is not None:
                return existing

        events = await self._incident_repository.list_incident_events(incident_id, limit=event_limit)
        latest_telemetry = await self._incident_repository.get_telemetry(incident.latest_telemetry_id)
        classification = self._classifier.classify(incident, events)
        evidence = self._code_context.build_evidence(
            incident=incident,
            events=events,
            classification=classification,
            latest_telemetry=latest_telemetry,
        )

        proposal = await self._generate_patch_proposal(
            incident=incident,
            classification=classification,
            evidence=evidence,
        )
        diff_summary = summarize_unified_diff(proposal.unified_diff)
        file_count = max(len(proposal.target_files), diff_summary.file_count)

        if file_count == 0:
            raise APIError(
                "Patch generation returned no target files.",
                code="invalid_patch_response",
            )
        if file_count > _MAX_PATCH_FILES:
            raise APIError(
                f"Patch generation exceeded the {_MAX_PATCH_FILES}-file limit.",
                code="patch_constraints_violated",
            )
        if diff_summary.changed_line_count > _MAX_PATCH_LINES:
            raise APIError(
                f"Patch generation exceeded the {_MAX_PATCH_LINES}-line diff limit.",
                code="patch_constraints_violated",
            )

        return await self._patch_repository.create_patch_run(
            incident_id=incident.id,
            proposal=proposal,
            model_name=self._model,
            based_on_commit_sha=evidence.latest_commit_sha,
            diff_line_count=diff_summary.changed_line_count,
            file_count=file_count,
        )

    async def _generate_patch_proposal(
        self,
        *,
        incident: IncidentRecord,
        classification: FailureClassification,
        evidence: RootCauseEvidence,
    ) -> PatchProposal:
        prompt_payload = {
            "incident": {
                "id": incident.id,
                "title": incident.title,
                "service": incident.service,
                "environment": incident.environment.value,
                "severity": incident.severity.value,
            },
            "classification": classification.model_dump(mode="json"),
            "evidence": evidence.model_dump(mode="json"),
            "constraints": {
                "max_files": _MAX_PATCH_FILES,
                "max_changed_lines": _MAX_PATCH_LINES,
                "patch_format": "unified_diff",
            },
        }

        completion = await self._client.chat.completions.create(
            model=self._model,
            temperature=0.1,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a patch generation assistant for a self-healing software platform. "
                        "Use only the grounded incident, classification, and code-context evidence provided. "
                        "Generate a minimal, targeted patch proposal. "
                        "Return raw JSON with keys: patch_summary, rationale, target_files, unified_diff, "
                        "verification_steps, confidence. "
                        "Each target_files item must contain path and reason. "
                        "The unified_diff must be a valid unified diff touching no more than 3 files and "
                        "changing no more than 200 added or removed lines."
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
            raise APIError("OpenAI returned an empty patch generation response.", code="empty_patch_response")

        try:
            raw_payload = json.loads(_extract_json_object(content))
            proposal = PatchProposal.model_validate(
                {
                    **raw_payload,
                    "target_files": [
                        PatchTargetFile.model_validate(item)
                        for item in raw_payload.get("target_files", [])
                    ],
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise APIError(
                "OpenAI returned an invalid patch generation response.",
                code="invalid_patch_response",
            ) from exc

        if not proposal.unified_diff.strip():
            raise APIError("Patch generation returned an empty diff.", code="invalid_patch_response")
        return proposal


class DiffSummary:
    def __init__(self, *, file_count: int, changed_line_count: int) -> None:
        self.file_count = file_count
        self.changed_line_count = changed_line_count


def summarize_unified_diff(unified_diff: str) -> DiffSummary:
    file_paths: set[str] = set()
    changed_line_count = 0

    for line in unified_diff.splitlines():
        if line.startswith("+++ b/"):
            file_paths.add(line.removeprefix("+++ b/").strip())
            continue
        if line.startswith("diff --git "):
            match = re.match(r"diff --git a/(.+?) b/(.+)", line)
            if match:
                file_paths.add(match.group(2).strip())
            continue
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("+") or line.startswith("-"):
            changed_line_count += 1

    return DiffSummary(
        file_count=len(file_paths),
        changed_line_count=changed_line_count,
    )


def _extract_json_object(content: str) -> str:
    normalized = content.strip()
    if normalized.startswith("{") and normalized.endswith("}"):
        return normalized

    start = normalized.find("{")
    end = normalized.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response.")
    return normalized[start : end + 1]
