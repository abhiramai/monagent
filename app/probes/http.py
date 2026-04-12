from typing import Optional

import httpx
from loguru import logger

from app.probes.base import BaseProbe


class HttpProbe(BaseProbe):
    """
    HTTP health check probe.
    Performs a GET request against the configured address
    and returns health status with the HTTP status code.
    """

    async def perform_check(
        self, client: httpx.AsyncClient
    ) -> tuple[bool, Optional[int]]:
        try:
            response = await client.get(self.config.address)
            return response.is_success, response.status_code
        except httpx.ConnectTimeout:
            logger.warning(
                f"[{self.config.name}] Connection timed out "
                f"after {self.config.timeout_seconds}s"
            )
            return False, None
        except httpx.ConnectError as e:
            logger.warning(f"[{self.config.name}] Connection failed: {e}")
            return False, None
        except httpx.HTTPStatusError as e:
            logger.warning(f"[{self.config.name}] HTTP error {e.response.status_code}")
            return False, e.response.status_code
