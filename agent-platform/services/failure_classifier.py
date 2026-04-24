from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, field_validator

from models.failure_classification import FailureCategory, FailureClassification
from models.incident import IncidentEventRecord, IncidentRecord

logger = logging.getLogger(__name__)

_MAX_PROMPT_TOTAL_CHARS = 24_000

_FAILURE_CATEGORY_LLM = tuple(
    c for c in FailureCategory if c is not FailureCategory.UNKNOWN
)


class LlmFailureClassificationPayload(BaseModel):
    """Expected JSON from the LLM; unknown is rejected and remapped in code."""

    model_config = {"extra": "forbid"}

    category: str
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    matched_signals: list[str] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def _summary_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("summary must be non-empty")
        return v.strip()


def _category_from_llm_value(raw: str) -> FailureCategory | None:
    if not raw:
        return None
    key = raw.strip().lower()
    for member in _FAILURE_CATEGORY_LLM:
        if key == member.value or key == member.name.lower():
            return member
    return None


def _extract_json_object(content: str) -> str:
    normalized = content.strip()
    if normalized.startswith("{") and normalized.endswith("}"):
        return normalized
    start = normalized.find("{")
    end = normalized.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response.")
    return normalized[start : end + 1]


def _llm_system_prompt() -> str:
    allowed = ", ".join(c.value for c in _FAILURE_CATEGORY_LLM)
    return (
        "You label incidents for a self-healing platform. You MUST respond with raw JSON only "
        f"(no markdown) using keys: category, confidence, summary, matched_signals. "
        f"category must be one of: {allowed}. Do NOT use 'unknown'. "
        "Pick the best-matching single category from the evidence. "
        "confidence is 0.0-1.0. summary is 1-3 clear sentences. "
        "matched_signals is a short list of short phrases from the evidence you relied on. "
        "If evidence is weak, still pick the most plausible non-unknown category and lower confidence."
    )


def _build_evidence_payload(incident: IncidentRecord, events: Sequence[IncidentEventRecord]) -> dict[str, object]:
    event_payloads: list[dict[str, object]] = []
    for event in events:
        event_payloads.append(
            {
                "error_message": _truncate(_strip_for_prompt(event.error_message), 4_000),
                "stacktrace": _truncate(_strip_for_prompt(event.stacktrace), 4_000),
                "request_payload": _truncate(_strip_for_prompt(event.request_payload), 2_000),
                "response_payload": _truncate(_strip_for_prompt(event.response_payload), 2_000),
            }
        )
    return {
        "incident": {
            "title": _truncate(incident.title, 1_000),
            "service": incident.service,
            "environment": incident.environment.value
            if hasattr(incident.environment, "value")
            else str(incident.environment),
        },
        "event_count": len(events),
        "events": event_payloads,
    }


