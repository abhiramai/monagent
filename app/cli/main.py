import asyncio
import threading
import os
from datetime import datetime, timezone

import typer
import uvicorn
from rich.console import Console
from rich.table import Table
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select, SQLModel

from app.api.webhook import app as webhook_app
from app.core.db import get_engine
from app.core.engine import ProbeEngine
from app.models.check_result import ServiceConfig
from app.probes.base import BaseProbe
from app.probes.heartbeat import HeartbeatProbe
from app.probes.http import HttpProbe
from app.probes.tcp import TcpProbe
from app.tui.dashboard import DashboardApp
from dotenv import load_dotenv

app = typer.Typer(
    name="monagent",
    help="monagent: High-Contrast Lab Monitor",
    add_completion=False,
)
console = Console()
load_dotenv()

API_KEY = os.environ.get("MONAGENT_API_KEY", "MA-HEART-BEAT")


@app.command()
def add(
    name: str = typer.Option(..., help="Service name (e.g. 'immich')"),
    url: str = typer.Option(
        ..., help="Health check URL or host:port for TCP/Heartbeat"
    ),
    type: str = typer.Option("http", help="Probe type: http, tcp, or heartbeat"),
    interval: int = typer.Option(30, help="Check interval in seconds"),
    timeout: int = typer.Option(10, help="Request timeout in seconds"),
    alert_threshold: int = typer.Option(
        0, help="Consecutive failures before alert fires (0 = disabled)"
    ),
) -> None:
    """Register a new service to monitor."""
    SQLModel.metadata.create_all(get_engine())
    if type not in ("http", "tcp", "heartbeat"):
        console.print(
            f"[bold red]Error:[/] Invalid type '{type}'. Must be http, tcp, or heartbeat."
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
    engine = get_engine()
    with Session(engine) as session:
        session.add(config)
        try:
            session.commit()
        except IntegrityError:
            console.print(
                f"[bold red]Error:[/] A service named '{name}' already exists."
            )
            raise typer.Exit(1)
    console.print(
        f"[green]+[/green] Added '[bold cyan]{name}[/bold cyan]' ({type}) monitoring {url}"
    )


@app.command()
def delete(name: str = typer.Option(..., help="Service name to delete")) -> None:
    """Remove a service from monitoring."""
    SQLModel.metadata.create_all(get_engine())
    engine = get_engine()
    with Session(engine) as session:
        config = session.exec(
            select(ServiceConfig).where(ServiceConfig.name == name)
        ).first()
        if not config:
            console.print(f"[bold red]Error:[/] No service named '{name}' found.")
            raise typer.Exit(1)
        if typer.confirm(f"Are you sure you want to delete '{name}'?"):
            session.delete(config)
            session.commit()
            console.print(f"[green]✓[/green] Deleted '[bold cyan]{name}[/bold cyan]'.")
        else:
            console.print("Aborted.")


@app.command()
def update(
    name: str = typer.Option(..., help="Service name to update"),
    url: str | None = typer.Option(None, help="New target URL"),
    interval: int | None = typer.Option(None, help="New interval seconds"),
    timeout: int | None = typer.Option(None, help="New timeout seconds"),
    type: str | None = typer.Option(None, help="New probe type: http, tcp, heartbeat"),
    alert_threshold: int | None = typer.Option(None, help="New alert threshold"),
) -> None:
    """Modify an existing service configuration."""
    SQLModel.metadata.create_all(get_engine())
    engine = get_engine()
    with Session(engine) as session:
        config = session.exec(
            select(ServiceConfig).where(ServiceConfig.name == name)
        ).first()
        if not config:
            console.print(f"[bold red]Error:[/] No service named '{name}' found.")
            raise typer.Exit(1)

        changed = False
        if url is not None:
            config.target_url = url
            changed = True
        if interval is not None:
            config.interval_seconds = interval
            changed = True
        if timeout is not None:
            config.timeout_seconds = timeout
            changed = True
        if type is not None:
            if type not in ("http", "tcp", "heartbeat"):
                console.print(
                    f"[bold red]Error:[/] Invalid type '{type}'. Must be http, tcp, or heartbeat."
                )
                raise typer.Exit(1)
            config.probe_type = type
            changed = True
        if alert_threshold is not None:
            config.alert_threshold = alert_threshold
            changed = True

        if not changed:
            console.print(
                "[yellow]No fields to update. Provide at least one option.[/]"
            )
            raise typer.Exit(0)

        session.add(config)
        session.commit()
        console.print(f"[green]✓[/green] Updated '[bold cyan]{name}[/bold cyan]'.")


@app.command("list")
def list_services() -> None:
    """Display all registered services in a formatted table."""
    SQLModel.metadata.create_all(get_engine())
    engine = get_engine()
    with Session(engine) as session:
        configs = session.exec(select(ServiceConfig)).all()
    if not configs:
        console.print(
            "[yellow]No services found. Add one with [bold]monagent add[/bold][/yellow]"
        )
        return
    table = Table(
        title="Monitored Services", border_style="blue", header_style="bold magenta"
    )
    table.add_column("Name", style="bold cyan")
    table.add_column("Type")
    table.add_column("Target")
    table.add_column("Client")
    table.add_column("Interval")
    table.add_column("Alerts")
    for c in configs:
        alert_display = (
            str(c.alert_threshold) if c.alert_threshold > 0 else "[dim]disabled[/]"
        )
        # Show client IP for heartbeat probes, target URL for others
        if c.probe_type == "heartbeat":
            target_display = c.client_ip or "[dim]N/A[/]"
        else:
            target_display = c.target_url
        table.add_row(
            c.name,
            c.probe_type.upper(),
            target_display,
            str(c.client_ip or ""),
            f"{c.interval_seconds}s",
            alert_display,
        )
    console.print(table)


@app.command("list-services")
def list_services_alias() -> None:
    """Alias for list command."""
    list_services()


# --- Application Runner Commands ---


async def _run_monagent(headless: bool) -> None:
    SQLModel.metadata.create_all(get_engine())

    probes = _get_probes()
    engine = ProbeEngine(probes=probes)

    # Setup API server
    api_config = uvicorn.Config(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        log_level="warning",
        loop="asyncio",
        lifespan="off",
    )
    api_server = uvicorn.Server(api_config)

    # Create tasks
    engine_task = asyncio.create_task(engine.start(), name="engine_task")
    api_task = asyncio.create_task(api_server.serve(), name="api_task")

    if headless:
        console.print(
            "[bold bright_cyan]>> Starting monagent HEADLESS (API + Engine)...[/]"
        )
        # Wait for engine and API to run indefinitely unless cancelled externally
        await asyncio.gather(engine_task, api_task)
    else:
        console.print(
            "[bold bright_cyan]📡 Starting monagent FULL (API + Engine + TUI)...[/]"
        )
        dashboard = DashboardApp()  # Dashboard fetches data dynamically
        tui_task = asyncio.create_task(dashboard.run_async(), name="tui_task")

        # Wait for the TUI to exit, then gracefully shut down other tasks
        await tui_task

        console.print(
            "Shutdown triggered from TUI, gracefully stopping other services..."
        )
        # Signal API server to stop
        api_server.should_exit = True
        await engine.stop()  # Stop the engine gracefully

        # Cancel other tasks and wait for them to finish
        for task in [api_task, engine_task]:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        console.print("[bold bright_cyan]✅ monagent services stopped.[/]")


@app.command()
def run(
    headless: bool = typer.Option(
        False, "--headless", help="Run engine & API without the TUI."
    ),
) -> None:
    """Launch the monagent engine, API, and/or TUI dashboard."""
    asyncio.run(_run_monagent(headless))


@app.command()
def dash() -> None:
    """Launch the TUI dashboard independently."""
    SQLModel.metadata.create_all(get_engine())
    asyncio.run(DashboardApp().run_async())


def _get_probes() -> list[BaseProbe]:
    engine = get_engine()
    with Session(engine) as session:
        configs = session.exec(select(ServiceConfig)).all()
    if not configs:
        console.print(
            "[bold red]Error:[/] No services registered. Use [bold]monagent add[/bold] first."
        )
        raise typer.Exit(1)
    probes: list[BaseProbe] = []
    for c in configs:
        if c.probe_type == "http":
            probes.append(HttpProbe(config=c))
        elif c.probe_type == "tcp":
            probes.append(TcpProbe(config=c))
        elif c.probe_type == "heartbeat":
            probes.append(HeartbeatProbe(config=c))
    return probes


if __name__ == "__main__":
    app()
