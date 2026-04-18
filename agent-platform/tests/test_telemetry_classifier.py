from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from models.normalized_telemetry import NormalizedTelemetry
from services.telemetry_classifier import (
    Classification,
    TelemetryClassifier,
)
from shared.types.telemetry import Environment, HttpRequestContext, HttpResponseContext


def build_normalized(
    *,
    error_message: str = "Something went wrong",
    stacktrace: str = "Traceback:\n  line 1",
    request: HttpRequestContext | None = None,
    response: HttpResponseContext | None = None,
    handled: bool | None = None,
    project_id: str = "project-1",
    fingerprint: str = "fp-1",
) -> NormalizedTelemetry:
    return NormalizedTelemetry(
        id="tlm-1",
        project_id=project_id,
        environment=Environment.PRODUCTION,
        service="api",
        error_message=error_message,
        stacktrace=stacktrace,
        fingerprint=fingerprint,
        request=request,
        response=response,
        commit_sha=None,
        handled=handled,
        occurred_at=datetime(2026, 3, 16, 12, 0, tzinfo=UTC),
    )


class StubFingerprintRepo:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str], dict[str, Any]] = {}

    async def get(self, *, project_id: str, fingerprint: str) -> dict[str, Any] | None:
        return self.store.get((project_id, fingerprint))

    async def put(
        self,
        *,
        project_id: str,
        fingerprint: str,
        classification: str,
        reason: str | None,
        source: str,
        confidence: float | None = None,
        model: str | None = None,
    ) -> None:
        self.store[(project_id, fingerprint)] = {
            "classification": classification,
            "reason": reason,
            "source": source,
            "confidence": confidence,
            "model": model,
        }


class StubTelemetryRepo:
    def __init__(self, counts: dict[tuple[str, str], int] | None = None) -> None:
        self.counts = counts or {}

    async def count_recent_by_fingerprint(
        self, *, project_id: str, fingerprint: str, since
    ) -> int:
        _ = since
        return self.counts.get((project_id, fingerprint), 0)


@pytest.mark.asyncio
async def test_handled_flag_is_treated_as_user_error() -> None:
    classifier = TelemetryClassifier()
    telemetry = build_normalized(handled=True)
    result = await classifier.classify(telemetry)
    assert result.classification == Classification.USER_ERROR
    assert result.source == "rules"


@pytest.mark.asyncio
async def test_5xx_is_code_bug() -> None:
    classifier = TelemetryClassifier()
    telemetry = build_normalized(
        response=HttpResponseContext(status_code=503),
    )
    result = await classifier.classify(telemetry)
    assert result.classification == Classification.CODE_BUG


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403])
async def test_auth_status_on_auth_endpoint_is_user_error(status_code: int) -> None:
    classifier = TelemetryClassifier()
    telemetry = build_normalized(
        request=HttpRequestContext(
            method="POST", url="https://api.example.com/api:abc/auth/login"
        ),
        response=HttpResponseContext(status_code=status_code),
    )
    result = await classifier.classify(telemetry)
    assert result.classification == Classification.USER_ERROR
    assert "auth" in result.reason.lower() or str(status_code) in result.reason


@pytest.mark.asyncio
async def test_rate_limit_is_user_error() -> None:
    classifier = TelemetryClassifier()
    telemetry = build_normalized(response=HttpResponseContext(status_code=429))
    result = await classifier.classify(telemetry)
    assert result.classification == Classification.USER_ERROR


@pytest.mark.asyncio
async def test_422_with_validation_envelope_is_user_error() -> None:
    classifier = TelemetryClassifier()
    telemetry = build_normalized(
        response=HttpResponseContext(
            status_code=422,
            body={"errors": {"email": ["is invalid"]}},
        ),
    )
    result = await classifier.classify(telemetry)
    assert result.classification == Classification.USER_ERROR


@pytest.mark.asyncio
async def test_unhandled_exception_without_http_context_is_code_bug() -> None:
    classifier = TelemetryClassifier()
    telemetry = build_normalized(
        error_message="TypeError: Cannot read property 'x' of undefined",
        handled=False,
    )
    result = await classifier.classify(telemetry)
    assert result.classification == Classification.CODE_BUG


@pytest.mark.asyncio
async def test_invalid_credentials_message_without_http_context_is_user_error() -> None:
    classifier = TelemetryClassifier()
    telemetry = build_normalized(
        error_message="Invalid Credentials.",
        stacktrace="Error: Invalid Credentials.\n    at login",
        handled=None,
        request=None,
        response=None,
    )
    result = await classifier.classify(telemetry)
    assert result.classification == Classification.USER_ERROR
    assert result.source == "rules"


@pytest.mark.asyncio
async def test_session_expired_message_without_http_context_is_user_error() -> None:
    classifier = TelemetryClassifier()
    telemetry = build_normalized(
        error_message="Soul Song Service: Your session has expired. Please log in again.",
        stacktrace="Error: session expired\n    at refreshSession",
        handled=None,
        request=None,
        response=None,
    )
    result = await classifier.classify(telemetry)
    assert result.classification == Classification.USER_ERROR
    assert result.source == "rules"


