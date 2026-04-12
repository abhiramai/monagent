from datetime import datetime
from typing import Optional, Dict

from app.core.time_utils import now_utc
from sqlmodel import Field, SQLModel
from sqlalchemy import Column, JSON


class CheckResult(SQLModel, table=True):
    """The persistent unit for every probe result."""

    __tablename__ = "check_result"

    id: Optional[int] = Field(default=None, primary_key=True)
    service_name: str = Field(index=True)
    is_healthy: bool
    latency_ms: float
    timestamp: datetime = Field(default_factory=now_utc)
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    extra_info: Dict = Field(default_factory=dict, sa_column=Column(JSON))


class ServiceConfig(SQLModel, table=True):
    """Persistent configuration for a single probe instance."""

    __tablename__ = "service_config"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    target_url: str
    probe_type: str = Field(default="http")
    interval_seconds: int = Field(ge=1)
    timeout_seconds: int = Field(default=10, ge=1)
    alert_threshold: int = Field(default=0)
    last_seen: Optional[datetime] = Field(default=None)
