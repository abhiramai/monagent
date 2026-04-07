import asyncio
from typing import Optional

from loguru import logger

from app.probes.base import BaseProbe


class TcpProbe(BaseProbe):
    """
    TCP port connectivity probe.
    Uses raw asyncio sockets to verify if a host:port is listening
    without the overhead of a full HTTP request.
    """

    async def perform_check(self, client: object) -> tuple[bool, Optional[int]]:
        target = self.config.target_url

        if "://" in target:
            target = target.split("://", 1)[1]

        if ":" in target:
            host, port_str = target.rsplit(":", 1)
            port = int(port_str)
        else:
            host = target
            port = 22

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=self.config.timeout_seconds,
            )
            writer.close()
            await writer.wait_closed()
            return True, None
        except asyncio.TimeoutError:
            logger.warning(
                f"[{self.config.name}] TCP connection timed out "
                f"after {self.config.timeout_seconds}s on {host}:{port}"
            )
            return False, None
        except ConnectionRefusedError:
            logger.warning(
                f"[{self.config.name}] TCP connection refused on {host}:{port}"
            )
            return False, None
        except OSError as e:
            logger.warning(
                f"[{self.config.name}] TCP connection failed on {host}:{port}: {e}"
            )
            return False, None
