from sqlmodel import Session, SQLModel, create_engine

from app.models.check_result import ServiceConfig


def _make_memory_engine() -> object:
    """Create an in-memory SQLite engine for isolated tests."""
    return create_engine("sqlite:///:memory:")


def test_save_and_retrieve_service_config() -> None:
    """
    Prove that a ServiceConfig can be persisted to an in-memory
    SQLite database and retrieved with all fields intact.
    """
    engine = _make_memory_engine()
    SQLModel.metadata.create_all(engine)

    config = ServiceConfig(
        name="test-service",
        target_url="http://localhost:8080/health",
        interval_seconds=30,
        timeout_seconds=15,
    )

    with Session(engine) as session:
        session.add(config)
        session.commit()
        session.refresh(config)

        assert config.id is not None
        assert config.name == "test-service"
        assert config.target_url == "http://localhost:8080/health"
        assert config.interval_seconds == 30
        assert config.timeout_seconds == 15

    with Session(engine) as session:
        retrieved = session.get(ServiceConfig, config.id)
        assert retrieved is not None
        assert retrieved.name == "test-service"
        assert retrieved.target_url == "http://localhost:8080/health"
        assert retrieved.interval_seconds == 30
        assert retrieved.timeout_seconds == 15
