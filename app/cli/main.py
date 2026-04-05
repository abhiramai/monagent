import asyncio

import typer
from sqlmodel import Session, select

from app.core.db import get_engine, init_db
from app.core.engine import ProbeEngine
from app.core.logger import logger
from app.models.check_result import ServiceConfig
from app.probes.http import HttpProbe

app = typer.Typer(
    name="monagent",
    help="A lightweight, headless, modular Python monitoring service.",
    add_completion=False,
)


@app.command()
def add(
    name: str = typer.Option(..., help="Service name (e.g. 'immich')"),
    url: str = typer.Option(..., help="Health check URL"),
    interval: int = typer.Option(30, help="Check interval in seconds"),
    timeout: int = typer.Option(10, help="Request timeout in seconds"),
) -> None:
    """Register a new service to monitor."""
    init_db()

    config = ServiceConfig(
        name=name,
        target_url=url,
        interval_seconds=interval,
        timeout_seconds=timeout,
    )

    with Session(get_engine()) as session:
        session.add(config)
        session.commit()
        session.refresh(config)

    logger.info(f"Added service '{name}' → {url} (every {interval}s)")
    typer.echo(f"Added '{name}' monitoring {url}")


@app.command()
def run() -> None:
    """Start the monitoring engine with all registered services."""
    init_db()

    with Session(get_engine()) as session:
        configs = session.exec(select(ServiceConfig)).all()

    if not configs:
        typer.echo("No services registered. Use 'monagent add' first.")
        raise typer.Exit(1)

    logger.info(f"Loaded {len(configs)} service(s) from database")

    probes = [HttpProbe(config=c) for c in configs]
    engine = ProbeEngine(probes=probes)

    try:
        asyncio.run(engine.start())
    except KeyboardInterrupt:
        asyncio.run(engine.stop())


if __name__ == "__main__":
    app()
