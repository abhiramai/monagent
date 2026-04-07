import asyncio
from collections import deque
from typing import Callable, Optional, Sequence

import httpx
from loguru import logger

from app.core.alerts import AlertManager
from app.models.check_result import CheckResult
from app.probes.base import BaseProbe

ResultCallback = Callable[[CheckResult, bool], None]


class ProbeEngine:
    """
    The async orchestration layer. Runs each probe on its own heartbeat loop
    concurrently, using a single shared httpx.AsyncClient for connection pooling.
    """

    def __init__(
        self,
        probes: Sequence[BaseProbe],
        result_callback: Optional[ResultCallback] = None,
    ) -> None:
        self._probes = probes
        self._result_callback = result_callback
        self._tasks: list[asyncio.Task[None]] = []
        self._client: Optional[httpx.AsyncClient] = None
        self._log_buffer: deque[str] = deque(maxlen=5)
        self._failure_counts: dict[str, int] = {}
        self._alerted_state: dict[str, bool] = {}
        self._alert_manager = AlertManager()

    @property
    def log_buffer(self) -> list[str]:
        return list(self._log_buffer)

    def get_alerted_state(self, service_name: str) -> bool:
        """Check if a service currently has an active alert."""
        return self._alerted_state.get(service_name, False)

    async def start(self) -> None:
        """
        Initialize the master httpx client, spawn a background task for
        every probe, and run them all concurrently until cancelled.
        """
        logger.info(f"ProbeEngine starting with {len(self._probes)} probe(s)")

        self._client = httpx.AsyncClient(follow_redirects=True)
        self._tasks = [
            asyncio.create_task(self._run_probe(probe), name=probe.config.name)
            for probe in self._probes
        ]

        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self) -> None:
        """Cancel all running probe tasks and close the master client."""
        logger.info("ProbeEngine shutting down")
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _run_probe(self, probe: BaseProbe) -> None:
        """
        Independent heartbeat loop for a single probe.
        Crashes are caught and logged so other probes continue running.
        """
        assert self._client is not None
        logger.info(
            f"Scheduling probe '{probe.config.name}' "
            f"every {probe.config.interval_seconds}s"
        )

        self._failure_counts[probe.config.name] = 0
        self._alerted_state[probe.config.name] = False

        while True:
            try:
                result = await probe.run(client=self._client)
                await self._on_result(result, probe.config.alert_threshold)
            except asyncio.CancelledError:
                logger.info(f"Probe '{probe.config.name}' cancelled")
                raise
            except Exception:
                logger.exception(
                    f"Probe '{probe.config.name}' loop crashed — restarting in "
                    f"{probe.config.interval_seconds}s"
                )

            await asyncio.sleep(probe.config.interval_seconds)

    async def _on_result(self, result: CheckResult, alert_threshold: int) -> None:
        """Emit result to logger, manage alert state, and send notifications."""
        status = "HEALTHY" if result.is_healthy else "UNHEALTHY"
        log_line = (
            f"[{result.service_name}] {status} | "
            f"latency={result.latency_ms}ms | "
            f"code={result.status_code} | "
            f"error={result.error_message}"
        )
        logger.info(log_line)
        self._log_buffer.append(log_line)

        # Alert state machine (only if threshold > 0)
        service = result.service_name
        if alert_threshold > 0:
            if not result.is_healthy:
                self._failure_counts[service] = self._failure_counts.get(service, 0) + 1
                if self._failure_counts[
                    service
                ] == alert_threshold and not self._alerted_state.get(service, False):
                    self._alerted_state[service] = True
                    logger.warning(
                        f"🚨 ALERT TRIGGERED: '{service}' failed "
                        f"{alert_threshold} consecutive checks"
                    )
                    # Fire notification in background — don't block the engine
                    asyncio.create_task(
                        self._alert_manager.send_notification(
                            title=f"🔴 DOWN: {service}",
                            body=f"{service} is unreachable at {result.service_name}. "
                            f"Error: {result.error_message or 'Unknown'}",
                        )
                    )
            else:
                if self._alerted_state.get(service, False):
                    self._alerted_state[service] = False
                    logger.info(f"✅ RECOVERED: '{service}' is healthy again")
                    # Fire recovery notification in background
                    asyncio.create_task(
                        self._alert_manager.send_notification(
                            title=f"🟢 RECOVERED: {service}",
                            body=f"{service} is back online. "
                            f"Latency: {result.latency_ms}ms",
                        )
                    )
                self._failure_counts[service] = 0

        is_alerted = self._alerted_state.get(service, False)

        if self._result_callback is not None:
            self._result_callback(result, is_alerted)