@pytest.mark.asyncio
async def test_session_expired_message_with_stacktrace_still_beats_no_http_bug_rule() -> None:
    classifier = TelemetryClassifier()
    telemetry = build_normalized(
        error_message="Your session has expired. Please log in again.",
        stacktrace="TypeError: auth token missing\n    at resumePlayback",
        handled=None,
        request=None,
        response=None,
    )
    result = await classifier.classify(telemetry)
    assert result.classification == Classification.USER_ERROR
    assert result.source == "rules"


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403])
async def test_session_expired_message_on_non_auth_url_is_user_error(status_code: int) -> None:
    classifier = TelemetryClassifier()
    telemetry = build_normalized(
        error_message="Your session has expired. Please log in again.",
        request=HttpRequestContext(
            method="GET", url="https://api.example.com/api/music/songs"
        ),
        response=HttpResponseContext(status_code=status_code),
    )
    result = await classifier.classify(telemetry)
    assert result.classification == Classification.USER_ERROR
    assert result.source == "rules"


@pytest.mark.asyncio
async def test_ambiguous_without_llm_falls_back_to_ambiguous() -> None:
    classifier = TelemetryClassifier()
    telemetry = build_normalized(
        error_message="An unexpected outcome",
        stacktrace="",
        response=HttpResponseContext(status_code=404),
        request=HttpRequestContext(method="GET", url="https://api.example.com/v1/item/123"),
    )
    result = await classifier.classify(telemetry)
    assert result.classification == Classification.CODE_AMBIGUOUS


@pytest.mark.asyncio
async def test_cache_hit_bypasses_rules_and_llm() -> None:
    repo = StubFingerprintRepo()
    repo.store[("project-1", "fp-1")] = {
        "classification": "user_error",
        "reason": "cached reason",
        "source": "llm",
        "confidence": 0.9,
        "model": "gpt-test",
    }
    classifier = TelemetryClassifier(fingerprint_repository=repo)
    telemetry = build_normalized(
        error_message="ambiguous",
        stacktrace="",
        response=HttpResponseContext(status_code=404),
        request=HttpRequestContext(method="GET", url="https://api.example.com/v1/item/123"),
    )
    result = await classifier.classify(telemetry)
    assert result.classification == Classification.USER_ERROR
    assert result.source == "cache"


@pytest.mark.asyncio
async def test_frequency_escalation_flips_user_error_to_code_bug() -> None:
    telemetry_repo = StubTelemetryRepo(counts={("project-1", "fp-1"): 25})
    classifier = TelemetryClassifier(
        telemetry_repository=telemetry_repo,
        frequency_window_minutes=5,
        frequency_threshold=10,
    )
    telemetry = build_normalized(
        request=HttpRequestContext(
            method="POST", url="https://api.example.com/api/auth/login"
        ),
        response=HttpResponseContext(status_code=403),
    )
    result = await classifier.classify(telemetry)
    assert result.classification == Classification.CODE_BUG
    assert result.source == "frequency"


@pytest.mark.asyncio
async def test_frequency_below_threshold_keeps_user_error() -> None:
    telemetry_repo = StubTelemetryRepo(counts={("project-1", "fp-1"): 3})
    classifier = TelemetryClassifier(
        telemetry_repository=telemetry_repo,
        frequency_threshold=10,
    )
    telemetry = build_normalized(
        request=HttpRequestContext(
            method="POST", url="https://api.example.com/api/auth/login"
        ),
        response=HttpResponseContext(status_code=403),
    )
    result = await classifier.classify(telemetry)
    assert result.classification == Classification.USER_ERROR


class StubLLMClient:
    def __init__(self, verdict: dict[str, Any]) -> None:
        self._verdict = verdict
        self.calls: list[dict[str, Any]] = []
        self.chat = self  # type: ignore[assignment]
        self.completions = self  # type: ignore[assignment]

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)

        class _Choice:
            def __init__(self, content: str) -> None:
                self.message = type("Msg", (), {"content": content})

        class _Completion:
            def __init__(self, choices: list[_Choice]) -> None:
                self.choices = choices

        import json

        return _Completion([_Choice(json.dumps(self._verdict))])


@pytest.mark.asyncio
async def test_llm_classification_is_cached() -> None:
    fingerprint_repo = StubFingerprintRepo()
    llm = StubLLMClient(
        {"classification": "user_error", "reason": "LLM said so", "confidence": 0.8}
    )
    classifier = TelemetryClassifier(
        fingerprint_repository=fingerprint_repo,
        openai_client=llm,
        openai_model="gpt-test",
    )
    telemetry = build_normalized(
        error_message="ambiguous",
        stacktrace="",
        response=HttpResponseContext(status_code=404),
        request=HttpRequestContext(method="GET", url="https://api.example.com/v1/item/123"),
    )
    result = await classifier.classify(telemetry)
    assert result.classification == Classification.USER_ERROR
    assert result.source == "llm"
    assert len(llm.calls) == 1
    assert llm.calls[0]["model"] == "gpt-test"
    assert llm.calls[0]["response_format"] == {"type": "json_object"}
    assert llm.calls[0]["temperature"] == 0.0
    assert llm.calls[0]["messages"][0]["role"] == "system"
    assert "code_ambiguous" in llm.calls[0]["messages"][0]["content"]
    assert '"status_code": 404' in llm.calls[0]["messages"][1]["content"]
    cached = fingerprint_repo.store[("project-1", "fp-1")]
    assert cached["classification"] == "user_error"
    assert cached["source"] == "llm"
    assert cached["model"] == "gpt-test"
