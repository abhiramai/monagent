from datetime import datetime
from zoneinfo import ZoneInfo

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Footer, Label, Static

from app.core.engine import ProbeEngine
from app.models.check_result import CheckResult

AEST = ZoneInfo("Australia/Sydney")


class ServiceRow(Static):
    """A high-density, single-line status row."""

    def __init__(self, name: str, url: str) -> None:
        super().__init__()
        self.service_name = name
        self.url = url
        self._result: CheckResult | None = None
        self.status = "PENDING"
        self.latency = "0.00ms"
        self.code = "---"

    def update_data(self, result: CheckResult) -> None:
        self._result = result
        self.status = "HEALTHY" if result.is_healthy else "UNHEALTHY"
        self.latency = f"{result.latency_ms:.2f}ms"
        self.code = str(result.status_code) if result.status_code else "ERR"
        self._refresh_content()

    def _refresh_content(self) -> None:
        color = "green" if self.status == "HEALTHY" else "red"
        self.update(
            f"[bold cyan]{self.service_name:<15}[/] "
            f"[dim white]{self.url:<30}[/] "
            f"[yellow]{self.code:>5}[/] "
            f"[magenta]{self.latency:>10}[/] "
            f" [white on {color}] {self.status} [/]"
        )


class DashboardApp(App[None]):
    """The Zenith-inspired High-Density Dashboard."""

    CSS = """
        Screen { background: #0c0c0c; }

        #top-bar {
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

        #row-container {
            height: 1fr;
            padding: 0 1;
        }

        ServiceRow {
            height: 1;
            margin-bottom: 0;
            padding: 0 1;
        }

        ServiceRow:hover {
            background: #1a1a1a;
        }

        #log-footer {
            height: 4;
            border-top: solid #333;
            color: #666;
            padding: 0 1;
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
        service_names: list[str],
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._engine = engine
        self._service_names = service_names
        self._rows: dict[str, ServiceRow] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="top-bar"):
            yield Label("monagent v0.1.0", id="app-title")
            yield Label("", id="sydney-clock")

        with VerticalScroll(id="row-container"):
            for name in self._service_names:
                url = next(
                    p.config.target_url
                    for p in self._engine._probes
                    if p.config.name == name
                )
                row = ServiceRow(name, url)
                self._rows[name] = row
                yield row

        yield Static(id="log-footer")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(1, self._update_clock)
        self._update_clock()
        self._engine._result_callback = self.post_result

    def _update_clock(self) -> None:
        self.query_one("#sydney-clock", Label).update(
            datetime.now(AEST).strftime("%H:%M:%S AEST")
        )

    def post_result(self, result: CheckResult) -> None:
        """Safe message passing to the UI thread."""
        self.call_next(self._update_row, result)

    def _update_row(self, result: CheckResult) -> None:
        if result.service_name in self._rows:
            row = self._rows[result.service_name]
            row.update_data(result)

            if self.hide_healthy and result.is_healthy:
                row.display = False
            else:
                row.display = True

        if self._engine.log_buffer:
            self.query_one("#log-footer", Static).update(self._engine.log_buffer[-1])

    def action_toggle_healthy(self) -> None:
        self.hide_healthy = not self.hide_healthy
        for name, row in self._rows.items():
            if self.hide_healthy:
                row.display = (
                    not row._result.is_healthy if row._result is not None else True
                )
            else:
                row.display = True
