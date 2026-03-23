from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from threading import Lock
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from api.core.config import get_deployment_environment, is_local_development_environment

_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("stimpact_request_id", default="-")


def get_request_id() -> str:
    return _request_id_ctx.get()


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", get_request_id()),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    root_logger = logging.getLogger()
    if getattr(root_logger, "_stimpact_logging_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    if is_local_development_environment():
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s [request_id=%(request_id)s] %(message)s"
        )
    else:
        formatter = JsonLogFormatter()
    handler.setFormatter(formatter)
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)
    root_logger._stimpact_logging_configured = True  # type: ignore[attr-defined]


@dataclass(frozen=True)
class _MetricKey:
    name: str
    labels: tuple[tuple[str, str], ...]


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[_MetricKey, float] = defaultdict(float)
        self._histograms: dict[_MetricKey, tuple[int, float]] = defaultdict(lambda: (0, 0.0))
        self._lock = Lock()

    def increment(self, name: str, *, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        key = _MetricKey(name, tuple(sorted((labels or {}).items())))
        with self._lock:
            self._counters[key] += value

    def observe(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
        key = _MetricKey(name, tuple(sorted((labels or {}).items())))
        with self._lock:
            count, total = self._histograms[key]
            self._histograms[key] = (count + 1, total + value)

    def render_prometheus(self) -> str:
        lines: list[str] = [
            f'stimpact_build_info{{environment="{get_deployment_environment()}"}} 1'
        ]
        with self._lock:
            for key, value in sorted(self._counters.items(), key=lambda item: (item[0].name, item[0].labels)):
                lines.append(f"{key.name}{_format_labels(key.labels)} {value}")
            for key, (count, total) in sorted(
                self._histograms.items(),
                key=lambda item: (item[0].name, item[0].labels),
            ):
                lines.append(f"{key.name}_count{_format_labels(key.labels)} {count}")
                lines.append(f"{key.name}_sum{_format_labels(key.labels)} {total}")
        return "\n".join(lines) + "\n"


def _format_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    rendered = ",".join(f'{key}="{value}"' for key, value in labels)
    return f"{{{rendered}}}"


_metrics_registry = MetricsRegistry()


def get_metrics_registry() -> MetricsRegistry:
    return _metrics_registry


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid4())
        token = _request_id_ctx.set(request_id)
        started_at = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
        finally:
            duration = time.perf_counter() - started_at
            status_code = getattr(response, "status_code", 500)
            path = request.url.path
            get_metrics_registry().increment(
                "stimpact_api_requests_total",
                labels={
                    "method": request.method,
                    "path": path,
                    "status_code": str(status_code),
                },
            )
            get_metrics_registry().observe(
                "stimpact_api_request_latency_seconds",
                duration,
                labels={"method": request.method, "path": path},
            )
            logging.getLogger("api.request").info(
                "request completed",
                extra={
                    "method": request.method,
                    "path": path,
                    "status_code": status_code,
                    "duration_seconds": round(duration, 6),
                },
            )
            _request_id_ctx.reset(token)
        if response is None:
            raise RuntimeError("Request handling completed without a response.")
        response.headers["X-Request-Id"] = request_id
        return response
