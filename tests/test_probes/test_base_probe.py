import pytest
from app.models.check_result import CheckResult, ServiceConfig
from app.probes.base import BaseProbe


class MockSuccessProbe(BaseProbe):
    async def perform_check(self) -> tuple[bool, int | None]:
        return True, 200


class MockFailProbe(BaseProbe):
    async def perform_check(self) -> tuple[bool, int | None]:
        return False, 500


class MockCrashProbe(BaseProbe):
    async def perform_check(self) -> tuple[bool, int | None]:
        raise ValueError("simulated probe crash")


@pytest.fixture
def success_config() -> ServiceConfig:
    return ServiceConfig(
        name="mock-success",
        target_url="http://localhost:8080",
        interval_seconds=30,
    )


@pytest.fixture
def fail_config() -> ServiceConfig:
    return ServiceConfig(
        name="mock-fail",
        target_url="http://localhost:9090",
        interval_seconds=30,
    )


@pytest.fixture
def crash_config() -> ServiceConfig:
    return ServiceConfig(
        name="mock-crash",
        target_url="http://localhost:1234",
        interval_seconds=30,
    )


@pytest.mark.asyncio
async def test_success_probe_returns_healthy(success_config: ServiceConfig) -> None:
    probe = MockSuccessProbe(config=success_config)
    result = await probe.run()

    assert isinstance(result, CheckResult)
    assert result.is_healthy is True
    assert result.status_code == 200
    assert result.latency_ms >= 0
    assert result.error_message is None


@pytest.mark.asyncio
async def test_fail_probe_returns_unhealthy(fail_config: ServiceConfig) -> None:
    probe = MockFailProbe(config=fail_config)
    result = await probe.run()

    assert isinstance(result, CheckResult)
    assert result.is_healthy is False
    assert result.status_code == 500
    assert result.latency_ms >= 0
    assert result.error_message is None


@pytest.mark.asyncio
async def test_crash_probe_is_caught_by_error_boundary(crash_config: ServiceConfig) -> None:
    probe = MockCrashProbe(config=crash_config)
    result = await probe.run()

    assert isinstance(result, CheckResult)
    assert result.is_healthy is False
    assert result.status_code is None
    assert result.latency_ms >= 0
    assert result.error_message is not None
    assert "ValueError" in result.error_message
    assert "simulated probe crash" in result.error_message
