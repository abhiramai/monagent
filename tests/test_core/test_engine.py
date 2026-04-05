import asyncio

import httpx
import pytest

from app.core.engine import ProbeEngine
from app.models.check_result import ServiceConfig
from app.probes.base import BaseProbe


class MockSuccessProbe(BaseProbe):
    async def perform_check(self, client: httpx.AsyncClient) -> tuple[bool, int | None]:
        return True, 200


class MockFailProbe(BaseProbe):
    async def perform_check(self, client: httpx.AsyncClient) -> tuple[bool, int | None]:
        return False, 500


@pytest.mark.asyncio
async def test_engine_runs_probes_concurrently() -> None:
    """
    Prove the engine can run two probes concurrently for 5 seconds
    without crashing. Each probe fires on a 1-second heartbeat.
    """
    success_config = ServiceConfig(
        name="engine-success",
        target_url="http://localhost:8080",
        interval_seconds=1,
    )

    fail_config = ServiceConfig(
        name="engine-fail",
        target_url="http://localhost:9090",
        interval_seconds=1,
    )

    engine = ProbeEngine(
        probes=[
            MockSuccessProbe(config=success_config),
            MockFailProbe(config=fail_config),
        ],
    )

    task = asyncio.create_task(engine.start())

    # Let the engine run for 5 seconds — both probes should execute multiple times
    await asyncio.sleep(5)

    await engine.stop()
    await task
