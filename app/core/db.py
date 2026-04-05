from pathlib import Path
from typing import Generator

from loguru import logger
from sqlmodel import Session, SQLModel, create_engine

DB_PATH = Path("data") / "monagent.db"
DB_URL = f"sqlite:///{DB_PATH}"

_engine = create_engine(DB_URL, echo=False)


def get_engine() -> object:
    """Return the shared SQLAlchemy engine."""
    return _engine


def get_session() -> Generator[Session, None, None]:
    """
    Context-managed session generator.
    Ensures every session is closed after use.
    """
    with Session(_engine) as session:
        yield session


def init_db() -> None:
    """Create all tables and log success."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(_engine)
    logger.info(f"Database initialized at {DB_PATH}")
