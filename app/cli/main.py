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
        f"[green]✓[/green] Added '[bold cyan]{name}[/bold cyan]' monitoring {url} (every {interval}s)"
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

    console.print(f"[green]✓[/green] Deleted '[bold cyan]{name}[/bold cyan]'.")


@app.command()
def update(
    name: str = typer.Option(..., help="Service name to update"),
    url: str | None = typer.Option(None, help="New health check URL"),
    interval: int | None = typer.Option(None, help="New check interval in seconds"),
    timeout: int | None = typer.Option(None, help="New request timeout in seconds"),
) -> None:
    """Update an existing service's configuration."""
    init_db()

    if not any([url, interval, timeout]):
        console.print(
            "[bold red]Error:[/] Provide at least one field to update (--url, --interval, or --timeout)."
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
        if interval is not None:
            config.interval_seconds = interval
        if timeout is not None:
            config.timeout_seconds = timeout

        session.add(config)
        session.commit()

    console.print(f"[green]✓[/green] Updated '[bold cyan]{name}[/bold cyan]'.")


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
        console.print(
            "[bold red]Error:[/] No services registered. Use [bold]monagent add[/bold] first."
        )
        raise typer.Exit(1)

    services = [{"type": "http", "name": c.name, "url": c.target_url} for c in configs]
    probes = [HttpProbe(config=c) for c in configs]

    async def _run_with_tui() -> None:
        from loguru import logger

        logger.remove()

        engine = ProbeEngine(probes=probes)

        async def _start_engine() -> None:
            try:
                await engine.start()
            finally:
                await engine.stop()

        dashboard = DashboardApp(
            engine=engine,
            services=services,
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
