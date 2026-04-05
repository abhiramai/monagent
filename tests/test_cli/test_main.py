import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.cli.main import app
from app.models.check_result import ServiceConfig
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def memory_db(tmp_path: Path) -> object:
    """Create an in-memory SQLite database and swap the DB_PATH."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    return engine


def test_add_command_creates_row(memory_db: object) -> None:
    """Verify 'monagent add' inserts a ServiceConfig into the database."""
    with patch("app.cli.main.get_engine", return_value=memory_db):
        result = runner.invoke(
            app,
            [
                "add",
                "--name",
                "test-svc",
                "--url",
                "http://localhost:9999/health",
                "--interval",
                "15",
            ],
        )

    assert result.exit_code == 0
    assert "test-svc" in result.stdout

    with Session(memory_db) as session:
        configs = session.exec(select(ServiceConfig)).all()
        assert len(configs) == 1
        assert configs[0].name == "test-svc"
        assert configs[0].target_url == "http://localhost:9999/health"
        assert configs[0].interval_seconds == 15


def test_run_command_loads_and_starts_engine(memory_db: object) -> None:
    """Verify 'monagent run' loads configs and calls engine.start()."""
    with Session(memory_db) as session:
        session.add(
            ServiceConfig(
                name="pre-seeded",
                target_url="http://localhost:8080",
                interval_seconds=30,
            )
        )
        session.commit()

    with patch("app.cli.main.get_engine", return_value=memory_db):
        with patch(
            "app.cli.main.ProbeEngine.start", new_callable=AsyncMock
        ) as mock_start:
            result = runner.invoke(app, ["run"])

    assert result.exit_code == 0
    mock_start.assert_called_once()
