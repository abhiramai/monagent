from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Footer, Label, Static

from app.core.engine import ProbeEngine
from app.models.check_result import CheckResult

AEST = ZoneInfo("Australia/Sydney")

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

HEADER_FMT = (
    f"[bold #00ffff]{'PROBE':<{COL_PROBE}}[/]"
    f"[bold #00ffff]{'SERVICE':<{COL_SERVICE}}[/]"
    f"[bold #00ffff]{'TARGET':<{COL_TARGET}}[/]"
    f"[bold #00ffff]{'RESP':<{COL_RESP}}[/]"
    f"[bold #00ffff]{'LATENCY':<{COL_LATENCY}}[/]"
    f"[bold #00ffff]{'STATUS':<{COL_STATUS}}[/]"
    f"[bold #00ffff]{'🔔/🚨':<{COL_ALERT}}[/]"
)

SEPARATOR = "[dim #333333]" + "─" * TOTAL_WIDTH + "[/]"


class ServiceRow(Static):
    """A high-density, single-line service status row."""

    DEFAULT_CSS = """
        ServiceRow {
            height: 1;
            padding: 0 1;
            margin-bottom: 0;
        }
        ServiceRow:hover {
            background: #1a1a1a;
        }
    """

    scroll_offset: reactive[int] = reactive(0)

    def __init__(
        self,
        probe_type: str,
        name: str,
        url: str,
        alert_threshold: int = 0,
        last_seen: datetime | None = None,
    ) -> None:
        super().__init__()
        self.probe_type = probe_type
        self.service_name = name
        self.url = url
        self.alert_threshold = alert_threshold
        self.last_seen = last_seen
        self._result: CheckResult | None = None
        self._alerted = False

    def on_mount(self) -> None:
        if len(self.url) > COL_TARGET:
            self.set_interval(0.2, self._tick_scroll)

    def _tick_scroll(self) -> None:
        padded = self.url + "   |   "
        if self.scroll_offset >= len(padded):
            self.scroll_offset = 0
        else:
            self.scroll_offset += 1

    def update_data(self, result: CheckResult, alerted: bool = False) -> None:
        self._result = result
        self._alerted = alerted
        self._refresh()

    def _refresh(self) -> None:
        if self._result is None:
            probe_display = (
                f"[dim]💓 HEARTBEAT[/]{'': <{COL_PROBE - 10}}"
                if self.probe_type == "heartbeat"
                else f"[dim]🔌 TCP[/]{'': <{COL_PROBE - 6}}"
                if self.probe_type == "tcp"
                else f"[dim]🌐 HTTP[/]{'': <{COL_PROBE - 6}}"
            )
            url_display = "Pending..."
            self.update(
                f"{probe_display}"
                f"[bold cyan]{self.service_name:<{COL_SERVICE}}[/]"
                f"[dim green]{url_display:<{COL_TARGET}}[/]"
                f"[yellow]{'...':<{COL_RESP}}[/]"
                f"[magenta]{'...':<{COL_LATENCY}}[/]"
                f"[white on #666666] PENDING [/]"
            )
            return

        r = self._result

        probe_display = (
            f"[dim]💓 HEARTBEAT[/]{'': <{COL_PROBE - 10}}"
            if self.probe_type == "heartbeat"
            else f"[dim]🔌 TCP[/]{'': <{COL_PROBE - 6}}"
            if self.probe_type == "tcp"
            else f"[dim]🌐 HTTP[/]{'': <{COL_PROBE - 6}}"
        )

        if self.probe_type == "heartbeat":
            resp = "THUMP" if r.is_healthy else "STALE"
        elif self.probe_type == "tcp":
            resp = "OPEN" if r.is_healthy else "CLOSED"
        else:
            resp = str(r.status_code) if r.status_code else "ERR"
        lat = f"{r.latency_ms:.1f}ms"

        if r.is_healthy:
            badge = "[white on #00aa44] HEALTHY [/]"
        else:
            badge = "[white on #cc2222] UNHEALTHY[/]"

        if self.probe_type == "heartbeat":
            if self.last_seen:
                delta = datetime.now(timezone.utc) - self.last_seen.replace(
                    tzinfo=timezone.utc
                )
                url_display = f"Last seen: {delta.total_seconds():.0f}s ago"
            else:
                url_display = "Never seen"
        elif len(self.url) <= COL_TARGET:
            url_display = self.url
        else:
            padded = self.url + "   |   "
            offset = self.scroll_offset % len(padded)
            url_display = (padded + padded)[offset : offset + COL_TARGET]

        # Alert column: empty if no threshold, green bell if monitoring, red siren if alerted
        if self.alert_threshold == 0:
            alert_display = ""
        elif self._alerted:
            alert_display = "[bold red]🚨[/]"
        else:
            alert_display = "[bold green]🔔[/]"

        self.update(
            f"{probe_display}"
            f"[bold cyan]{self.service_name:<{COL_SERVICE}}[/]"
            f"[dim green]{url_display:<{COL_TARGET}}[/]"
            f"[yellow]{resp:<{COL_RESP}}[/]"
            f"[magenta]{lat:<{COL_LATENCY}}[/]"
            f"{badge}"
            f"{alert_display}"
        )


