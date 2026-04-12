from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Footer, Label, Static

from app.core.db import get_session
from app.core.time_utils import now_utc, to_aest, to_aware, now_aware
from sqlmodel import select
from app.models.check_result import CheckResult, ServiceConfig

# ── Column Width Constants ──────────────────────────────────────────
COL_PROBE = 12
COL_SERVICE = 20
COL_TARGET = 35
COL_RESP = 10
COL_LATENCY = 12
COL_STATUS = 15
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
        self._alerted: bool = False

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
                    last_seen_value = latest_result.extra_info["last_seen"]
                    # Convert string to datetime if needed (for SQLite JSON storage)
                    if isinstance(last_seen_value, str):
                        try:
                            from datetime import datetime

                            last_seen_value = datetime.fromisoformat(last_seen_value)
                        except ValueError:
                            pass  # Keep original value if conversion fails
                    self.config.last_seen = last_seen_value
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
                    now_aware() - to_aware(self.config.last_seen)
                ).total_seconds() > self.config.interval_seconds
                is_healthy = not is_stale
            else:
                is_healthy = False
        else:
            if self._result:
                is_healthy = self._result.is_healthy
            else:
                is_healthy = None

        # 2. Build Display Strings
        probe_icon = {"http": "🌐", "tcp": "🔌", "heartbeat": "💓"}.get(
            self.config.probe_type, "❓"
        )
        probe_display = f"[dim]{probe_icon} {self.config.probe_type.upper():<{COL_PROBE - len(probe_icon) - 2}}[/]"
        service_display = f"[bold bright_cyan]{self.config.name:<{COL_SERVICE}}[/]"

        # URL display (possibly scrolling)
        if self.config.probe_type == "heartbeat":
            source_ip = "N/A"
            if (
                self._result
                and self._result.extra_info
                and "source_ip" in self._result.extra_info
            ):
                source_ip = str(self._result.extra_info["source_ip"])
            elif self.config.client_ip:
                source_ip = str(self.config.client_ip)
            target_display = f"[bold cyan]{source_ip:<{COL_TARGET}}[/]"
        else:
            url_display = self.config.target_url
            if len(url_display) > COL_TARGET:
                padded = url_display + "   |   "
                url_display = (padded + padded)[
                    self.scroll_offset : self.scroll_offset + COL_TARGET
                ]
            target_display = f"[bold white]{url_display:<{COL_TARGET}}[/]"

        # Response and Latency
        if self.config.probe_type == "heartbeat":
            if is_healthy:
                if self.config.interval_seconds >= 3600 and self.config.last_seen:
                    seconds_remaining = (
                        self.config.interval_seconds
                        - (
                            now_aware() - to_aware(self.config.last_seen)
                        ).total_seconds()
                    )
                    if seconds_remaining > 0:
                        hours_remaining = int(seconds_remaining // 3600)
                        minutes_remaining = int((seconds_remaining % 3600) // 60)
                        if hours_remaining > 0:
                            resp = f"TTL{hours_remaining}h"
                        else:
                            resp = f"TTL{minutes_remaining}m"
                    else:
                        resp = "STALE    "
                else:
                    resp = "THUMP    "
            else:
                resp = "STALE    "
            lat = " " * COL_LATENCY
        elif self.config.probe_type == "tcp":
            resp = "OPEN" if is_healthy else "CLOSED"
            lat = " " * COL_LATENCY
        else:  # http
            resp = (
                str(self._result.status_code)
                if self._result and self._result.status_code is not None
                else "ERR"
            )
            lat = (
                f"{self._result.latency_ms:.1f}ms"
                if self._result
                else " " * COL_LATENCY
            )

        # 3. Determine Badge and Alert Icon
        badge_status = (
            "PENDING"
            if is_healthy is None
            else ("HEALTHY" if is_healthy else "UNHEALTHY")
        )
        if is_healthy is None:
            badge = f"[black on #cccc00] {badge_status:>9} [/]"
            alert_display = ""
        elif is_healthy:
            badge = f"[black on #00aa44] {badge_status:>9} [/]"
            alert_display = (
                "[bold green]🔔[/]" if self.config.alert_threshold > 0 else ""
            )
        else:
            badge = f"[white on #cc2222] {badge_status:>9} [/]"
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

    # Utility method used by DashboardApp to apply result updates
    def update_data(self, result: CheckResult, alerted: bool = False) -> None:
        self._result = result
        if result.extra_info and "last_seen" in result.extra_info:
            self.config.last_seen = result.extra_info["last_seen"]
        # Preserve alert state if needed (unused currently)
        self._alerted = alerted


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

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._rows: dict[str, ServiceRow] = {}
        self.hide_healthy: bool = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="header-bar"):
            yield Label("monagent 0.1", id="app-title")
            yield Label("", id="sydney-clock")
        yield Static(HEADER_FMT, id="column-header")
        yield Static(SEPARATOR, id="column-separator")
        with VerticalScroll(id="row-container"):
            pass

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

    def post_result(self, result: CheckResult, alerted: bool = False) -> None:
        self.call_next(self._update_row, result, alerted)

    def _update_row(self, result: CheckResult, alerted: bool = False) -> None:
        if result.service_name == "__sync__":
            self._sync_rows()
            return

        if result.service_name in self._rows:
            row = self._rows[result.service_name]
            row.update_data(result, alerted)
            if self.hide_healthy and result.is_healthy:
                row.display = False
            else:
                row.display = True

    def _sync_rows(self) -> None:
        from app.core.db import get_engine
        from app.core.engine import ProbeEngine
        from app.probes.base import BaseProbe

        # Since we don't have a reference to the running engine, we rebuild the probe list from DB
        engine = get_engine()
        with Session(engine) as session:
            configs = session.exec(select(ServiceConfig)).all()
        probes: list[BaseProbe] = []
        for c in configs:
            if c.probe_type == "http":
                from app.probes.http import HttpProbe

                probes.append(HttpProbe(config=c))
            elif c.probe_type == "tcp":
                from app.probes.tcp import TcpProbe

                probes.append(TcpProbe(config=c))
            elif c.probe_type == "heartbeat":
                from app.probes.heartbeat import HeartbeatProbe

                probes.append(HeartbeatProbe(config=c))

        container = self.query_one("#row-container", VerticalScroll)
        new_rows = []
        for probe in probes:
            if probe.config.name not in self._rows:
                row = ServiceRow(config=probe.config)
                self._rows[probe.config.name] = row
                new_rows.append(row)
        if new_rows:
            container.mount_all(new_rows)

    def action_toggle_healthy(self) -> None:
        self.hide_healthy = not self.hide_healthy
        for row in self._rows.values():
            if self.hide_healthy:
                row.display = (
                    not row._result.is_healthy if row._result is not None else True
                )
            else:
                row.display = True
