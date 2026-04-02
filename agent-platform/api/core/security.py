from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from collections import deque
from dataclasses import dataclass
from typing import Protocol

import jwt
from redis.asyncio import Redis

from fastapi import Depends, Request, status

from api.core.config import (
    get_admin_api_token,
    get_auth_session_secret,
    get_auth_session_ttl_seconds,
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
from api.repositories.identity_repository import IdentityRepository
from api.schemas.telemetry import TelemetryErrorRequest, TelemetryHeartbeatRequest
from models.auth import OrganizationMembershipRole

PROJECT_API_KEY_HEADER = "X-Stimpact-Project-Key"
BEARER_PREFIX = "Bearer "
AUTH_SESSION_ALGORITHM = "HS256"


def build_project_api_key() -> tuple[str, str]:
    raw_key = f"stimp_live_{secrets.token_urlsafe(24)}"
    return raw_key, raw_key[:16]


def hash_api_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_token_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(value: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(value.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=64)
    return f"scrypt:16384:8:1:{salt.hex()}:{derived.hex()}"


def verify_password(value: str, password_hash: str) -> bool:
    try:
        algorithm, n_value, r_value, p_value, salt_hex, digest_hex = password_hash.split(":", 5)
    except ValueError:
        return False
    if algorithm != "scrypt":
        return False
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        derived = hashlib.scrypt(
            value.encode("utf-8"),
            salt=salt,
            n=int(n_value),
            r=int(r_value),
            p=int(p_value),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived, expected)


@dataclass(frozen=True)
class AuthenticatedUserContext:
    user_id: str
    organization_id: str
    role: OrganizationMembershipRole


def build_session_token(
    *,
    user_id: str,
    organization_id: str,
    role: OrganizationMembershipRole,
) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "org_id": organization_id,
        "role": role.value,
        "type": "session",
        "iat": now,
        "exp": now + get_auth_session_ttl_seconds(),
    }
    return jwt.encode(payload, get_auth_session_secret(), algorithm=AUTH_SESSION_ALGORITHM)


def decode_session_token(token: str) -> AuthenticatedUserContext:
    try:
        payload = jwt.decode(
            token,
            get_auth_session_secret(),
            algorithms=[AUTH_SESSION_ALGORITHM],
        )
    except jwt.PyJWTError as exc:
        raise APIError(
            "The user session token is invalid or expired.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="session_token_invalid",
        ) from exc
    if payload.get("type") != "session":
        raise APIError(
            "The user session token is invalid.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="session_token_invalid",
        )
    user_id = payload.get("sub")
    organization_id = payload.get("org_id")
    role = payload.get("role")
    if not isinstance(user_id, str) or not isinstance(organization_id, str) or not isinstance(role, str):
        raise APIError(
            "The user session token is invalid.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="session_token_invalid",
        )
    return AuthenticatedUserContext(
        user_id=user_id,
        organization_id=organization_id,
        role=OrganizationMembershipRole(role),
    )


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


def get_identity_repository(
    manager: PostgresConnectionManager = Depends(get_postgres_manager),
) -> IdentityRepository:
    return IdentityRepository(manager.pool)


def _resolve_identity_repository_from_request(request: Request) -> IdentityRepository:
    manager = get_postgres_manager(request)
    return IdentityRepository(manager.pool)


def _extract_user_session_context(request: Request) -> AuthenticatedUserContext | None:
    token = _extract_bearer_token(request)
    if token is None:
        return None
    try:
        return decode_session_token(token)
    except APIError:
        return None


async def get_current_user_context(
    request: Request,
    repository: IdentityRepository = Depends(get_identity_repository),
) -> AuthenticatedUserContext:
    context = _extract_user_session_context(request)
    if context is None:
        raise APIError(
            "A valid user session is required.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="session_required",
        )
    membership = await repository.get_membership(context.organization_id, context.user_id)
    if membership is None:
        raise APIError(
            "The user does not belong to the requested organization.",
            status_code=status.HTTP_403_FORBIDDEN,
            code="organization_access_denied",
        )
    return context


async def enforce_control_plane_rate_limit(request: Request) -> None:
    limit = get_control_plane_rate_limit_per_minute()
    token = _extract_bearer_token(request)
    bucket = f"control-plane:{token[:12] if token else _client_identity(request)}"
    await _get_rate_limiter(request).enforce(bucket, limit=limit)


async def enforce_telemetry_payload_rate_limit(request: Request, payload) -> None:
    limit = get_telemetry_rate_limit_per_minute()
    bucket = f"telemetry:{payload.project_id}:{_client_identity(request)}"
    await _get_rate_limiter(request).enforce(bucket, limit=limit)


async def enforce_telemetry_rate_limit(request: Request, payload: TelemetryErrorRequest) -> None:
    await enforce_telemetry_payload_rate_limit(request, payload)


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
    identity_repository: IdentityRepository | None = Depends(get_identity_repository),
) -> None:
    if not is_control_plane_auth_enforced():
        return
    if _has_valid_admin_token(request):
        return
    user_context = _extract_user_session_context(request)
    if user_context is not None:
        resolved_identity_repository = identity_repository or _resolve_identity_repository_from_request(request)
        project = await resolved_identity_repository.get_project_for_user(project_id, user_context.user_id)
        if project is not None:
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
    identity_repository: IdentityRepository | None = None,
) -> None:
    if _has_valid_admin_token(request):
        return
    user_context = _extract_user_session_context(request)
    if user_context is not None:
        resolved_identity_repository = identity_repository or _resolve_identity_repository_from_request(request)
        project = await resolved_identity_repository.get_project_for_user(project_id, user_context.user_id)
        if project is not None:
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
    identity_repository: IdentityRepository | None = None,
) -> None:
    if project_id is None:
        if (
            is_project_api_key_auth_enforced()
            or _extract_project_api_key(request) is not None
            or _has_valid_admin_token(request)
            or _extract_user_session_context(request) is not None
        ):
            raise APIError(
                "A project_id is required for project-scoped incident access.",
                status_code=status.HTTP_400_BAD_REQUEST,
                code="project_id_required",
            )
        return
    await require_project_read_access(
        request,
        project_id,
        repository=repository,
        identity_repository=identity_repository,
    )


async def authorize_telemetry_ingest_payload(
    request: Request,
    payload,
    repository: ControlPlaneRepository,
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


async def require_telemetry_ingest_access(
    request: Request,
    payload: TelemetryErrorRequest,
    repository: ControlPlaneRepository = Depends(get_security_control_plane_repository),
) -> None:
    await authorize_telemetry_ingest_payload(request, payload, repository)


async def require_telemetry_heartbeat_access(
    request: Request,
    payload: TelemetryHeartbeatRequest,
    repository: ControlPlaneRepository = Depends(get_security_control_plane_repository),
) -> None:
    await authorize_telemetry_ingest_payload(request, payload, repository)
