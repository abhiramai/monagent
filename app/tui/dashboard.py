from datetime import datetime
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

TOTAL_WIDTH = COL_PROBE + COL_SERVICE + COL_TARGET + COL_RESP + COL_LATENCY + COL_STATUS

HEADER_FMT = (
    f"[bold #00ffff]{'PROBE':<{COL_PROBE}}[/]"
    f"[bold #00ffff]{'SERVICE':<{COL_SERVICE}}[/]"
    f"[bold #00ffff]{'TARGET':<{COL_TARGET}}[/]"
    f"[bold #00ffff]{'RESP':<{COL_RESP}}[/]"
    f"[bold #00ffff]{'LATENCY':<{COL_LATENCY}}[/]"
    f"[bold #00ffff]{'STATUS':<{COL_STATUS}}[/]"
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

    def __init__(self, probe_type: str, name: str, url: str) -> None:
        super().__init__()
        self.probe_type = probe_type
        self.service_name = name
        self.url = url
        self._result: CheckResult | None = None

    def on_mount(self) -> None:
        if len(self.url) > COL_TARGET:
            self.set_interval(0.2, self._tick_scroll)

    def _tick_scroll(self) -> None:
        self.scroll_offset += 1

    def update_data(self, result: CheckResult) -> None:
        self._result = result
        self._refresh()

    def _refresh(self) -> None:
        assert self._result is not None
        r = self._result

        probe_display = (
            f"[dim]🔌 TCP[/]{'': <{COL_PROBE - 6}}"
            if self.probe_type == "tcp"
            else f"[dim]🌐 HTTP[/]{'': <{COL_PROBE - 6}}"
        )

        if self.probe_type == "tcp":
            resp = "OPEN" if r.is_healthy else "CLOSED"
        else:
            resp = str(r.status_code) if r.status_code else "ERR"
        lat = f"{r.latency_ms:.1f}ms"

        if r.is_healthy:
            badge = "[white on #00aa44] HEALTHY [/]"
        else:
            badge = "[white on #cc2222] UNHEALTHY[/]"

        if len(self.url) <= COL_TARGET:
            url_display = self.url
        else:
            looped = self.url + " | "
            offset = self.scroll_offset % len(looped)
            window = (looped + looped)[: offset + COL_TARGET][
                offset : offset + COL_TARGET
            ]
            url_display = window

        self.update(
            f"{probe_display}"
            f"[bold cyan]{self.service_name:<{COL_SERVICE}}[/]"
            f"[dim green]{url_display:<{COL_TARGET}}[/]"
            f"[yellow]{resp:<{COL_RESP}}[/]"
            f"[magenta]{lat:<{COL_LATENCY}}[/]"
            f"{badge}"
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
