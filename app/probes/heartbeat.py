import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx
from loguru import logger

from app.probes.base import BaseProbe


class HeartbeatProbe(BaseProbe):
    """
    A "dead man's switch" probe. It doesn't make any network calls.
    It checks if a service has "checked in" by updating its `last_seen`
    timestamp. If `(Now - last_seen) > interval`, it's considered unhealthy.
    """

    async def perform_check(
        self, client: httpx.AsyncClient
    ) -> tuple[bool, Optional[int]]:
        """Check the age of the last_seen timestamp."""
        if self.config.last_seen is None:
            logger.warning(
                f"[{self.config.name}] Heartbeat probe has never received a check-in."
            )
            return False, None

        now = datetime.now(timezone.utc)
        time_since_last_seen = now - self.config.last_seen
        is_stale = time_since_last_seen.total_seconds() > self.config.interval_seconds

        if is_stale:
            logger.warning(
                f"[{self.config.name}] Heartbeat is stale. Last seen "
                f"{time_since_last_seen.total_seconds():.0f}s ago."
            )
            return False, None

        return True, None
