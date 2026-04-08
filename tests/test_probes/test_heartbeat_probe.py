import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.models.check_result import ServiceConfig
from app.probes.heartbeat import HeartbeatProbe


@pytest.mark.asyncio
async def test_heartbeat_probe_healthy() -> None:
    """Verify the heartbeat probe returns healthy if last_seen is recent."""
    config = ServiceConfig(
        name="test-heartbeat",
        target_url="heartbeat",
        probe_type="heartbeat",
        interval_seconds=60,
        last_seen=datetime.now(timezone.utc) - timedelta(seconds=30),
    )
    probe = HeartbeatProbe(config=config)
    is_healthy, status_code = await probe.perform_check(client=None)
    assert is_healthy is True
    assert status_code is None


@pytest.mark.asyncio
async def test_heartbeat_probe_stale() -> None:
    """Verify the heartbeat probe returns unhealthy if last_seen is too old."""
    config = ServiceConfig(
        name="test-heartbeat",
        target_url="heartbeat",
        probe_type="heartbeat",
        interval_seconds=60,
        last_seen=datetime.now(timezone.utc) - timedelta(seconds=90),
    )
    probe = HeartbeatProbe(config=config)
    is_healthy, status_code = await probe.perform_check(client=None)
    assert is_healthy is False
    assert status_code is None


@pytest.mark.asyncio
async def test_heartbeat_probe_never_seen() -> None:
    """Verify the heartbeat probe returns unhealthy if last_seen is None."""
    config = ServiceConfig(
        name="test-heartbeat",
        target_url="heartbeat",
        probe_type="heartbeat",
        interval_seconds=60,
        last_seen=None,
    )
    probe = HeartbeatProbe(config=config)
    is_healthy, status_code = await probe.perform_check(client=None)
    assert is_healthy is False
    assert status_code is None
