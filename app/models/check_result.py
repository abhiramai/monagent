from datetime import datetime
from typing import Optional, Dict

from app.core.time_utils import now_utc

from sqlmodel import Field, SQLModel
from sqlalchemy import Column, JSON


class CheckResult(SQLModel, table=True):
    """The persistent unit for every probe result, now saved to DB."""

    __tablename__ = "check_result"

    id: Optional[int] = Field(default=None, primary_key=True)
    service_name: str = Field(index=True)  # Linked to ServiceConfig.name
    is_healthy: bool
    latency_ms: float
    timestamp: datetime = Field(default_factory=now_utc)
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    # SQLite doesn't have a 'dict' type, so we use SQLAlchemy's JSON type
    extra_info: Dict = Field(default_factory=dict, sa_column=Column(JSON))


class ServiceConfig(SQLModel, table=True):
    """
    Persistent configuration for a single probe instance.
    Stored in SQLite and loaded by the engine at startup.
    """

    __tablename__ = "service_config"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    target_url: str
    probe_type: str = Field(default="http")
    interval_seconds: int = Field(ge=1)
    timeout_seconds: int = Field(default=10, ge=1)
    alert_threshold: int = Field(default=0)
    last_seen: Optional[datetime] = Field(default=None)
