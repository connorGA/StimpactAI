from __future__ import annotations

from fastapi import Request, Response, status
from starlette.types import ASGIApp

from api.core.config import (
    allow_legacy_browser_token_exchange,
    get_telemetry_cors_allowed_headers,
    get_telemetry_cors_allowed_methods,
    get_telemetry_cors_allowed_origins,
    get_telemetry_cors_max_age_seconds,
    normalize_origin,
)
from services.telemetry_origin_registry import TelemetryOriginRegistry

class TelemetryCorsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.allowed_origins = set(get_telemetry_cors_allowed_origins())
        self.allowed_methods = {method.upper() for method in get_telemetry_cors_allowed_methods()}
        self.allowed_headers = {header.lower() for header in get_telemetry_cors_allowed_headers()}
        self.max_age_seconds = get_telemetry_cors_max_age_seconds()

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not self._is_cors_managed_path(path):
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive=receive)

        origin = normalize_origin(request.headers.get("origin"))
        is_preflight = (
            scope.get("method") == "OPTIONS"
            and request.headers.get("access-control-request-method") is not None
        )
        origin_allowed = origin is not None and await self._origin_allowed(scope, origin)
        if is_preflight:
            response = self._build_preflight_response(request, origin, origin_allowed)
            await response(scope, receive, send)
            return

        async def send_with_cors(message) -> None:
            if message["type"] == "http.response.start" and origin is not None and origin_allowed:
                headers = list(message.get("headers", []))
                headers = self._set_raw_header(headers, b"access-control-allow-origin", origin.encode("latin-1"))
                headers = self._merge_vary_header(headers, "Origin")
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_cors)

    def _build_preflight_response(
        self,
        request: Request,
        origin: str | None,
        origin_allowed: bool,
    ) -> Response:
        if origin is None or not origin_allowed:
            return Response(status_code=status.HTTP_400_BAD_REQUEST)

        requested_method = request.headers.get("access-control-request-method", "").upper()
        if requested_method not in self.allowed_methods:
            return Response(status_code=status.HTTP_405_METHOD_NOT_ALLOWED)

        requested_headers = {
            item.strip().lower()
            for item in request.headers.get("access-control-request-headers", "").split(",")
            if item.strip()
        }
        if requested_headers and not requested_headers.issubset(self.allowed_headers):
            return Response(status_code=status.HTTP_400_BAD_REQUEST)

        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        self._apply_cors_headers(response, origin)
        response.headers["Access-Control-Allow-Methods"] = ", ".join(sorted(self.allowed_methods))
        response.headers["Access-Control-Allow-Headers"] = ", ".join(
            sorted(header for header in self.allowed_headers)
        )
        response.headers["Access-Control-Max-Age"] = str(self.max_age_seconds)
        return response

    async def _origin_allowed(self, scope, origin: str) -> bool:
        if "*" in self.allowed_origins or origin in self.allowed_origins:
            return True
        registry = self._resolve_origin_registry(scope)
        if registry is None:
            return False
        return await registry.is_origin_allowed(origin)

    def _resolve_origin_registry(self, scope) -> TelemetryOriginRegistry | None:
        app = scope.get("app")
        if app is None:
            return None
        registry = getattr(app.state, "telemetry_origin_registry", None)
        if isinstance(registry, TelemetryOriginRegistry):
            return registry
        return None

    @staticmethod
    def _is_cors_managed_path(path: str) -> bool:
        if path in {"/telemetry/error", "/telemetry/heartbeat"}:
            return True
        return path == "/telemetry/browser-token" and allow_legacy_browser_token_exchange()

    @staticmethod
    def _append_vary(response: Response, value: str) -> None:
        existing = response.headers.get("Vary")
        if existing is None:
            response.headers["Vary"] = value
            return
        vary_parts = {item.strip() for item in existing.split(",") if item.strip()}
        vary_parts.add(value)
        response.headers["Vary"] = ", ".join(sorted(vary_parts))

    def _apply_cors_headers(self, response: Response, origin: str) -> None:
        response.headers["Access-Control-Allow-Origin"] = origin
        self._append_vary(response, "Origin")

    @staticmethod
    def _set_raw_header(
        headers: list[tuple[bytes, bytes]],
        name: bytes,
        value: bytes,
    ) -> list[tuple[bytes, bytes]]:
        filtered = [(key, existing_value) for key, existing_value in headers if key.lower() != name]
        filtered.append((name, value))
        return filtered

    @classmethod
    def _merge_vary_header(
        cls,
        headers: list[tuple[bytes, bytes]],
        value: str,
    ) -> list[tuple[bytes, bytes]]:
        vary_name = b"vary"
        existing_values = [
            existing_value.decode("latin-1")
            for key, existing_value in headers
            if key.lower() == vary_name
        ]
        vary_parts = {
            item.strip()
            for existing in existing_values
            for item in existing.split(",")
            if item.strip()
        }
        vary_parts.add(value)
        merged_value = ", ".join(sorted(vary_parts)).encode("latin-1")
        return cls._set_raw_header(headers, vary_name, merged_value)


def install_telemetry_cors_middleware(app: ASGIApp) -> None:
    app.add_middleware(TelemetryCorsMiddleware)
