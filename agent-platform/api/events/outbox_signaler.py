from __future__ import annotations

import logging

from api.events.redis_bus import OutboxSignalBus

logger = logging.getLogger(__name__)


class OutboxSignaler:
    def __init__(self, signal_bus: OutboxSignalBus) -> None:
        self._signal_bus = signal_bus

    async def signal(self, *, event_id: str, event_type: str) -> None:
        try:
            await self._signal_bus.signal(event_id=event_id, event_type=event_type)
        except Exception:
            # The outbox is still the source of truth, so signaling failures should not invalidate ingestion.
            logger.exception(
                "Failed to publish Redis outbox wake-up signal",
                extra={"event_id": event_id, "event_type": event_type},
            )
