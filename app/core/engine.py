import asyncio
from typing import Sequence

from loguru import logger

from app.models.check_result import CheckResult
from app.probes.base import BaseProbe


class ProbeEngine:
    """
    The async orchest layer. Runs each probe on its own heartbeat loop
    concurrently, ensuring no single probe blocks another.
    """

    def __init__(self, probes: Sequence[BaseProbe]) -> None:
        self._probes = probes
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        """
        Spawn a background task for every probe and run them all concurrently.
        The engine will run until cancelled.
        """
        logger.info(f"ProbeEngine starting with {len(self._probes)} probe(s)")

        self._tasks = [
            asyncio.create_task(self._run_probe(probe), name=probe.config.name)
            for probe in self._probes
        ]

        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self) -> None:
        """Cancel all running probe tasks gracefully."""
        logger.info("ProbeEngine shutting down")
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _run_probe(self, probe: BaseProbe) -> None:
        """
        Independent heartbeat loop for a single probe.
        Crashes are caught and logged so other probes continue running.
        """
        logger.info(
            f"Scheduling probe '{probe.config.name}' "
            f"every {probe.config.interval_seconds}s"
        )

        while True:
            try:
                result = await probe.run()
                self._log_result(result)
            except asyncio.CancelledError:
                logger.info(f"Probe '{probe.config.name}' cancelled")
                raise
            except Exception:
                logger.exception(
                    f"Probe '{probe.config.name}' loop crashed — restarting in "
                    f"{probe.config.interval_seconds}s"
                )

            await asyncio.sleep(probe.config.interval_seconds)

    @staticmethod
    def _log_result(result: CheckResult) -> None:
        """Emit a structured summary for every probe execution."""
        status = "HEALTHY" if result.is_healthy else "UNHEALTHY"
        logger.info(
            f"[{result.service_name}] {status} | "
            f"latency={result.latency_ms}ms | "
            f"code={result.status_code} | "
            f"error={result.error_message}"
        )
