from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from models.failure_classification import FailureCategory, FailureClassification
from models.incident import IncidentEventRecord, IncidentRecord


class FailureClassifier:
    def classify(
        self,
        incident: IncidentRecord,
        events: Sequence[IncidentEventRecord],
    ) -> FailureClassification:
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

        return FailureClassification(
            category=FailureCategory.UNKNOWN,
            confidence=0.35,
            summary=(
                f"The classifier could not confidently map the {incident.service} incident "
                "to a known failure category from the current evidence."
            ),
            matched_signals=[],
            inspected_event_count=len(events),
        )

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
            f"The {service} incident is most likely a {readable_category} based on "
            f"{signal_text}."
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