class DashboardApp(App[None]):
    """The Zenith Dashboard — a professional, constant-aligned TUI."""

    CSS = """
        Screen {
            background: #0c0c0c;
        }

        #header-bar {
            height: 1;
            padding: 0 1;
        }

        #app-title {
            text-style: bold;
            color: #00ffff;
        }

        #sydney-clock {
            width: auto;
            dock: right;
            color: #ffaa00;
            text-style: bold;
            padding: 0 1;
        }

        #column-header {
            height: 1;
            padding: 0 1;
            background: #1a1a2e;
        }

        #row-container {
            height: 1fr;
        }
    """

    BINDINGS = [
        ("h", "toggle_healthy", "Hide Healthy"),
        ("q", "quit", "Quit"),
    ]

    hide_healthy: reactive[bool] = reactive(False)

    def __init__(
        self,
        engine: ProbeEngine,
        services: list[dict[str, str]],
        **kwargs: object,
    ) -> None:
        """
        Args:
            engine: The running ProbeEngine.
            services: List of dicts with keys 'type', 'name', 'url'.
        """
        super().__init__(**kwargs)
        self._engine = engine
        self._services = services
        self._rows: dict[str, ServiceRow] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="header-bar"):
            yield Label("monagent v0.1.0", id="app-title")
            yield Label("", id="sydney-clock")

        yield Static(HEADER_FMT, id="column-header")
        yield Static(SEPARATOR, id="column-separator")

        with VerticalScroll(id="row-container"):
            existing_names = set()
            for svc in self._services:
                row = ServiceRow(
                    probe_type=svc["type"],
                    name=svc["name"],
                    url=svc["url"],
                    alert_threshold=svc.get("alert_threshold", 0),
                    last_seen=svc.get("last_seen"),
                )
                self._rows[svc["name"]] = row
                existing_names.add(svc["name"])
                yield row

            for probe in self._engine._probes:
                if probe.config.name not in existing_names:
                    row = ServiceRow(
                        probe_type=probe.config.probe_type,
                        name=probe.config.name,
                        url=probe.config.target_url,
                        alert_threshold=probe.config.alert_threshold,
                        last_seen=probe.config.last_seen,
                    )
                    self._rows[probe.config.name] = row
                    yield row

        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(1, self._update_clock)
        self._update_clock()
        self._engine._result_callback = self.post_result

    def _update_clock(self) -> None:
        now = datetime.now(AEST).strftime("%H:%M:%S AEST")
        self.query_one("#sydney-clock", Label).update(now)

    def post_result(self, result: CheckResult, alerted: bool = False) -> None:
        """Thread-safe entry point called by the engine callback."""
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
        """Add any newly discovered services to the dashboard."""
        container = self.query_one("#row-container", VerticalScroll)
        new_rows = []
        for svc in self._engine._probes:
            if svc.config.name not in self._rows:
                row = ServiceRow(
                    probe_type=svc.config.probe_type,
                    name=svc.config.name,
                    url=svc.config.target_url,
                    alert_threshold=svc.config.alert_threshold,
                    last_seen=svc.config.last_seen,
                )
                self._rows[svc.config.name] = row
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
