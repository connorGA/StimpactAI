from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from time import monotonic

from api.repositories.control_plane_repository import ControlPlaneRepository

OriginLookupOverride = Callable[[], list[str] | Awaitable[list[str]]]


class TelemetryOriginRegistry:
    def __init__(
        self,
        *,
        pool_getter: Callable[[], object | None],
        fallback_origins: list[str] | None = None,
        lookup_override: OriginLookupOverride | None = None,
        cache_ttl_seconds: float = 5.0,
    ) -> None:
        self._pool_getter = pool_getter
        self._fallback_origins = set(fallback_origins or [])
        self.lookup_override = lookup_override
        self._cache_ttl_seconds = max(0.0, cache_ttl_seconds)
        self._cached_dynamic_origins: set[str] = set()
        self._cache_expires_at = 0.0
        self._refresh_lock = asyncio.Lock()

    async def list_allowed_origins(self) -> set[str]:
        allowed_origins = set(self._fallback_origins)
        allowed_origins.update(await self._load_dynamic_origins())
        return allowed_origins

    async def is_origin_allowed(self, origin: str) -> bool:
        return origin in await self.list_allowed_origins()

    def invalidate_cache(self) -> None:
        self._cache_expires_at = 0.0
        self._cached_dynamic_origins = set()

    async def _load_dynamic_origins(self) -> set[str]:
        if self.lookup_override is not None:
            result = self.lookup_override()
            if inspect.isawaitable(result):
                result = await result
            return set(result)

        pool = self._pool_getter()
        if pool is None:
            return set()

        current_time = monotonic()
        if current_time < self._cache_expires_at:
            return set(self._cached_dynamic_origins)

        async with self._refresh_lock:
            current_time = monotonic()
            if current_time < self._cache_expires_at:
                return set(self._cached_dynamic_origins)

            repository = ControlPlaneRepository(pool)
            allowed_origins = set(await repository.list_active_project_browser_key_origins())
            self._cached_dynamic_origins = allowed_origins
            self._cache_expires_at = monotonic() + self._cache_ttl_seconds
            return set(allowed_origins)
