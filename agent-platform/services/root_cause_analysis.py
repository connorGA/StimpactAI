from __future__ import annotations

import json
import logging
from typing import Sequence

from openai import AsyncOpenAI

from api.core.errors import APIError

logger = logging.getLogger(__name__)
from api.repositories.incident_repository import IncidentRepository
from models.failure_classification import FailureClassification
from models.incident import IncidentEventRecord, IncidentRecord, TelemetryRecord
from models.root_cause import (
    RootCauseAnalysis,
    RootCauseEvidence,
    RootCauseReasoning,
)
from services.code_context import (
    CodeContextService,
    CodeSearchAdapter,
    GitHistoryAdapter,
    SnippetRetriever,
    StackTraceParser,
)
from services.failure_classifier import FailureClassifier


class RootCauseAnalysisService:
    def __init__(
        self,
        repository: IncidentRepository,
        *,
        classifier: FailureClassifier,
        analyzer: RootCauseAnalyzer,
        reasoner: RootCauseReasoner,
    ) -> None:
        self._repository = repository
        self._classifier = classifier
        self._analyzer = analyzer
        self._reasoner = reasoner

    async def analyze_incident(
        self,
        incident_id: str,
        *,
        event_limit: int = 50,
    ) -> RootCauseAnalysis:
        incident = await self._repository.get_incident(incident_id)
        if incident is None:
            raise APIError(
                f"Incident {incident_id} was not found.",
                status_code=404,
                code="incident_not_found",
            )

        events = await self._repository.list_incident_events(incident_id, limit=event_limit)
        latest_telemetry = await self._repository.get_telemetry(incident.latest_telemetry_id)
        classification = await self._classifier.classify_async(incident, events)
        evidence = self._analyzer.analyze(
            incident=incident,
            events=events,
            classification=classification,
            latest_telemetry=latest_telemetry,
        )
        reasoning = await self._reasoner.reason_about_incident(
            incident=incident,
            classification=classification,
            evidence=evidence,
        )

        return RootCauseAnalysis(
            incident_id=incident.id,
            category=classification.category,
            category_summary=classification.summary,
            category_confidence=classification.confidence,
            evidence=evidence,
            reasoning=reasoning,
        )


class RootCauseAnalyzer:
    def __init__(
        self,
        *,
        stack_parser: StackTraceParser | None = None,
        code_search: CodeSearchAdapter | None = None,
        snippet_retriever: SnippetRetriever | None = None,
        git_history: GitHistoryAdapter | None = None,
    ) -> None:
        self._code_context = CodeContextService(
            stack_parser=stack_parser,
            code_search=code_search,
            snippet_retriever=snippet_retriever,
            git_history=git_history,
        )

    def analyze(
        self,
        *,
        incident: IncidentRecord,
        events: Sequence[IncidentEventRecord],
        classification: FailureClassification,
        latest_telemetry: TelemetryRecord,
    ) -> RootCauseEvidence:
        return self._code_context.build_evidence(
            incident=incident,
            events=events,
            classification=classification,
            latest_telemetry=latest_telemetry,
        )


class RootCauseReasoner:
    def __init__(self, *, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def reason_about_incident(
        self,
        *,
        incident: IncidentRecord,
        classification: FailureClassification,
        evidence: RootCauseEvidence,
    ) -> RootCauseReasoning:
        prompt_payload = {
            "incident": {
                "id": incident.id,
                "title": incident.title,
                "service": incident.service,
                "environment": incident.environment.value,
                "severity": incident.severity.value,
                "status": incident.status.value,
                "event_count": incident.event_count,
            },
            "classification": classification.model_dump(mode="json"),
            "evidence": evidence.model_dump(mode="json"),
        }

        completion = await self._client.chat.completions.create(
            model=self._model,
            temperature=0.1,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a root cause analysis assistant for a self-healing software platform. "
                        "Use only the provided grounded evidence. "
                        "Do not invent files, commits, symbols, or runtime facts that are not present. "
                        "Return raw JSON with keys: root_cause_hypothesis, reasoning_summary, "
                        "alternative_hypotheses, confidence."
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
            raise APIError("OpenAI returned an empty root cause analysis.", code="empty_root_cause_response")

        try:
            extracted = _extract_json_object(content)
            return RootCauseReasoning.model_validate_json(extracted)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to parse RCA response: %s\nRaw content: %s",
                exc,
                content[:2000],
            )
            raise APIError(
                "OpenAI returned an invalid root cause analysis response.",
                code="invalid_root_cause_response",
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