def _strip_for_prompt(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _truncate(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return f"{s[: max_chars - 20]}\n... [truncated]"


def _shrink_user_json_if_needed(payload: dict[str, object]) -> dict[str, object]:
    text = json.dumps(payload, ensure_ascii=True)
    if len(text) <= _MAX_PROMPT_TOTAL_CHARS:
        return payload
    # Drop stack traces first, then trim error messages
    ev = list(payload.get("events") or [])
    if not isinstance(ev, list):
        return {"note": "payload too large; omitted", "incident": payload.get("incident")}
    slim_events: list[dict[str, object]] = []
    for e in ev:
        if not isinstance(e, dict):
            continue
        slim_events.append(
            {
                "error_message": _truncate(str(e.get("error_message", "")), 1_200),
                "stacktrace": "[omitted: prompt size limit]",
                "request_payload": str(e.get("request_payload", ""))[:500],
                "response_payload": str(e.get("response_payload", ""))[:500],
            }
        )
    return {
        "incident": payload.get("incident"),
        "event_count": payload.get("event_count"),
        "events": slim_events,
        "note": "event bodies truncated to satisfy prompt size cap",
    }


class FailureClassifier:
    def __init__(
        self,
        *,
        openai_client: AsyncOpenAI | None = None,
        model: str | None = None,
    ) -> None:
        self._openai = openai_client
        self._model = model

    def classify(
        self,
        incident: IncidentRecord,
        events: Sequence[IncidentEventRecord],
    ) -> FailureClassification:
        """Deterministic rules only; if nothing matches, returns application_bug (never unknown)."""
        result = self._classify_from_rules(incident, events)
        if result is not None:
            return result
        return self._fallback_non_unknown(incident, events, source="heuristic")

    async def classify_async(
        self,
        incident: IncidentRecord,
        events: Sequence[IncidentEventRecord],
    ) -> FailureClassification:
        result = self._classify_from_rules(incident, events)
        if result is not None:
            return result
        if self._openai is None or not self._model:
            return self._fallback_non_unknown(incident, events, source="heuristic")
        return await self._classify_with_llm(incident, events)

    def _classify_from_rules(
        self,
        incident: IncidentRecord,
        events: Sequence[IncidentEventRecord],
    ) -> FailureClassification | None:
        search_text = " \n".join(
            filter(
                None,
                [
                    incident.title,
                    incident.service,
                    *[event.error_message for event in events],
                    *[event.stacktrace for event in events],
                    *[self._stringify_payload(event.request_payload) for event in events],
                    *[self._stringify_payload(event.response_payload) for event in events],
                ],
            )
        ).lower()
        status_codes = self._extract_status_codes(events)

        for category, confidence, signals in (
            self._match_configuration(search_text),
            self._match_authorization(search_text, status_codes),
            self._match_resource_exhaustion(search_text, status_codes),
            self._match_database(search_text),
            self._match_dependency(search_text, status_codes),
            self._match_network(search_text),
            self._match_timeout(search_text),
            self._match_null_reference(search_text),
            self._match_validation(search_text, status_codes),
            self._match_application_bug(search_text),
        ):
            if category is not None:
                return FailureClassification(
                    category=category,
                    confidence=confidence,
                    summary=self._build_summary(category, incident.service, signals),
                    matched_signals=signals,
                    inspected_event_count=len(events),
                )
        return None

    def _fallback_non_unknown(
        self,
        incident: IncidentRecord,
        events: Sequence[IncidentEventRecord],
        *,
        source: str,
    ) -> FailureClassification:
        return FailureClassification(
            category=FailureCategory.APPLICATION_BUG,
            confidence=0.5,
            summary=(
                f"The {incident.service} incident did not match built-in heuristics; "
                f"it is treated as a likely application or integration defect ({source})."
            ),
            matched_signals=[],
            inspected_event_count=len(events),
        )

    async def _classify_with_llm(
        self,
        incident: IncidentRecord,
        events: Sequence[IncidentEventRecord],
    ) -> FailureClassification:
        assert self._openai is not None and self._model
        payload = _shrink_user_json_if_needed(_build_evidence_payload(incident, events))
        user_content = json.dumps(payload, indent=2, sort_keys=True)
        try:
            completion = await self._openai.chat.completions.create(
                model=self._model,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": _llm_system_prompt()},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
            )
        except Exception:
            logger.exception(
                "failure_classifier_llm_failed",
                extra={"incident_id": incident.id, "service": incident.service},
            )
            return self._fallback_non_unknown(incident, events, source="llm_unavailable")

        content = completion.choices[0].message.content if completion.choices else None
        if not content:
            return self._fallback_non_unknown(incident, events, source="llm_empty")

        try:
            obj = json.loads(_extract_json_object(content))
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("failure_classifier_llm_json_parse", extra={"error": str(exc)})
            return self._fallback_non_unknown(incident, events, source="llm_invalid_json")

        try:
            parsed = LlmFailureClassificationPayload.model_validate(obj)
        except Exception as exc:
            logger.warning("failure_classifier_llm_schema", extra={"error": str(exc)})
            return self._fallback_non_unknown(incident, events, source="llm_invalid_shape")

        category = _category_from_llm_value(parsed.category)
        if category is None or category is FailureCategory.UNKNOWN:
            return self._fallback_non_unknown(incident, events, source="llm_rejected_category")

        signals = [s for s in parsed.matched_signals if isinstance(s, str) and s.strip()][:8]
        return FailureClassification(
            category=category,
            confidence=parsed.confidence,
            summary=self._coerce_summary(parsed.summary, category, incident.service, signals),
            matched_signals=signals,
            inspected_event_count=len(events),
        )

    def _coerce_summary(
        self,
        summary: str,
        category: FailureCategory,
        service: str,
        signals: Sequence[str],
    ) -> str:
        s = re.sub(r"\s+", " ", summary.strip())
        if len(s) < 20:
            return self._build_summary(category, service, signals or [s])
        return s

    def _match_configuration(
        self,
        search_text: str,
    ) -> tuple[FailureCategory | None, float, list[str]]:
        signals = _matched_keywords(
            search_text,
            [
                "not configured",
                "missing env",
                "missing environment variable",
                "invalid configuration",
                "configuration error",
                "api key",
            ],
        )
        return _classification_match(FailureCategory.CONFIGURATION_ERROR, 0.93, signals)

    def _match_authorization(
        self,
        search_text: str,
        status_codes: Sequence[int],
    ) -> tuple[FailureCategory | None, float, list[str]]:
        signals = _matched_keywords(
            search_text,
            ["unauthorized", "forbidden", "permission denied", "access denied", "invalid token"],
        )
        if any(code in {401, 403} for code in status_codes):
            signals.append(f"http {next(code for code in status_codes if code in {401, 403})}")
        return _classification_match(FailureCategory.AUTHORIZATION_FAILURE, 0.96, signals)

    def _match_resource_exhaustion(
        self,
        search_text: str,
        status_codes: Sequence[int],
    ) -> tuple[FailureCategory | None, float, list[str]]:
        signals = _matched_keywords(
            search_text,
            [
                "out of memory",
                "oom",
                "memory limit",
                "rate limit",
                "too many requests",
                "too many open files",
                "disk full",
            ],
        )
        if 429 in status_codes:
            signals.append("http 429")
        return _classification_match(FailureCategory.RESOURCE_EXHAUSTION, 0.91, signals)

    def _match_database(self, search_text: str) -> tuple[FailureCategory | None, float, list[str]]:
        signals = _matched_keywords(
            search_text,
            [
                "database",
                "postgres",
                "postgresql",
                "mysql",
                "sqlite",
                "sqlstate",
                "relation",
                "deadlock",
                "query failed",
                "connection pool",
            ],
        )
        return _classification_match(FailureCategory.DATABASE_FAILURE, 0.89, signals)

    def _match_dependency(
        self,
        search_text: str,
        status_codes: Sequence[int],
    ) -> tuple[FailureCategory | None, float, list[str]]:
        signals = _matched_keywords(
            search_text,
            [
                "upstream",
                "third-party",
                "external api",
                "provider",
                "dependency",
                "stripe",
                "openai",
                "webhook",
                "redis",
                "s3",
            ],
        )
        if any(code in {502, 503, 504} for code in status_codes) and signals:
            signals.append("upstream 5xx")
        return _classification_match(FailureCategory.DEPENDENCY_FAILURE, 0.84, signals)

    def _match_network(self, search_text: str) -> tuple[FailureCategory | None, float, list[str]]:
        signals = _matched_keywords(
            search_text,
            [
                "econnreset",
                "econnrefused",
                "connection refused",
                "connection reset",
                "socket hang up",
                "dns",
                "enotfound",
                "ssl",
                "tls",
                "broken pipe",
            ],
        )
        return _classification_match(FailureCategory.NETWORK_FAILURE, 0.87, signals)

    def _match_timeout(self, search_text: str) -> tuple[FailureCategory | None, float, list[str]]:
        signals = _matched_keywords(
            search_text,
            [
                "timeout",
                "timed out",
                "deadline exceeded",
                "gateway timeout",
                "request time-out",
            ],
        )
        return _classification_match(FailureCategory.TIMEOUT, 0.83, signals)

    def _match_null_reference(self, search_text: str) -> tuple[FailureCategory | None, float, list[str]]:
        signals = _matched_keywords(
            search_text,
            [
                "nonetype",
                "none type",
                "nullreference",
                "undefined is not",
                "cannot read properties of undefined",
                "attributeerror",
                "nil pointer",
                "null pointer",
            ],
        )
        return _classification_match(FailureCategory.NULL_REFERENCE, 0.92, signals)

    def _match_validation(
        self,
        search_text: str,
        status_codes: Sequence[int],
    ) -> tuple[FailureCategory | None, float, list[str]]:
        signals = _matched_keywords(
            search_text,
            [
                "validation",
                "invalid input",
                "invalid payload",
                "missing required",
                "unprocessable entity",
                "bad request",
                "malformed",
                "expected type",
            ],
        )
        if any(code in {400, 422} for code in status_codes):
            signals.append(f"http {next(code for code in status_codes if code in {400, 422})}")
        return _classification_match(FailureCategory.VALIDATION_FAILURE, 0.88, signals)

    def _match_application_bug(
        self,
        search_text: str,
    ) -> tuple[FailureCategory | None, float, list[str]]:
        signals = _matched_keywords(
            search_text,
            [
                "typeerror",
                "keyerror",
                "indexerror",
                "valueerror",
                "assertionerror",
                "unhandled exception",
                "traceback",
                "not valid json",
                "is not valid json",
                "json.parse",
                "unexpected token",
                "json parse error",
                "syntaxerror",
            ],
        )
        return _classification_match(FailureCategory.APPLICATION_BUG, 0.76, signals)

    def _extract_status_codes(self, events: Sequence[IncidentEventRecord]) -> list[int]:
        status_codes: list[int] = []
        for event in events:
            payload = event.response_payload
            if not isinstance(payload, dict):
                continue
            value = payload.get("status_code")
            if isinstance(value, int):
                status_codes.append(value)
            elif isinstance(value, str) and value.isdigit():
                status_codes.append(int(value))
        return status_codes

    def _stringify_payload(self, payload: dict[str, Any] | list[Any] | str | None) -> str:
        if payload is None:
            return ""
        return str(payload)

    def _build_summary(
        self,
        category: FailureCategory,
        service: str,
        signals: Sequence[str],
    ) -> str:
        signal_text = ", ".join(signals[:3]) if signals else "the incident evidence"
        readable_category = category.value.replace("_", " ")
        return (
            f"The {service} incident is most likely a {readable_category} based on {signal_text}."
        )


def _matched_keywords(search_text: str, keywords: Sequence[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword in search_text]


def _classification_match(
    category: FailureCategory,
    confidence: float,
    signals: Sequence[str],
) -> tuple[FailureCategory | None, float, list[str]]:
    unique_signals = list(dict.fromkeys(signal for signal in signals if signal))
    if not unique_signals:
        return None, 0.0, []
    return category, confidence, unique_signals
