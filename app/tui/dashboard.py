from datetime import datetime
from sqlmodel import select

from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Footer, Label, Static

from app.core.db import get_session
from app.core.time_utils import now_utc, to_aest, to_aware
from app.models.check_result import CheckResult, ServiceConfig

# ── Column Width Constants ──────────────────────────────────────────
COL_PROBE = 12
COL_SERVICE = 20
COL_TARGET = 35
COL_RESP = 10
COL_LATENCY = 12
COL_STATUS = 12
COL_ALERT = 3

TOTAL_WIDTH = (
    COL_PROBE
    + COL_SERVICE
    + COL_TARGET
    + COL_RESP
    + COL_LATENCY
    + COL_STATUS
    + COL_ALERT
)

# Pillar 2: NOC Contrast Header
HEADER_FMT = (
    f"[bold white]{'PROBE':<{COL_PROBE}}[/]"
    f"[bold white]{'SERVICE':<{COL_SERVICE}}[/]"
    f"[bold white]{'TARGET':<{COL_TARGET}}[/]"
    f"[bold white]{'RESP':<{COL_RESP}}[/]"
    f"[bold white]{'LATENCY':<{COL_LATENCY}}[/]"
    f"[bold white]{'STATUS':<{COL_STATUS}}[/]"
    f"[bold white]{'🔔/🚨':<{COL_ALERT}}[/]"
)

SEPARATOR = "[bold #555555]" + "─" * TOTAL_WIDTH + "[/]"


class ServiceRow(Static):
    """A self-refreshing, database-driven service status row."""

    scroll_offset: reactive[int] = reactive(0)

    def __init__(self, config: ServiceConfig) -> None:
        super().__init__()
        self.config = config
        self._result: CheckResult | None = None

    def on_mount(self) -> None:
        if len(self.config.target_url) > COL_TARGET:
            self.set_interval(0.2, self._tick_scroll)
        # Each row polls the DB for its own state
        self.set_interval(1.0, self.poll_database)
        self.poll_database()  # Initial poll

    async def poll_database(self) -> None:
        """Poll the database for the latest config and check result."""
        with get_session() as session:
            self.config = session.get(ServiceConfig, self.config.id) or self.config

            latest_result = session.exec(
                select(CheckResult)
                .where(CheckResult.service_name == self.config.name)
                .order_by(CheckResult.timestamp.desc())
            ).first()
            self._result = latest_result
            # Update config.last_seen from extra_info if present
            if latest_result and hasattr(latest_result, "extra_info"):
                if "last_seen" in latest_result.extra_info:
                    self.config.last_seen = latest_result.extra_info["last_seen"]
        self._refresh()

    def _tick_scroll(self) -> None:
        padded = self.config.target_url + "   |   "
        self.scroll_offset = (self.scroll_offset + 1) % len(padded)

    def _refresh(self) -> None:
        # 1. Determine Health Status
        is_healthy: bool | None
        if self.config.probe_type == "heartbeat":
            if self.config.last_seen:
                is_stale = (
                    now_utc() - to_aware(self.config.last_seen)
                ).total_seconds() > self.config.interval_seconds
                is_healthy = not is_stale
            else:
                is_healthy = False
        elif self._result:
            is_healthy = self._result.is_healthy
        else:
            is_healthy = None  # Pending

        # 2. Build Display Strings
        probe_icon = {"http": "🌐", "tcp": "🔌", "heartbeat": "💓"}.get(
            self.config.probe_type, "❓"
        )
        probe_display = f"[bold magenta]{probe_icon} {self.config.probe_type.upper():<{COL_PROBE - 3}}[/]"
        service_display = f"[bold bright_cyan]{self.config.name:<{COL_SERVICE}}[/]"

        if self.config.probe_type == "heartbeat":
            resp, lat = "", ""
            if self.config.last_seen:
                delta = (now_utc() - to_aware(self.config.last_seen)).total_seconds()
                url_display = f"Last seen: {delta:.0f}s ago"
                resp = "THUMP" if is_healthy else "STALE"
            else:
                url_display = "Never seen"
                resp = "SILENT"
        elif self._result:
            resp = str(self._result.status_code) if self._result.status_code else "ERR"
            lat = f"{self._result.latency_ms:.1f}ms"
            url_display = self.config.target_url
        else:
            # No result yet – show blanks (previously "..."/"Pending...")
            resp = ""
            lat = ""
            url_display = self.config.target_url

        if len(url_display) > COL_TARGET:
            padded = url_display + "   |   "
            url_display = (padded + padded)[
                self.scroll_offset : self.scroll_offset + COL_TARGET
            ]

        target_display = f"[bold white]{url_display:<{COL_TARGET}}[/]"

        # 3. Determine Badge and Alert Icon
        if is_healthy is None:
            badge = "[black on yellow] PENDING [/]"
            alert_display = ""
        elif is_healthy:
            badge = "[white on #00aa44] HEALTHY [/]"
            alert_display = (
                "[bold green]🔔[/]" if self.config.alert_threshold > 0 else ""
            )
        else:
            badge = "[white on #cc2222] UNHEALTHY [/]"
            alert_display = "[bold red]🚨[/]" if self.config.alert_threshold > 0 else ""

        # 4. Update Renderable
        line = (
            f"{probe_display}"
            f"{service_display}"
            f"{target_display}"
            f"[yellow]{resp:<{COL_RESP}}[/]"
            f"[magenta]{lat:<{COL_LATENCY}}[/]"
            f"{badge:<{COL_STATUS}} "
            f"{alert_display}"
        )
        self.update(line)


class DashboardApp(App[None]):
    CSS_PATH = None
    CSS = """
Screen {
    background: black;
    color: white;
}
#header-bar {
    background: #111111;
    height: 1;
    padding: 0 1;
}
#app-title {
    color: ansi_bright_cyan;
    text-style: bold;
    width: 100%;
    text-align: center;
}
#sydney-clock {
    color: ansi_bright_cyan;
    text-style: bold;
    text-align: right;
    width: 100%;
}
#column-header, #column-separator {
    background: #222222;
}
ServiceRow {
    height: 1;
    padding: 0 1;
    margin-bottom: 0;
}
"""
    BINDINGS = [("q", "quit", "Quit")]

    # ... (rest of DashboardApp remains the same as previous refactor) ...
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._rows: dict[str, ServiceRow] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="header-bar"):
            yield Label("monagent v1.0.0-final", id="app-title")
            yield Label("", id="sydney-clock")
        yield Static(HEADER_FMT, id="column-header")
        yield Static(SEPARATOR, id="column-separator")
        yield VerticalScroll(id="row-container")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(1, self._update_clock)
        self._update_clock()
        with get_session() as session:
            configs = session.exec(select(ServiceConfig)).all()
        container = self.query_one("#row-container", VerticalScroll)
        for config in configs:
            row = ServiceRow(config=config)
            self._rows[config.name] = row
        if self._rows:
            container.mount_all(self._rows.values())

    def _update_clock(self) -> None:
        now = to_aest(now_utc()).strftime("%H:%M:%S AEST")
        self.query_one("#sydney-clock", Label).update(now)
