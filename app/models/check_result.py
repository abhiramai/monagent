from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CheckResult(BaseModel):
    """The atomic unit returned by every probe after execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    service_name: str
    is_healthy: bool
    latency_ms: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status_code: Optional[int] = None
    error_message: Optional[str] = None


class ServiceConfig(BaseModel):
    """Configuration for a single probe instance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    target_url: str
    interval_seconds: int = Field(ge=1)
    timeout_seconds: int = Field(default=10, ge=1)
