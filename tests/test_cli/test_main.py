import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import IntegrityError
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


def test_add_command_duplicate_name(memory_db: object) -> None:
    """Verify 'monagent add' shows a clean error for duplicate names."""
    with Session(memory_db) as session:
        session.add(
            ServiceConfig(
                name="existing-svc",
                target_url="http://localhost:8080",
                interval_seconds=30,
            )
        )
        session.commit()

    with patch("app.cli.main.get_engine", return_value=memory_db):
        result = runner.invoke(
            app,
            [
                "add",
                "--name",
                "existing-svc",
                "--url",
                "http://localhost:9999",
            ],
        )

    assert result.exit_code == 1
    assert "already exists" in result.stdout


def test_delete_command_removes_service(memory_db: object) -> None:
    """Verify 'monagent delete' removes a service after confirmation."""
    with Session(memory_db) as session:
        session.add(
            ServiceConfig(
                name="to-delete",
                target_url="http://localhost:8080",
                interval_seconds=30,
            )
        )
        session.commit()

    with patch("app.cli.main.get_engine", return_value=memory_db):
        result = runner.invoke(
            app,
            ["delete", "--name", "to-delete"],
            input="y\n",
        )

    assert result.exit_code == 0
    assert "Deleted" in result.stdout

    with Session(memory_db) as session:
        remaining = session.exec(select(ServiceConfig)).all()
        assert len(remaining) == 0


def test_delete_command_missing_service(memory_db: object) -> None:
    """Verify 'monagent delete' errors on non-existent service."""
    with patch("app.cli.main.get_engine", return_value=memory_db):
        result = runner.invoke(
            app,
            ["delete", "--name", "nonexistent"],
        )

    assert result.exit_code == 1
    assert "No service named" in result.stdout


def test_update_command_changes_url(memory_db: object) -> None:
    """Verify 'monagent update' modifies only the provided fields."""
    with Session(memory_db) as session:
        session.add(
            ServiceConfig(
                name="updatable",
                target_url="http://old-url:8080",
                interval_seconds=30,
                timeout_seconds=10,
            )
        )
        session.commit()

    with patch("app.cli.main.get_engine", return_value=memory_db):
        result = runner.invoke(
            app,
            ["update", "--name", "updatable", "--url", "http://new-url:9090"],
        )

    assert result.exit_code == 0
    assert "Updated" in result.stdout

    with Session(memory_db) as session:
        config = session.exec(
            select(ServiceConfig).where(ServiceConfig.name == "updatable")
        ).first()
        assert config is not None
        assert config.target_url == "http://new-url:9090"
        assert config.interval_seconds == 30  # Unchanged


def test_run_command_loads_and_starts_engine(memory_db: object) -> None:
    """Verify 'monagent run' loads configs and launches the TUI dashboard."""
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
        with patch("app.cli.main.DashboardApp.run_async", new_callable=AsyncMock):
            result = runner.invoke(app, ["run"])

    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_engine_single_loop_lifecycle(memory_db: object) -> None:
    """
    Prove that the engine runs start -> loop -> stop in ONE event loop,
    exiting cleanly without ValueError.
    """
    from app.core.engine import ProbeEngine
    from app.probes.base import BaseProbe
    import httpx

    class QuickProbe(BaseProbe):
        async def perform_check(
            self, client: httpx.AsyncClient
        ) -> tuple[bool, int | None]:
            return True, 200

    config = ServiceConfig(
        name="quick-test",
        target_url="http://localhost:8080",
        interval_seconds=1,
    )

    engine = ProbeEngine(probes=[QuickProbe(config=config)])

    async def _cancel_after_delay() -> None:
        await asyncio.sleep(3)
        await engine.stop()

    async def _run_engine() -> None:
        try:
            await engine.start()
        finally:
            await engine.stop()

    await asyncio.gather(
        _run_engine(),
        _cancel_after_delay(),
    )


def test_list_command_empty_database(memory_db: object) -> None:
    """Verify 'monagent list' handles an empty database gracefully."""
    with patch("app.cli.main.get_engine", return_value=memory_db):
        result = runner.invoke(app, ["list-services"])

    assert result.exit_code == 0
    assert "No services found" in result.stdout
    assert "monagent add" in result.stdout


def test_list_command_shows_services(memory_db: object) -> None:
    """Verify 'monagent list-services' displays services in a Rich table."""
    with Session(memory_db) as session:
        session.add_all(
            [
                ServiceConfig(
                    name="immich",
                    target_url="http://192.168.1.10:2283",
                    interval_seconds=30,
                ),
                ServiceConfig(
                    name="audiobookshelf",
                    target_url="http://192.168.1.10:13378",
                    interval_seconds=60,
                ),
            ]
        )
        session.commit()

    with patch("app.cli.main.get_engine", return_value=memory_db):
        result = runner.invoke(app, ["list-services"])

    assert result.exit_code == 0
    assert "Monitored Services" in result.stdout
    assert "immich" in result.stdout
    assert "audiobook" in result.stdout
    assert "HTTP" in result.stdout
    assert "http://" in result.stdout
