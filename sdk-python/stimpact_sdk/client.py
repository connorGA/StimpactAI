from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import threading
import traceback
from typing import Any
from urllib import error, request


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StimpactRequestError(Exception):
    message: str
    status: int | None = None
    retryable: bool = False
    response_body: str | None = None

    def __str__(self) -> str:
        return self.message


class StimpactClient:
    def __init__(
        self,
        *,
        base_url: str,
        project_id: str,
        api_key: str,
        service: str,
        environment: str = "production",
        timeout_seconds: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.project_id = project_id
        self.api_key = api_key
        self.service = service
        self.environment = environment
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(
        cls,
        *,
        service: str | None = None,
        environment: str | None = None,
        timeout_seconds: float = 5.0,
    ) -> "StimpactClient":
        base_url = _require_env("STIMPACT_BASE_URL")
        project_id = _require_env("STIMPACT_PROJECT_ID")
        api_key = _require_env("STIMPACT_API_KEY")
        resolved_service = service or os.getenv("STIMPACT_SERVICE")
        resolved_environment = environment or os.getenv("STIMPACT_ENVIRONMENT") or "production"
        if not resolved_service:
            raise ValueError("STIMPACT_SERVICE must be set or provided explicitly.")
        return cls(
            base_url=base_url,
            project_id=project_id,
            api_key=api_key,
            service=resolved_service,
            environment=resolved_environment,
            timeout_seconds=timeout_seconds,
        )

    def capture_exception(
        self,
        error_value: BaseException | Exception,
        *,
        request: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
        commit_sha: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        payload = {
            "project_id": self.project_id,
            "environment": self.environment,
            "service": self.service,
            "error_message": str(error_value) or error_value.__class__.__name__,
            "stacktrace": _format_stacktrace(error_value),
            "request": request,
            "response": response,
            "commit_sha": commit_sha,
            "timestamp": timestamp or _utc_now_iso(),
        }
        self._send(payload)

    def wrap(self, operation, *, request: dict[str, Any] | None = None):
        try:
            return operation()
        except Exception as exc:  # pragma: no cover - thin wrapper
            self.capture_exception(exc, request=request)
            raise

    def send_heartbeat(
        self,
        *,
        commit_sha: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        payload = {
            "project_id": self.project_id,
            "environment": self.environment,
            "service": self.service,
            "commit_sha": commit_sha,
            "timestamp": timestamp or _utc_now_iso(),
        }
        self._send(payload, path="/telemetry/heartbeat")

    def start_heartbeat(
        self,
        *,
        interval_seconds: float = 300.0,
        commit_sha: str | None = None,
    ) -> "_HeartbeatHandle":
        stop_event = threading.Event()

        def run() -> None:
            while not stop_event.is_set():
                try:
                    self.send_heartbeat(commit_sha=commit_sha)
                except Exception:
                    pass
                stop_event.wait(interval_seconds)

        thread = threading.Thread(target=run, name="stimpact-heartbeat", daemon=True)
        thread.start()
        return _HeartbeatHandle(stop_event=stop_event, thread=thread)

    def _send(self, payload: dict[str, Any], *, path: str = "/telemetry/error") -> None:
        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            f"{self.base_url}{path}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Stimpact-Project-Key": self.api_key,
            },
            data=body,
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response_handle:
                status = getattr(response_handle, "status", 200)
                if status >= 400:
                    raise StimpactRequestError(
                        f"Telemetry delivery failed with status {status}.",
                        status=status,
                        retryable=status >= 500 or status == 429,
                    )
        except error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="ignore") if exc.fp is not None else None
            raise StimpactRequestError(
                f"Telemetry delivery failed with status {exc.code}.",
                status=exc.code,
                retryable=exc.code >= 500 or exc.code == 429,
                response_body=response_body or None,
            ) from exc
        except error.URLError as exc:
            raise StimpactRequestError(
                "Telemetry delivery failed before the platform acknowledged it.",
                retryable=True,
            ) from exc


def _format_stacktrace(error_value: BaseException) -> str:
    return "".join(traceback.format_exception(type(error_value), error_value, error_value.__traceback__))


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} must be set.")
    return value


@dataclass
class _HeartbeatHandle:
    stop_event: threading.Event
    thread: threading.Thread

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)
