from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import deque
from typing import Protocol

from redis.asyncio import Redis

from fastapi import Depends, Request, status

from api.core.config import (
    get_admin_api_token,
    get_control_plane_rate_limit_per_minute,
    get_redis_url,
    get_telemetry_rate_limit_per_minute,
    is_control_plane_auth_enforced,
    is_project_api_key_auth_enforced,
)
from api.core.errors import APIError
from api.db.postgres import PostgresConnectionManager, get_postgres_manager
from api.observability import get_metrics_registry
from api.repositories.control_plane_repository import ControlPlaneRepository
from api.schemas.telemetry import TelemetryErrorRequest

PROJECT_API_KEY_HEADER = "X-Stimpact-Project-Key"
BEARER_PREFIX = "Bearer "


def build_project_api_key() -> tuple[str, str]:
    raw_key = f"stimp_live_{secrets.token_urlsafe(24)}"
    return raw_key, raw_key[:16]


def hash_api_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class RateLimiter(Protocol):
    async def enforce(self, bucket: str, *, limit: int, window_seconds: int = 60) -> None: ...


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = {}

    async def enforce(self, bucket: str, *, limit: int, window_seconds: int = 60) -> None:
        now = time.monotonic()
        threshold = now - window_seconds
        queue = self._buckets.setdefault(bucket, deque())
        while queue and queue[0] <= threshold:
            queue.popleft()
        if len(queue) >= limit:
            get_metrics_registry().increment(
                "stimpact_rate_limit_exceeded_total",
                labels={"backend": "memory"},
            )
            raise APIError(
                "Rate limit exceeded. Please retry shortly.",
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                code="rate_limited",
            )
        queue.append(now)
        if len(self._buckets) > 10_000:
            self._cleanup_stale(threshold)

    def _cleanup_stale(self, threshold: float) -> None:
        stale_keys = [key for key, queue in self._buckets.items() if not queue or queue[-1] <= threshold]
        for key in stale_keys[:1000]:
            self._buckets.pop(key, None)


class RedisRateLimiter:
    def __init__(self, client: Redis) -> None:
        self._client = client
        self._fallback = InMemoryRateLimiter()

    async def enforce(self, bucket: str, *, limit: int, window_seconds: int = 60) -> None:
        now = int(time.time())
        window_id = now // window_seconds
        key = f"stimpact:ratelimit:{bucket}:{window_id}"
        try:
            current = await self._client.incr(key)
            if current == 1:
                await self._client.expire(key, window_seconds + 1)
            if current > limit:
                get_metrics_registry().increment(
                    "stimpact_rate_limit_exceeded_total",
                    labels={"backend": "redis"},
                )
                raise APIError(
                    "Rate limit exceeded. Please retry shortly.",
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    code="rate_limited",
                )
        except Exception:
            get_metrics_registry().increment(
                "stimpact_rate_limiter_fallback_total",
                labels={"backend": "redis"},
            )
            await self._fallback.enforce(bucket, limit=limit, window_seconds=window_seconds)


def _get_rate_limiter(request: Request) -> RateLimiter:
    existing = getattr(request.app.state, "rate_limiter", None)
    if isinstance(existing, (InMemoryRateLimiter, RedisRateLimiter)):
        return existing
    redis_url = get_redis_url()
    limiter: RateLimiter
    if redis_url:
        limiter = RedisRateLimiter(Redis.from_url(redis_url, decode_responses=True))
    else:
        limiter = InMemoryRateLimiter()
    request.app.state.rate_limiter = limiter
    return limiter


