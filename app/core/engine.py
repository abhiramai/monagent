import asyncio
from datetime import datetime, timezone
from collections import deque
from typing import Callable, Optional, Sequence, Any, Dict

import httpx
from loguru import logger

from app.core.alerts import AlertManager
from app.core.db import get_session
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

    def sync_probes(self, configs: Sequence[object]) -> None:
        """
        Compare the current probes with the given configs and add any new ones.
        Also updates existing probes if their config changed (e.g., alert_threshold).
        """
        new_probes = []
        current_probe_names = {p.config.name for p in self._probes}
        config_map = {c.name: c for c in configs}

        for config in configs:
            if config.name not in current_probe_names:
                logger.info(f"Discovered new service: '{config.name}'")
                new_probe = self._create_probe(config)
                new_probes.append(new_probe)
                self._probes.append(new_probe)
            else:
                existing = next(
                    (p for p in self._probes if p.config.name == config.name), None
                )
                if (
                    existing
                    and existing.config.alert_threshold != config.alert_threshold
                ):
                    logger.info(
                        f"Updating alert_threshold for '{config.name}' "
                        f"from {existing.config.alert_threshold} to {config.alert_threshold}"
                    )
                    existing.config.alert_threshold = config.alert_threshold

        if new_probes:
            self._tasks.extend(
                [
                    asyncio.create_task(self._run_probe(probe), name=probe.config.name)
                    for probe in new_probes
                ]
            )
            if self._result_callback:
                from app.models.check_result import CheckResult

                self._result_callback(
                    CheckResult(
                        service_name="__sync__",
                        is_healthy=True,
                        latency_ms=0,
                        timestamp=datetime.now(timezone.utc),
                    ),
                    False,
                )

    def _create_probe(self, config: object) -> BaseProbe:
        from app.probes.http import HttpProbe
        from app.probes.tcp import TcpProbe
        from app.probes.heartbeat import HeartbeatProbe

        if config.probe_type == "http":
            return HttpProbe(config=config)
        elif config.probe_type == "tcp":
            return TcpProbe(config=config)
        elif config.probe_type == "heartbeat":
            return HeartbeatProbe(config=config)
        else:
            raise ValueError(f"Unknown probe type: {config.probe_type}")

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
        self._tasks.append(asyncio.create_task(self._sync_loop(), name="_sync_loop"))

        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _sync_loop(self) -> None:
        from app.core.db import get_engine
        from app.models.check_result import ServiceConfig
        from sqlmodel import Session, select

        while True:
            await asyncio.sleep(2)
            with Session(get_engine()) as session:
                configs = session.exec(select(ServiceConfig)).all()
            self.sync_probes(configs)

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
                threshold = getattr(probe, "alert_threshold", None)
                if threshold is not None and callable(threshold):
                    threshold = threshold()
                elif threshold is None:
                    threshold = probe.config.alert_threshold
                await self._on_result(result, threshold)
            except asyncio.CancelledError:
                logger.info(f"Probe '{probe.config.name}' cancelled")
                raise
            except Exception:
                logger.exception(
                    f"Probe '{probe.config.name}' loop crashed — restarting in "
                    f"{probe.config.interval_seconds}s"
                )

            await asyncio.sleep(probe.config.interval_seconds)

    def _sanitize_extra_info(self, extra_info: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitize extra_info to ensure JSON serializability for SQLite."""
        if not isinstance(extra_info, dict):
            return extra_info

        sanitized = {}
        for key, value in extra_info.items():
            if isinstance(value, datetime):
                # Convert datetime to ISO format string for JSON storage
                sanitized[key] = value.isoformat()
            elif isinstance(value, dict):
                # Recursively sanitize nested dictionaries
                sanitized[key] = self._sanitize_extra_info(value)
            elif isinstance(value, list):
                # Handle lists that might contain datetimes
                sanitized[key] = [
                    self._sanitize_extra_info(item)
                    if isinstance(item, dict)
                    else item.isoformat()
                    if isinstance(item, datetime)
                    else item
                    for item in value
                ]
            else:
                # Keep other values as-is (str, int, float, bool, None)
                sanitized[key] = value
        return sanitized

    async def _on_result(self, result: CheckResult, alert_threshold: int) -> None:
        """Emit result to logger, manage alert state, and send notifications."""
        # SNAPSHOT AND TYPE-CAST VALUES IMMEDIATELY (Avoids DetachedInstanceError and NULLs)
        raw_name = result.service_name
        name = str(raw_name) if raw_name not in (None, "") else "unknown-service"
        healthy = bool(result.is_healthy)
        latency = float(result.latency_ms) if result.latency_ms is not None else 0.0
        # status_code can be None if column allows; we keep as-is
        code = result.status_code
        error_msg = (
            str(result.error_message) if result.error_message is not None else None
        )
        extra_info = dict(result.extra_info) if result.extra_info else {}

        # Log the sanitized values for debugging
        logger.debug(
            f"Sanitized fields: service_name={name!r}, is_healthy={healthy!r}, latency_ms={latency!r}, status_code={code!r}, error_message={error_msg!r}"
        )

        try:
            status = "HEALTHY" if healthy else "UNHEALTHY"
            log_line = (
                f"[{name}] {status} | "
                f"latency={latency}ms | "
                f"code={code} | "
                f"error={error_msg}"
            )
            logger.info(log_line)
            self._log_buffer.append(log_line)

            # Alert state machine (using local snapshots)
            service = name
            if alert_threshold > 0:
                if not healthy:
                    self._failure_counts[service] = (
                        self._failure_counts.get(service, 0) + 1
                    )
                    if self._failure_counts[
                        service
                    ] == alert_threshold and not self._alerted_state.get(
                        service, False
                    ):
                        self._alerted_state[service] = True
                        logger.warning(
                            f"🚨 ALERT TRIGGERED: '{service}' failed "
                            f"{alert_threshold} consecutive checks"
                        )
                        asyncio.create_task(
                            self._alert_manager.send_notification(
                                title=f"🔴 DOWN: {service}",
                                body=f"{service} is unreachable. Error: {error_msg or 'Unknown'}",
                            )
                        )
                else:
                    if self._alerted_state.get(service, False):
                        self._alerted_state[service] = False
                        logger.info(f"✅ RECOVERED: '{service}' is healthy again")
                        asyncio.create_task(
                            self._alert_manager.send_notification(
                                title=f"🟢 RECOVERED: {service}",
                                body=f"{service} is back online. Latency: {latency}ms",
                            )
                        )
                    self._failure_counts[service] = 0

            is_alerted = self._alerted_state.get(service, False)

            if self._result_callback is not None:
                # Rebuild CheckResult from local snapshots for the callback
                callback_result = CheckResult(
                    service_name=name,
                    is_healthy=healthy,
                    latency_ms=latency,
                    status_code=code,
                    error_message=error_msg,
                    extra_info=extra_info,
                )
                self._result_callback(callback_result, is_alerted)

            # Fresh Instance Pattern: create a new CheckResult for DB storage
            with get_session() as session:
                # Sanitize extra_info to ensure JSON serializability (convert datetimes to ISO strings)
                sanitized_extra_info = self._sanitize_extra_info(extra_info)
                db_record = CheckResult(
                    service_name=name,
                    is_healthy=healthy,
                    latency_ms=latency,
                    status_code=code,
                    error_message=error_msg,
                    extra_info=sanitized_extra_info,
                )
                session.add(db_record)
                session.commit()
                # Do not touch db_record after commit

        except Exception as e:
            # Error resilience: log but do not re-raise to keep other probes running
            logger.error(f"Failed to store result for service '{name}': {e}")
