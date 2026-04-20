"""Intelligent telemetry classifier.

Three layers decide whether a telemetry event is:

- ``code_bug``: a real bug that should trigger autonomous repair
- ``user_error``: a user-driven outcome (wrong password, validation, expired
  session) that should NOT create an incident or kick off a run
- ``code_ambiguous``: unclear \u2014 create an incident but require human approval
  before starting the repair loop

The layers run in order until one returns a decisive verdict:

1. Deterministic rules \u2014 cheap, microseconds, high precision
2. LLM classifier \u2014 called only for ambiguous cases and cached per fingerprint
3. Frequency escalation \u2014 flips a suppressed ``user_error`` to ``code_bug``
   when it suddenly spikes across many users (catches systemic bugs that look
   like user errors in isolation, e.g. a malformed-URL button producing 404s).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Literal

from openai import AsyncOpenAI

from api.repositories.fingerprint_classification_repository import (
    FingerprintClassificationRepository,
)
from api.repositories.telemetry_repository import PostgresTelemetryRepository
from models.normalized_telemetry import NormalizedTelemetry

logger = logging.getLogger(__name__)


class Classification(StrEnum):
    CODE_BUG = "code_bug"
    USER_ERROR = "user_error"
    CODE_AMBIGUOUS = "code_ambiguous"


ClassificationSource = Literal["rules", "llm", "frequency", "cache", "default"]


@dataclass(frozen=True)
class ClassificationResult:
    classification: Classification
    reason: str
    source: ClassificationSource
    confidence: float | None = None
    model: str | None = None


AUTH_URL_PATTERN = re.compile(
    r"/(?:auth|login|signin|sign-in|signup|sign-up|logout|sign-out|session|register|password|token|oauth|otp|verify|mfa|2fa|reset|forgot)(?:/|\?|$)",
    re.IGNORECASE,
)

USER_ERROR_STATUS_CODES = {401, 403, 429}
AUTH_STATUS_CODES = {401, 403}

UNHANDLED_EXCEPTION_PATTERNS = (
    "TypeError",
    "ReferenceError",
    "RangeError",
    "SyntaxError",
    "NullPointerException",
    "AttributeError",
    "KeyError",
    "IndexError",
    "UnboundLocalError",
    "ZeroDivisionError",
    "RecursionError",
    "NoSuchElementError",
    "NotImplementedError",
    "AssertionError",
    "Uncaught ",
    "Unhandled ",
    "UnhandledPromiseRejection",
)

VALIDATION_ENVELOPE_HINTS = (
    "errors",
    "field_errors",
    "fieldErrors",
    "validation",
    "validationErrors",
    "invalid_fields",
    "invalidFields",
    "violations",
)

AUTH_MESSAGE_HINTS = (
    "invalid credentials",
    "invalid password",
    "invalid email or password",
    "access denied",
    "authentication failed",
    "wrong password",
    "incorrect password",
    "session has expired",
    "session expired",
    "missing session",
    "not authenticated",
    "authentication required",
    "please log in",
    "please login",
    "log in again",
    "login again",
)

DEFAULT_FREQUENCY_WINDOW_MINUTES = 5
DEFAULT_FREQUENCY_THRESHOLD = 10


@dataclass(frozen=True)
class _RuleVerdict:
    decisive: bool
    result: ClassificationResult | None


class TelemetryClassifier:
    """Three-layer classifier: rules \u2192 LLM (cached) \u2192 frequency escalation.

    Cached fingerprint verdicts can outlive rule changes, so operators may need
    to clear or override a bad cached classification after rollout.
    """

    def __init__(
        self,
        *,
        fingerprint_repository: FingerprintClassificationRepository | None = None,
        telemetry_repository: PostgresTelemetryRepository | None = None,
        openai_client: AsyncOpenAI | None = None,
        openai_model: str | None = None,
        frequency_window_minutes: int = DEFAULT_FREQUENCY_WINDOW_MINUTES,
        frequency_threshold: int = DEFAULT_FREQUENCY_THRESHOLD,
        now_fn=None,
    ) -> None:
        self._fingerprints = fingerprint_repository
        self._telemetry = telemetry_repository
        self._openai = openai_client
        self._openai_model = openai_model
        self._freq_window = timedelta(minutes=max(1, frequency_window_minutes))
        self._freq_threshold = max(2, frequency_threshold)
        self._now = now_fn or (lambda: datetime.now(UTC))

    async def classify(self, telemetry: NormalizedTelemetry) -> ClassificationResult:
        rule = self._apply_deterministic_rules(telemetry)
        if rule.decisive and rule.result is not None:
            if rule.result.classification == Classification.USER_ERROR:
                return await self._maybe_escalate_by_frequency(telemetry, rule.result)
            return rule.result

        cached = await self._get_cached(telemetry)
        if cached is not None:
            if cached.classification == Classification.USER_ERROR:
                return await self._maybe_escalate_by_frequency(telemetry, cached)
            return cached

        llm = await self._classify_with_llm(telemetry)
        if llm is not None:
            await self._cache(telemetry, llm)
            if llm.classification == Classification.USER_ERROR:
                return await self._maybe_escalate_by_frequency(telemetry, llm)
            return llm

        fallback = ClassificationResult(
            classification=Classification.CODE_AMBIGUOUS,
            reason=(
                "No deterministic rule matched and the LLM classifier is unavailable; "
                "falling back to human approval."
            ),
            source="default",
        )
        return fallback

    def _apply_deterministic_rules(
        self, telemetry: NormalizedTelemetry
    ) -> _RuleVerdict:
        status_code = _status_code(telemetry)
        url = _request_url(telemetry)
        method = _request_method(telemetry)
        error_message = telemetry.error_message or ""
        auth_message_matched = _matches_auth_user_error_message(error_message)
        stacktrace = telemetry.stacktrace or ""
        response_body = _response_body(telemetry)

        if status_code is not None and 500 <= status_code <= 599:
            return _decisive(
                Classification.CODE_BUG,
                f"Server-side failure (HTTP {status_code}).",
            )

        if status_code == 429:
            return _decisive(
                Classification.USER_ERROR,
                "HTTP 429 rate-limit response; not a code defect.",
            )

        if status_code in AUTH_STATUS_CODES and url and AUTH_URL_PATTERN.search(url):
            return _decisive(
                Classification.USER_ERROR,
                f"HTTP {status_code} on authentication endpoint '{_shorten_url(url)}'. "
                "Expected outcome for invalid credentials / missing session.",
            )

        if status_code in AUTH_STATUS_CODES and auth_message_matched:
            return _decisive(
                Classification.USER_ERROR,
                f"HTTP {status_code} with a session/authentication message; "
                "expected protected-resource outcome rather than a code defect.",
            )

        if (
            status_code == 422
            and isinstance(response_body, dict)
            and any(key in response_body for key in VALIDATION_ENVELOPE_HINTS)
        ):
            return _decisive(
                Classification.USER_ERROR,
                "HTTP 422 with a validation error envelope; user input rejected.",
            )

        if (
            status_code is None
            and url is None
            and auth_message_matched
        ):
            return _decisive(
                Classification.USER_ERROR,
                "Error message matches a handled authentication failure without HTTP context.",
            )

        if telemetry.handled is True:
            if _looks_like_unhandled_exception(error_message):
                return _decisive(
                    Classification.CODE_BUG,
                    "Handled at the call site, but the exception type still indicates an application defect.",
                )
            if status_code is not None and status_code in USER_ERROR_STATUS_CODES:
                return _decisive(
                    Classification.USER_ERROR,
                    f"Handled HTTP {status_code} response matches an expected user-driven outcome.",
                )

        if telemetry.handled is False and status_code is None:
            if _looks_like_unhandled_exception(error_message):
                return _decisive(
                    Classification.CODE_BUG,
                    "Unhandled exception type bubbled up without HTTP context.",
                )

        if status_code is None and _looks_like_unhandled_exception(error_message):
            return _decisive(
                Classification.CODE_BUG,
                "Error message matches an unhandled exception shape.",
            )

        if method is None and url is None and status_code is None and stacktrace.strip():
            return _decisive(
                Classification.CODE_BUG,
                "Error reported with a stacktrace but no HTTP context; likely application exception.",
            )

        return _RuleVerdict(decisive=False, result=None)

    async def _get_cached(
        self, telemetry: NormalizedTelemetry
    ) -> ClassificationResult | None:
        if self._fingerprints is None:
            return None
        try:
            cached = await self._fingerprints.get(
                project_id=telemetry.project_id,
                fingerprint=telemetry.fingerprint,
            )
        except Exception:
            logger.exception(
                "fingerprint_classification_cache_read_failed",
                extra={
                    "project_id": telemetry.project_id,
                    "fingerprint": telemetry.fingerprint,
                },
            )
            return None
        if not cached:
            return None
        try:
            classification = Classification(str(cached["classification"]))
        except ValueError:
            return None
        reason = cached.get("reason") or "Cached fingerprint classification."
        confidence_value = cached.get("confidence")
        model_value = cached.get("model")
        return ClassificationResult(
            classification=classification,
            reason=str(reason),
            source="cache",
            confidence=float(confidence_value) if confidence_value is not None else None,
            model=str(model_value) if model_value is not None else None,
        )

    async def _cache(
        self, telemetry: NormalizedTelemetry, result: ClassificationResult
    ) -> None:
        if self._fingerprints is None:
            return
        try:
            await self._fingerprints.put(
                project_id=telemetry.project_id,
                fingerprint=telemetry.fingerprint,
                classification=result.classification.value,
                reason=result.reason,
                source=result.source,
                confidence=result.confidence,
                model=result.model,
            )
        except Exception:
            logger.exception(
                "fingerprint_classification_cache_write_failed",
                extra={
                    "project_id": telemetry.project_id,
                    "fingerprint": telemetry.fingerprint,
                },
            )

    async def _classify_with_llm(
        self, telemetry: NormalizedTelemetry
    ) -> ClassificationResult | None:
        if self._openai is None or not self._openai_model:
            return None

        status_code = _status_code(telemetry)
        url = _request_url(telemetry)
        method = _request_method(telemetry)
        response_body = _response_body(telemetry)

        prompt_payload: dict[str, Any] = {
            "project_id": telemetry.project_id,
            "environment": telemetry.environment.value,
            "service": telemetry.service,
            "error_message": _truncate(telemetry.error_message, 1_200),
            "stacktrace_excerpt": _truncate(telemetry.stacktrace, 3_500),
            "handled": telemetry.handled,
            "http": {
                "method": method,
                "url": url,
                "status_code": status_code,
            },
            "response_body_excerpt": _truncate(
                json.dumps(response_body, default=str) if response_body is not None else "",
                1_000,
            ),
        }

        try:
            completion = await self._openai.chat.completions.create(
                model=self._openai_model,
                temperature=0.0,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You classify telemetry events for a self-healing software platform. "
                            "For each event decide whether it represents a code defect worth automated "
                            "repair, an expected user-driven outcome, or is ambiguous. Return raw JSON "
                            "with keys: classification (one of 'code_bug', 'user_error', "
                            "'code_ambiguous'), reason (one short sentence citing the strongest "
                            "signal), confidence (0.0-1.0). Treat invalid credentials, expired "
                            "sessions, validation errors, and rate-limit responses as user_error. "
                            "Treat 5xx, unhandled exceptions, and clear defects in application code "
                            "as code_bug. If you cannot decide with moderate confidence, answer "
                            "code_ambiguous."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(prompt_payload, indent=2, sort_keys=True),
                    },
                ],
                response_format={"type": "json_object"},
            )
        except Exception:
            logger.exception(
                "telemetry_classifier_llm_call_failed",
                extra={
                    "project_id": telemetry.project_id,
                    "fingerprint": telemetry.fingerprint,
                },
            )
            return None

        content = completion.choices[0].message.content if completion.choices else None
        if not content:
            return None
        try:
            payload = json.loads(_extract_json_object(content))
            classification = Classification(str(payload["classification"]).strip())
            reason = str(payload.get("reason") or "LLM classification.").strip()
            confidence_value = payload.get("confidence")
            confidence = float(confidence_value) if confidence_value is not None else None
        except Exception:
            logger.exception(
                "telemetry_classifier_llm_parse_failed",
                extra={"raw": content[:500]},
            )
            return None
        return ClassificationResult(
            classification=classification,
            reason=reason or "LLM classification.",
            source="llm",
            confidence=confidence,
            model=self._openai_model,
        )

    async def _maybe_escalate_by_frequency(
        self,
        telemetry: NormalizedTelemetry,
        current: ClassificationResult,
    ) -> ClassificationResult:
        if self._telemetry is None:
            return current
        since = self._now() - self._freq_window
        try:
            count = await self._telemetry.count_recent_by_fingerprint(
                project_id=telemetry.project_id,
                fingerprint=telemetry.fingerprint,
                since=since,
            )
        except Exception:
            logger.exception(
                "telemetry_classifier_frequency_query_failed",
                extra={
                    "project_id": telemetry.project_id,
                    "fingerprint": telemetry.fingerprint,
                },
            )
            return current
        if count >= self._freq_threshold:
            escalation_reason = (
                f"Frequency escalation: fingerprint hit {count} times in the last "
                f"{int(self._freq_window.total_seconds() // 60)} minute(s); treating as a bug "
                "even though individual occurrences look like user errors."
            )
            return ClassificationResult(
                classification=Classification.CODE_BUG,
                reason=escalation_reason,
                source="frequency",
            )
        return current


def _status_code(telemetry: NormalizedTelemetry) -> int | None:
    if telemetry.response is None:
        return None
    code = telemetry.response.status_code
    return int(code) if isinstance(code, int) else None


def _request_url(telemetry: NormalizedTelemetry) -> str | None:
    if telemetry.request is None:
        return None
    url = telemetry.request.url
    if isinstance(url, str) and url.strip():
        return url.strip()
    return None


def _request_method(telemetry: NormalizedTelemetry) -> str | None:
    if telemetry.request is None:
        return None
    method = telemetry.request.method
    if isinstance(method, str) and method.strip():
        return method.strip().upper()
    return None


def _response_body(telemetry: NormalizedTelemetry) -> Any:
    if telemetry.response is None:
        return None
    return telemetry.response.body


def _looks_like_unhandled_exception(message: str) -> bool:
    if not message:
        return False
    normalized = message.strip()
    return any(pattern in normalized for pattern in UNHANDLED_EXCEPTION_PATTERNS)


def _matches_auth_user_error_message(message: str) -> bool:
    if not message:
        return False
    normalized = message.lower()
    return any(hint in normalized for hint in AUTH_MESSAGE_HINTS)


def _decisive(classification: Classification, reason: str) -> _RuleVerdict:
    return _RuleVerdict(
        decisive=True,
        result=ClassificationResult(
            classification=classification,
            reason=reason,
            source="rules",
        ),
    )


def _shorten_url(url: str) -> str:
    if len(url) <= 80:
        return url
    return f"{url[:77]}\u2026"


def _truncate(value: str, limit: int) -> str:
    if value is None:
        return ""
    if len(value) <= limit:
        return value
    return f"{value[:limit]}\n... [truncated]"


def _extract_json_object(content: str) -> str:
    normalized = content.strip()
    if normalized.startswith("{") and normalized.endswith("}"):
        return normalized
    start = normalized.find("{")
    end = normalized.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response.")
    return normalized[start : end + 1]
