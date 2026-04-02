from __future__ import annotations

import json
from urllib import error

from stimpact_sdk import StimpactClient
from stimpact_sdk.client import StimpactRequestError


class _FakeHttpResponse:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_client_builds_from_env(monkeypatch):
    monkeypatch.setenv("STIMPACT_BASE_URL", "https://stimpact.example.com")
    monkeypatch.setenv("STIMPACT_PROJECT_ID", "project-1")
    monkeypatch.setenv("STIMPACT_API_KEY", "stimp_live_123")
    monkeypatch.setenv("STIMPACT_SERVICE", "billing-api")

    client = StimpactClient.from_env()

    assert client.base_url == "https://stimpact.example.com"
    assert client.project_id == "project-1"
    assert client.api_key == "stimp_live_123"
    assert client.service == "billing-api"


def test_capture_exception_posts_expected_payload(monkeypatch):
    monkeypatch.setenv("STIMPACT_BASE_URL", "https://stimpact.example.com")
    monkeypatch.setenv("STIMPACT_PROJECT_ID", "project-1")
    monkeypatch.setenv("STIMPACT_API_KEY", "stimp_live_123")
    monkeypatch.setenv("STIMPACT_SERVICE", "billing-api")

    captured: dict[str, object] = {}

    def fake_urlopen(http_request, timeout):
        captured["url"] = http_request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(http_request.header_items())
        captured["body"] = json.loads(http_request.data.decode("utf-8"))
        return _FakeHttpResponse()

    monkeypatch.setattr("stimpact_sdk.client.request.urlopen", fake_urlopen)

    client = StimpactClient.from_env(environment="production")
    client.capture_exception(RuntimeError("boom"), request={"method": "POST", "url": "/charge"})

    assert captured["url"] == "https://stimpact.example.com/telemetry/error"
    assert captured["timeout"] == 5.0
    assert captured["body"]["project_id"] == "project-1"
    assert captured["body"]["service"] == "billing-api"
    assert captured["body"]["request"] == {"method": "POST", "url": "/charge"}
    assert captured["headers"]["X-stimpact-project-key"] == "stimp_live_123"


def test_capture_exception_raises_wrapped_request_error(monkeypatch):
    monkeypatch.setenv("STIMPACT_BASE_URL", "https://stimpact.example.com")
    monkeypatch.setenv("STIMPACT_PROJECT_ID", "project-1")
    monkeypatch.setenv("STIMPACT_API_KEY", "stimp_live_123")
    monkeypatch.setenv("STIMPACT_SERVICE", "billing-api")

    def fake_urlopen(http_request, timeout):
        del http_request, timeout
        raise error.URLError("network down")

    monkeypatch.setattr("stimpact_sdk.client.request.urlopen", fake_urlopen)

    client = StimpactClient.from_env()

    try:
        client.capture_exception(RuntimeError("boom"))
    except StimpactRequestError as exc:
        assert exc.retryable is True
        assert exc.status is None
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected StimpactRequestError")


def test_send_heartbeat_posts_expected_payload(monkeypatch):
    monkeypatch.setenv("STIMPACT_BASE_URL", "https://stimpact.example.com")
    monkeypatch.setenv("STIMPACT_PROJECT_ID", "project-1")
    monkeypatch.setenv("STIMPACT_API_KEY", "stimp_live_123")
    monkeypatch.setenv("STIMPACT_SERVICE", "billing-api")

    captured: dict[str, object] = {}

    def fake_urlopen(http_request, timeout):
        captured["url"] = http_request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(http_request.data.decode("utf-8"))
        return _FakeHttpResponse()

    monkeypatch.setattr("stimpact_sdk.client.request.urlopen", fake_urlopen)

    client = StimpactClient.from_env(environment="production")
    client.send_heartbeat(commit_sha="abc123")

    assert captured["url"] == "https://stimpact.example.com/telemetry/heartbeat"
    assert captured["timeout"] == 5.0
    assert captured["body"]["project_id"] == "project-1"
    assert captured["body"]["service"] == "billing-api"
    assert captured["body"]["commit_sha"] == "abc123"
