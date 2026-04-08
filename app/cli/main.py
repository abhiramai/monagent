import asyncio

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.db import get_engine, init_db
from app.core.engine import ProbeEngine
from app.models.check_result import ServiceConfig
from app.probes.http import HttpProbe
from app.probes.tcp import TcpProbe
from app.probes.heartbeat import HeartbeatProbe
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
    url: str = typer.Option(..., help="Health check URL or host:port for TCP"),
    type: str = typer.Option("http", help="Probe type: http or tcp"),
    interval: int = typer.Option(30, help="Check interval in seconds"),
    timeout: int = typer.Option(10, help="Request timeout in seconds"),
    alert_threshold: int = typer.Option(
        0, help="Consecutive failures before alert fires (0 = disabled)"
    ),
) -> None:
    """Register a new service to monitor."""
    init_db()

    if type not in ("http", "tcp", "heartbeat"):
        console.print(
            f"[bold red]Error:[/] Invalid type '{type}'. Must be 'http', 'tcp', or 'heartbeat'."
        )
        raise typer.Exit(1)

    config = ServiceConfig(
        name=name,
        target_url=url,
        probe_type=type,
        interval_seconds=interval,
        timeout_seconds=timeout,
        alert_threshold=alert_threshold,
    )

    with Session(get_engine()) as session:
        session.add(config)
        try:
            session.commit()
            session.refresh(config)
        except IntegrityError:
            session.rollback()
            console.print(
                f"[bold red]Error:[/] A service named '{name}' already exists."
            )
            raise typer.Exit(1)

    console.print(
        f"[green]OK[/green] Added '[bold cyan]{name}[/bold cyan]' ({type}) monitoring {url} (every {interval}s)"
    )


@app.command()
def delete(
    name: str = typer.Option(..., help="Service name to delete"),
) -> None:
    """Remove a service from monitoring."""
    init_db()

    with Session(get_engine()) as session:
        config = session.exec(
            select(ServiceConfig).where(ServiceConfig.name == name)
        ).first()

        if config is None:
            console.print(f"[bold red]Error:[/] No service named '{name}' found.")
            raise typer.Exit(1)

        if not typer.confirm(f"Are you sure you want to delete '{name}'?"):
            console.print("Aborted.")
            raise typer.Exit(0)

        session.delete(config)
        session.commit()

    console.print(f"[green]OK[/green] Deleted '[bold cyan]{name}[/bold cyan]'.")


@app.command()
def update(
    name: str = typer.Option(..., help="Service name to update"),
    url: str | None = typer.Option(None, help="New health check URL"),
    type: str | None = typer.Option(None, help="New probe type: http or tcp"),
    interval: int | None = typer.Option(None, help="New check interval in seconds"),
    timeout: int | None = typer.Option(None, help="New request timeout in seconds"),
    alert_threshold: int | None = typer.Option(
        None, help="Consecutive failures before alert fires (0 = disabled)"
    ),
) -> None:
    """Update an existing service's configuration."""
    init_db()

    if not any([url, type, interval, timeout, alert_threshold is not None]):
        console.print(
            "[bold red]Error:[/] Provide at least one field to update (--url, --type, --interval, --timeout, or --alert-threshold)."
        )
        raise typer.Exit(1)

    if type is not None and type not in ("http", "tcp"):
        console.print(
            f"[bold red]Error:[/] Invalid type '{type}'. Must be 'http' or 'tcp'."
        )
        raise typer.Exit(1)

    with Session(get_engine()) as session:
        config = session.exec(
            select(ServiceConfig).where(ServiceConfig.name == name)
        ).first()

        if config is None:
            console.print(f"[bold red]Error:[/] No service named '{name}' found.")
            raise typer.Exit(1)

        if url is not None:
            config.target_url = url
        if type is not None:
            config.probe_type = type
        if interval is not None:
            config.interval_seconds = interval
        if timeout is not None:
            config.timeout_seconds = timeout
        if alert_threshold is not None:
            config.alert_threshold = alert_threshold

        session.add(config)
        session.commit()

    console.print(f"[green]OK[/green] Updated '[bold cyan]{name}[/bold cyan]'.")


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
    table.add_column("Type", justify="center")
    table.add_column("Name", style="bold cyan")
    table.add_column("Target URL", style="green")
    table.add_column("Interval (s)", justify="right")
    table.add_column("Timeout (s)", justify="right")
    table.add_column("Alert Threshold", justify="right")

    for c in configs:
        alert_display = (
            str(c.alert_threshold) if c.alert_threshold > 0 else "[dim]disabled[/]"
        )
        table.add_row(
            str(c.id),
            c.probe_type.upper(),
            c.name,
            c.target_url,
            str(c.interval_seconds),
            str(c.timeout_seconds),
            alert_display,
        )

    console.print(table)


async def _run_with_tui(probes: list, services: list) -> None:
    from loguru import logger
    import uvicorn
    from app.api.webhook import app as webhook_app

    logger.remove()

    engine = ProbeEngine(probes=probes)
    dashboard = DashboardApp(engine=engine, services=services)

    config = uvicorn.Config(
        webhook_app,
        host="0.0.0.0",
        port=8000,
        log_level="warning",
        loop="asyncio",
        lifespan="off",
    )
    server = uvicorn.Server(config)

    tui_task = asyncio.create_task(dashboard.run_async())
    api_task = asyncio.create_task(server.serve())
    engine_task = asyncio.create_task(engine.start())

    # Wait for the TUI to exit, then gracefully shut down other tasks
    await tui_task

    logger.info("Shutdown triggered from TUI")
    server.should_exit = True
    await engine.stop()

    api_task.cancel()
    engine_task.cancel()
    try:
        await api_task
        await engine_task
    except asyncio.CancelledError:
        pass


@app.command()
def run() -> None:
    """Launch the Zenith Dashboard TUI and start monitoring."""
    init_db()

    with Session(get_engine()) as session:
        configs = session.exec(select(ServiceConfig)).all()

    if not configs:
        console.print(
            "[bold red]Error:[/] No services registered. Use [bold]monagent add[/bold] first."
        )
        raise typer.Exit(1)

    services = [
        {
            "type": c.probe_type,
            "name": c.name,
            "url": c.target_url,
            "alert_threshold": c.alert_threshold,
            "last_seen": c.last_seen,
        }
        for c in configs
    ]
    probes = []
    for c in configs:
        if c.probe_type == "http":
            probes.append(HttpProbe(config=c))
        elif c.probe_type == "tcp":
            probes.append(TcpProbe(config=c))
        elif c.probe_type == "heartbeat":
            probes.append(HeartbeatProbe(config=c))

    asyncio.run(_run_with_tui(probes, services))


if __name__ == "__main__":
    app()
