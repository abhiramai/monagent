from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from app.models.check_result import ServiceConfig
from app.probes.http import HttpProbe


@pytest.fixture
def http_config() -> ServiceConfig:
    return ServiceConfig(
        name="test-http",
        target_url="http://localhost:8080/health",
        interval_seconds=30,
        timeout_seconds=10,
    )


@pytest.mark.asyncio
@respx.mock
async def test_http_probe_success_200(http_config: ServiceConfig) -> None:
    respx.get("http://localhost:8080/health").mock(return_value=httpx.Response(200))

    probe = HttpProbe(config=http_config)
    result = await probe.run()

    assert result.is_healthy is True
    assert result.status_code == 200
    assert result.error_message is None


@pytest.mark.asyncio
@respx.mock
async def test_http_probe_404_is_unhealthy(http_config: ServiceConfig) -> None:
    respx.get("http://localhost:8080/health").mock(return_value=httpx.Response(404))

    probe = HttpProbe(config=http_config)
    result = await probe.run()

    assert result.is_healthy is False
    assert result.status_code == 404
    assert result.error_message is None


@pytest.mark.asyncio
async def test_http_probe_timeout_returns_unhealthy(http_config: ServiceConfig) -> None:
    """Simulate a hanging server by mocking AsyncClient.get to raise ConnectTimeout."""
    probe = HttpProbe(config=http_config)

    async def _fake_get(*_args: object, **_kwargs: object) -> None:
        raise httpx.ConnectTimeout("Connection timed out")

    with patch.object(httpx.AsyncClient, "get", new=_fake_get):
        result = await probe.run()

    assert result.is_healthy is False
    assert result.status_code is None
    assert "timed out" in result.error_message.lower() if result.error_message else True
