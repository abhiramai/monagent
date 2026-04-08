from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel


class CheckResult(BaseModel):
    """The atomic unit returned by every probe after execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    service_name: str
    is_healthy: bool
    latency_ms: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status_code: Optional[int] = None
    error_message: Optional[str] = None


class ServiceConfig(SQLModel, table=True):
    """
    Persistent configuration for a single probe instance.
    Stored in SQLite and loaded by the engine at startup.
    """

    __tablename__ = "service_config"

    id: Optional[int] = SQLField(default=None, primary_key=True)
    name: str = SQLField(index=True, unique=True)
    target_url: str
    probe_type: str = SQLField(default="http")
    interval_seconds: int = SQLField(ge=1)
    timeout_seconds: int = SQLField(default=10, ge=1)
    alert_threshold: int = SQLField(default=0)
    last_seen: Optional[datetime] = SQLField(default=None)
