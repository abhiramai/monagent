from pathlib import Path
import os
from typing import Generator
from contextlib import contextmanager

from loguru import logger
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

DB_PATH = Path(__file__).parent.parent.parent / "data" / "monagent.db"
DB_PATH = Path(os.path.abspath(DB_PATH))
DB_URL = f"sqlite:///{DB_PATH}"

_engine = create_engine(DB_URL, echo=False)


def get_engine() -> object:
    """Return the shared SQLAlchemy engine."""
    return _engine


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Context-managed session generator.
    Ensures every session is closed after use.
    """
    with Session(_engine) as session:
        yield session


def init_db() -> None:
    """Create all tables and apply any pending column migrations."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(_engine)

    # Auto-migrate: add missing columns to existing tables
    _migrate_columns()

    logger.info(f"Database initialized at {DB_PATH}")


def _migrate_columns() -> None:
    """
    Check for missing columns on the service_config table
    and add them via ALTER TABLE. Safe for existing databases.
    """
    migrations = [
        (
            "probe_type",
            "ALTER TABLE service_config ADD COLUMN probe_type VARCHAR DEFAULT 'http'",
        ),
        (
            "alert_threshold",
            "ALTER TABLE service_config ADD COLUMN alert_threshold INTEGER DEFAULT 0",
        ),
    ]

    with Session(_engine) as session:
        for col_name, alter_sql in migrations:
            try:
                session.exec(text(f"SELECT {col_name} FROM service_config LIMIT 1"))
            except Exception:
                logger.info(f"Migrating: adding column '{col_name}'")
                session.exec(text(alter_sql))
                session.commit()