def _client_identity(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


def _extract_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if authorization is None:
        return None
    if not authorization.startswith(BEARER_PREFIX):
        return None
    token = authorization[len(BEARER_PREFIX) :].strip()
    return token or None


def _extract_project_api_key(request: Request) -> str | None:
    explicit = request.headers.get(PROJECT_API_KEY_HEADER)
    if explicit is not None and explicit.strip():
        return explicit.strip()
    return _extract_bearer_token(request)


def _has_valid_admin_token(request: Request) -> bool:
    expected = get_admin_api_token()
    if expected is None:
        return False
    provided = _extract_bearer_token(request)
    return provided is not None and hmac.compare_digest(provided, expected)


def get_security_control_plane_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> ControlPlaneRepository:
    return ControlPlaneRepository(manager.pool)


async def enforce_control_plane_rate_limit(request: Request) -> None:
    limit = get_control_plane_rate_limit_per_minute()
    token = _extract_bearer_token(request)
    bucket = f"control-plane:{token[:12] if token else _client_identity(request)}"
    await _get_rate_limiter(request).enforce(bucket, limit=limit)


async def enforce_telemetry_rate_limit(request: Request, payload: TelemetryErrorRequest) -> None:
    limit = get_telemetry_rate_limit_per_minute()
    bucket = f"telemetry:{payload.project_id}:{_client_identity(request)}"
    await _get_rate_limiter(request).enforce(bucket, limit=limit)


async def require_control_plane_access(request: Request) -> None:
    if not is_control_plane_auth_enforced():
        return
    expected = get_admin_api_token()
    if expected is None:
        raise APIError(
            "Control-plane authentication is enabled but AGENT_PLATFORM_ADMIN_TOKEN is not configured.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="control_plane_auth_unconfigured",
        )
    provided = _extract_bearer_token(request)
    if provided is None:
        raise APIError(
            "A bearer token is required for control-plane access.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="control_plane_token_missing",
        )
    if not hmac.compare_digest(provided, expected):
        raise APIError(
            "The control-plane bearer token is invalid.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="control_plane_token_invalid",
        )


async def require_project_control_plane_access(
    request: Request,
    project_id: str,
    repository: ControlPlaneRepository = Depends(get_security_control_plane_repository),
) -> None:
    if not is_control_plane_auth_enforced():
        return
    if _has_valid_admin_token(request):
        return
    if isinstance(repository, ControlPlaneRepository) and getattr(repository, "_pool", None) is None:
        raise APIError(
            "Project-scoped control-plane access requires Postgres-backed control-plane access.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="project_control_plane_auth_unavailable",
        )
    project_key = _extract_project_api_key(request)
    if project_key is None:
        raise APIError(
            "A project API key is required for project-scoped onboarding access.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="project_control_plane_token_missing",
        )
    record = await repository.find_active_project_api_key(
        project_id=project_id,
        key_hash=hash_api_key(project_key),
    )
    if record is None:
        raise APIError(
            "The project API key is invalid for this project.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="project_control_plane_token_invalid",
        )
    await repository.mark_project_api_key_used(record.id)


async def require_project_read_access(
    request: Request,
    project_id: str,
    repository: ControlPlaneRepository = Depends(get_security_control_plane_repository),
) -> None:
    if _has_valid_admin_token(request):
        return
    if isinstance(repository, ControlPlaneRepository) and getattr(repository, "_pool", None) is None:
        if is_project_api_key_auth_enforced():
            raise APIError(
                "Project-scoped incident access requires Postgres-backed control-plane access.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="project_api_key_auth_unavailable",
            )
        return

    project_key = _extract_project_api_key(request)
    if project_key is not None:
        record = await repository.find_active_project_api_key(
            project_id=project_id,
            key_hash=hash_api_key(project_key),
        )
        if record is not None:
            await repository.mark_project_api_key_used(record.id)
            return

    project_has_keys = await repository.has_active_project_api_keys(project_id)
    if project_has_keys:
        code = "project_api_key_missing" if project_key is None else "project_api_key_invalid"
        raise APIError(
            "A valid project API key is required to access incidents for this project.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=code,
        )

    if is_project_api_key_auth_enforced():
        raise APIError(
            "Project API keys are required for incident access.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="project_api_key_required",
        )


async def require_project_list_access(
    request: Request,
    project_id: str | None,
    repository: ControlPlaneRepository = Depends(get_security_control_plane_repository),
) -> None:
    if project_id is None:
        if is_project_api_key_auth_enforced() or _extract_project_api_key(request) is not None or _has_valid_admin_token(request):
            raise APIError(
                "A project_id is required for project-scoped incident access.",
                status_code=status.HTTP_400_BAD_REQUEST,
                code="project_id_required",
            )
        return
    await require_project_read_access(request, project_id, repository)


async def require_telemetry_ingest_access(
    request: Request,
    payload: TelemetryErrorRequest,
    repository: ControlPlaneRepository = Depends(get_security_control_plane_repository),
) -> None:
    if isinstance(repository, ControlPlaneRepository) and getattr(repository, "_pool", None) is None:
        if is_project_api_key_auth_enforced():
            raise APIError(
                "Project API key authentication requires Postgres-backed control-plane access.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="project_api_key_auth_unavailable",
            )
        return

    project_key = _extract_project_api_key(request)
    if project_key is not None:
        record = await repository.find_active_project_api_key(
            project_id=payload.project_id,
            key_hash=hash_api_key(project_key),
        )
        if record is not None:
            await repository.mark_project_api_key_used(record.id)
            return

    project_has_keys = await repository.has_active_project_api_keys(payload.project_id)
    if project_has_keys:
        code = "project_api_key_missing" if project_key is None else "project_api_key_invalid"
        raise APIError(
            "A valid project API key is required to submit telemetry for this project.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=code,
        )

    if is_project_api_key_auth_enforced():
        raise APIError(
            "Project API keys are required for telemetry ingestion.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="project_api_key_required",
        )
