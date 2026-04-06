from datetime import datetime
from zoneinfo import ZoneInfo

from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Footer, Label, Static

from app.core.engine import ProbeEngine
from app.models.check_result import CheckResult

AEST = ZoneInfo("Australia/Sydney")

COL_TYPE_W = 6
COL_NAME_W = 16
COL_URL_W = 32
COL_RESP_W = 8
COL_LAT_W = 12
COL_STATUS_W = 10

HEADER_FMT = (
    f"[bold #00ffff]{'PROBE':<{COL_TYPE_W}}[/]"
    f"[bold #00ffff]{'SERVICE':<{COL_NAME_W}}[/]"
    f"[bold #00ffff]{'TARGET':<{COL_URL_W}}[/]"
    f"[bold #00ffff]{'RESP':<{COL_RESP_W}}[/]"
    f"[bold #00ffff]{'LATENCY':<{COL_LAT_W}}[/]"
    f"[bold #00ffff]{'STATUS':<{COL_STATUS_W}}[/]"
)

SEPARATOR = (
    "[dim #333333]"
    + "─"
    * (COL_TYPE_W + COL_NAME_W + COL_URL_W + COL_RESP_W + COL_LAT_W + COL_STATUS_W)
    + "[/]"
)


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

    def __init__(self, probe_type: str, name: str, url: str) -> None:
        super().__init__()
        self.probe_type = probe_type
        self.service_name = name
        self.url = url
        self._result: CheckResult | None = None

    def update_data(self, result: CheckResult) -> None:
        self._result = result
        self._refresh()

    def _refresh(self) -> None:
        assert self._result is not None
        r = self._result

        type_display = (
            f"[dim]HTTP[/]{'':>{COL_TYPE_W - 4}}"
            if self.probe_type == "http"
            else f"{'':<{COL_TYPE_W}}"
        )
        resp = str(r.status_code) if r.status_code else "ERR"
        lat = f"{r.latency_ms:.1f}ms"

        if r.is_healthy:
            badge = "[white on #00aa44] HEALTHY [/]"
        else:
            badge = "[white on #cc2222] UNHEALTHY[/]"

        url_display = (
            self.url if len(self.url) <= COL_URL_W else self.url[: COL_URL_W - 1] + "…"
        )

        self.update(
            f"{type_display}"
            f"[bold cyan]{self.service_name:<{COL_NAME_W}}[/]"
            f"[dim green]{url_display:<{COL_URL_W}}[/]"
            f"[yellow]{resp:<{COL_RESP_W}}[/]"
            f"[magenta]{lat:<{COL_LAT_W}}[/]"
            f"{badge}"
        )


class DashboardApp(App[None]):
    """The Zenith Dashboard — a professional, row-based TUI."""

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
            for svc in self._services:
                row = ServiceRow(
                    probe_type=svc["type"],
                    name=svc["name"],
                    url=svc["url"],
                )
                self._rows[svc["name"]] = row
                yield row

        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(1, self._update_clock)
        self._update_clock()
        self._engine._result_callback = self.post_result

    def _update_clock(self) -> None:
        now = datetime.now(AEST).strftime("%H:%M:%S AEST")
        self.query_one("#sydney-clock", Label).update(now)

    def post_result(self, result: CheckResult) -> None:
        """Thread-safe entry point called by the engine callback."""
        self.call_next(self._update_row, result)

    def _update_row(self, result: CheckResult) -> None:
        if result.service_name in self._rows:
            row = self._rows[result.service_name]
            row.update_data(result)

            if self.hide_healthy and result.is_healthy:
                row.display = False
            else:
                row.display = True

    def action_toggle_healthy(self) -> None:
        self.hide_healthy = not self.hide_healthy
        for row in self._rows.values():
            if self.hide_healthy:
                row.display = (
                    not row._result.is_healthy if row._result is not None else True
                )
            else:
                row.display = True
