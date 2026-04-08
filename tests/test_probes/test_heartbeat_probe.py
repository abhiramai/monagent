import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.check_result import ServiceConfig
from app.probes.heartbeat import HeartbeatProbe


@pytest.fixture
def memory_db(tmp_path) -> object:
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def mock_engine(memory_db):
    with patch("app.probes.heartbeat.get_engine", return_value=memory_db):
        yield memory_db


@pytest.mark.asyncio
async def test_heartbeat_probe_healthy(mock_engine) -> None:
    """Verify the heartbeat probe returns healthy if last_seen is recent."""
    service_name = "test-heartbeat"
    config = ServiceConfig(
        name=service_name,
        target_url="heartbeat",
        probe_type="heartbeat",
        interval_seconds=60,
        last_seen=datetime.now(timezone.utc),
    )
    with Session(mock_engine) as session:
        session.add(config)
        session.commit()

    probe = HeartbeatProbe(config=config, service_name=service_name)
    is_healthy, status_code = await probe.perform_check(client=None)
    assert is_healthy is True


@pytest.mark.asyncio
async def test_heartbeat_probe_stale(mock_engine) -> None:
    """Verify the heartbeat probe returns unhealthy if last_seen is too old."""
    service_name = "test-heartbeat-stale"
    config = ServiceConfig(
        name=service_name,
        target_url="heartbeat",
        probe_type="heartbeat",
        interval_seconds=60,
        last_seen=datetime.now(timezone.utc) - timedelta(seconds=90),
    )
    with Session(mock_engine) as session:
        session.add(config)
        session.commit()

    probe = HeartbeatProbe(config=config, service_name=service_name)
    is_healthy, status_code = await probe.perform_check(client=None)
    assert is_healthy is False


@pytest.mark.asyncio
async def test_heartbeat_probe_never_seen(mock_engine) -> None:
    """Verify the heartbeat probe returns unhealthy if last_seen is None."""
    service_name = "test-heartbeat-never"
    config = ServiceConfig(
        name=service_name,
        target_url="heartbeat",
        probe_type="heartbeat",
        interval_seconds=60,
        last_seen=None,
    )
    with Session(mock_engine) as session:
        session.add(config)
        session.commit()

    probe = HeartbeatProbe(config=config, service_name=service_name)
    is_healthy, status_code = await probe.perform_check(client=None)
    assert is_healthy is False
