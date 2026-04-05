import asyncio

import typer
from rich.console import Console
from rich.table import Table
from sqlmodel import Session, select

from app.core.db import get_engine, init_db
from app.core.engine import ProbeEngine
from app.core.logger import logger
from app.models.check_result import ServiceConfig
from app.probes.http import HttpProbe
from app.tui.dashboard import DashboardApp

app = typer.Typer(
    name="monagent",
    help="A lightweight, headless, modular Python monitoring service.",
    add_completion=False,
)

console = Console()


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


async def _run_app(engine: ProbeEngine) -> None:
    """Run the engine lifecycle in a single event loop."""
    try:
        await engine.start()
    finally:
        await engine.stop()


@app.command()
def list_services() -> None:
    """Display all registered services in a formatted table."""
    init_db()

    with Session(get_engine()) as session:
        configs = session.exec(select(ServiceConfig)).all()

    if not configs:
        console.print(
            "[yellow]No services found.[/yellow] Add one with [bold]monagent add[/bold]"
        )
        return

    table = Table(
        title="Monitored Services",
        border_style="blue",
        show_header=True,
        header_style="bold magenta",
    )

    table.add_column("ID", justify="right", style="dim")
    table.add_column("Name", style="bold cyan")
    table.add_column("Target URL", style="green")
    table.add_column("Interval (s)", justify="right")
    table.add_column("Timeout (s)", justify="right")

    for c in configs:
        table.add_row(
            str(c.id),
            c.name,
            c.target_url,
            str(c.interval_seconds),
            str(c.timeout_seconds),
        )

    console.print(table)


@app.command()
def run() -> None:
    """Launch the Zenith Dashboard TUI and start monitoring."""
    init_db()

    with Session(get_engine()) as session:
        configs = session.exec(select(ServiceConfig)).all()

    if not configs:
        typer.echo("No services registered. Use 'monagent add' first.")
        raise typer.Exit(1)

    logger.info(f"Loaded {len(configs)} service(s) from database")

    service_names = [c.name for c in configs]
    probes = [HttpProbe(config=c) for c in configs]

    async def _run_with_tui() -> None:
        engine = ProbeEngine(probes=probes)

        async def _start_engine() -> None:
            try:
                await engine.start()
            finally:
                await engine.stop()

        dashboard = DashboardApp(
            engine=engine,
            service_names=service_names,
        )

        engine_task = asyncio.create_task(_start_engine())
        await dashboard.run_async()
        engine_task.cancel()
        try:
            await engine_task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run_with_tui())


if __name__ == "__main__":
    app()
