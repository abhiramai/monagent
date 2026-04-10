from datetime import datetime
import httpx
from sqlmodel import Session, select

from app.core.db import get_session
from app.core.time_utils import now_utc, to_aware
from app.models.check_result import CheckResult, ServiceConfig
from app.probes.base import BaseProbe


class HeartbeatProbe(BaseProbe):
    """A probe that checks for a 'last_seen' timestamp in the database."""

    def __init__(self, config: ServiceConfig) -> None:
        super().__init__(config)
        self.extra_info: dict = {}

    async def perform_check(self, client: httpx.AsyncClient) -> tuple[bool, None]:
        """Check the database for the last_seen timestamp and determine health."""
        with get_session() as session:
            db_config = session.get(ServiceConfig, self.config.id)

        if not db_config or not db_config.last_seen:
            self.extra_info = {"last_seen": None}
            return False, None

        # Update in-memory config and metadata
        self.config.last_seen = db_config.last_seen
        self.extra_info = {"last_seen": db_config.last_seen}

        # Perform the stale check using aware datetimes
        last_seen_aware = to_aware(db_config.last_seen)
        is_stale = (
            now_utc() - last_seen_aware
        ).total_seconds() > self.config.interval_seconds

        is_healthy = not is_stale
        return is_healthy, None

    async def run(self, client: httpx.AsyncClient | None = None) -> CheckResult:
        """Override the base run to inject metadata into the result."""
        # Perform the check and get the basic result from the parent run method
        result = await super().run(client)

        # Return a new CheckResult with the metadata included
        return result.model_copy(update={"extra_info": self.extra_info})
