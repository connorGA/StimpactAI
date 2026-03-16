from __future__ import annotations

import json
import logging
from typing import Any, Protocol, cast

from redis.asyncio import Redis

from api.core.config import (
    get_outbox_signal_block_ms,
    get_outbox_signal_maxlen,
    get_outbox_signal_stream,
    get_redis_url,
)

logger = logging.getLogger(__name__)


class OutboxSignalBus(Protocol):
    async def signal(self, *, event_id: str, event_type: str) -> None: ...
    async def wait_for_signal(self, *, last_id: str = "$", block_ms: int | None = None) -> list[dict[str, str]]: ...
    async def close(self) -> None: ...


class NullOutboxSignalBus:
    async def signal(self, *, event_id: str, event_type: str) -> None:
        logger.info(
            "Redis outbox signaling disabled; skipping signal",
            extra={"event_id": event_id, "event_type": event_type},
        )

    async def wait_for_signal(self, *, last_id: str = "$", block_ms: int | None = None) -> list[dict[str, str]]:
        _ = (last_id, block_ms)
        return []

    async def close(self) -> None:
        return None


class RedisOutboxSignalBus:
    def __init__(self, client: Redis) -> None:
        self._client = client
        self._stream = get_outbox_signal_stream()
        self._maxlen = get_outbox_signal_maxlen()

    async def signal(self, *, event_id: str, event_type: str) -> None:
        await self._client.xadd(
            self._stream,
            {
                "event_id": event_id,
                "event_type": event_type,
                "payload": json.dumps({"event_id": event_id, "event_type": event_type}, default=str),
            },
            maxlen=self._maxlen,
            approximate=True,
        )

    async def wait_for_signal(self, *, last_id: str = "$", block_ms: int | None = None) -> list[dict[str, str]]:
        effective_block_ms = block_ms or get_outbox_signal_block_ms()
        results = await self._client.xread(
            streams={self._stream: last_id},
            block=effective_block_ms,
            count=100,
        )

        messages: list[dict[str, str]] = []
        for _, entries in results:
            for message_id, payload in entries:
                normalized_payload = {str(key): str(value) for key, value in cast(dict[Any, Any], payload).items()}
                normalized_payload["stream_id"] = str(message_id)
                messages.append(normalized_payload)

        return messages

    async def close(self) -> None:
        await self._client.aclose()


def build_outbox_signal_bus() -> OutboxSignalBus:
    redis_url = get_redis_url()
    if not redis_url:
        logger.warning("REDIS_URL is not configured; Redis outbox signaling is disabled.")
        return NullOutboxSignalBus()

    return RedisOutboxSignalBus(Redis.from_url(redis_url, decode_responses=True))
