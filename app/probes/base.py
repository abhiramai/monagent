from abc import ABC, abstractmethod
import time
from typing import Optional

import httpx
from loguru import logger

from app.models.check_result import CheckResult, ServiceConfig


class BaseProbe(ABC):
    """
    The 'Interface' for all monagent checks.
    Enforces ODD (timing/logging) and TDD (abstract contracts).
    """

    def __init__(self, config: ServiceConfig) -> None:
        self.config = config

    @abstractmethod
    async def perform_check(
        self, client: httpx.AsyncClient
    ) -> tuple[bool, Optional[int]]:
        """
        The specific logic for each probe.
        Receives a shared httpx.AsyncClient from the engine for connection pooling.
        Returns: (is_healthy, status_code)
        """
        ...

    async def run(self, client: Optional[httpx.AsyncClient] = None) -> CheckResult:
        """
        The ODD wrapper. This ensures EVERY probe is timed and logged
        without the developer having to do it manually.
        """
        logger.info(f"Running probe: {self.config.name} on {self.config.target_url}")

        start_time = time.perf_counter()
        error_msg: Optional[str] = None
        status_code: Optional[int] = None

        try:
            if client is None:
                client = httpx.AsyncClient(timeout=self.config.timeout_seconds)
                is_healthy, status_code = await self.perform_check(client)
                await client.aclose()
            else:
                is_healthy, status_code = await self.perform_check(client)
        except Exception as e:
            logger.exception(f"Unhandled exception in {self.config.name} probe")
            is_healthy = False
            error_msg = f"Unhandled {type(e).__name__}: {e}"

        end_time = time.perf_counter()
        latency = (end_time - start_time) * 1000

        return CheckResult(
            service_name=self.config.name,
            is_healthy=is_healthy,
            latency_ms=round(latency, 2),
            status_code=status_code,
            error_message=error_msg,
        )
