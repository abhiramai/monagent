import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx
from loguru import logger
from sqlmodel import Session, select

from app.core.db import get_engine
from app.models.check_result import ServiceConfig
from app.probes.base import BaseProbe


class HeartbeatProbe(BaseProbe):
    """
    A "dead man's switch" probe. It doesn't make any network calls.
    It checks if a service has "checked in" by updating its `last_seen`
    timestamp. If `(Now - last_seen) > interval`, it's considered unhealthy.
    """

    def __init__(
        self, config: ServiceConfig, service_name: Optional[str] = None
    ) -> None:
        super().__init__(config)
        self._service_name = service_name or config.name

    async def perform_check(
        self, client: httpx.AsyncClient
    ) -> tuple[bool, Optional[int]]:
        """Check the age of the last_seen timestamp from the database."""
        with Session(get_engine()) as session:
            config = session.exec(
                select(ServiceConfig).where(ServiceConfig.name == self._service_name)
            ).first()

            if config is None or config.last_seen is None:
                logger.warning(
                    f"[{self._service_name}] Heartbeat probe has never received a check-in."
                )
                return False, None

            self.config.last_seen = config.last_seen
            self.config.interval_seconds = config.interval_seconds
            self.config.alert_threshold = config.alert_threshold

            self._last_seen_metadata = {"last_seen": config.last_seen}

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            time_since_last_seen = now - config.last_seen.replace(tzinfo=None)
            is_stale = time_since_last_seen.total_seconds() > config.interval_seconds

            if is_stale:
                logger.warning(
                    f"[{self._service_name}] Heartbeat is stale. Last seen "
                    f"{time_since_last_seen.total_seconds():.0f}s ago."
                )
                return False, None

            return True, None

    @property
    def alert_threshold(self) -> int:
        """Fetch alert_threshold from DB for alert state machine."""
        with Session(get_engine()) as session:
            config = session.exec(
                select(ServiceConfig).where(ServiceConfig.name == self._service_name)
            ).first()
            return config.alert_threshold if config else 0
