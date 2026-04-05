# Project Blueprint: monagent (2026 Edition)

## 1. Executive Summary
**Vision:** A lightweight, headless, modular Python monitoring service.
**Primary Goal:** Monitor APIs, MCP, HTTP, cloud rersources.
**Philosophy:** 90% Planning, 10% Implementation. Architecture over Speed.

---

## 2. Technical Stack & Constraints
* **Language:** Python 3.12+ (Strict Type Hinting required).
* **Async Engine:** `asyncio` + `httpx` (Strictly NO `requests` or blocking I/O).
* **Data Validation:** `Pydantic v2` for all schemas and configuration.
* **Configuration:** `pydantic-settings` for Environment Variables.
* **Hardware Context:** Monitoring for slow degrdations.

---

## 3. System Architecture & Data Contracts

### 3A. The Atomic Unit (The "Contract")
All probes MUST return this exact Pydantic model. 

```python
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    service_name: str
    is_healthy: bool
    latency_ms: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status_code: Optional[int] = None
    error_message: Optional[str] = None

### 3B. Component Layers
To maintain the "90% Planning" philosophy, the system is strictly decoupled into three layers:

1.  **Probes (The Eyes):** - Modular classes inheriting from `BaseProbe`.
    - Responsibilities: Network connection, data parsing, and returning a `CheckResult`.
    - *Example:* `TrueNASProbe`, `HTTPProbe`, `DockerProbe`.
2.  **The Engine (The Brain):** - An `asyncio` event loop.
    - Responsibilities: Managing check intervals, triggering Probes concurrently, and passing results to Consumers.
3.  **Consumers (The Voice):** - Notification handlers triggered ONLY on state changes (e.g., UP -> DOWN).
    - *Example:* `NtfyConsumer`, `TelegramConsumer`, `ConsoleLogger`.
---

## 4. Implementation Roadmap

### Phase 1: Foundation (Structure) ✅
- **Directory Setup:** `/app/core`, `/app/probes`, `/app/models`, `/app/cli`, `/app/tui`, `/app/consumers`.
- **Environment:** `pyproject.toml` with `uv`, `hatchling` build system.
- **Base Class:** `BaseProbe` ABC with ODD-driven `run()` wrapper (timing, logging, error boundary).
- **Models:** `CheckResult` (frozen Pydantic) and `ServiceConfig` (SQLModel table).

### Phase 2: The Async Engine ✅
- **Orchestration:** `ProbeEngine` with concurrent heartbeat loops per probe.
- **Connection Pooling:** Single shared `httpx.AsyncClient` with `follow_redirects=True`.
- **TDD:** Engine runs multiple probes concurrently for 5s without crashing.

### Phase 3: Storage Layer ✅
- **SQLModel + SQLite:** `ServiceConfig` persisted to `data/monagent.db`.
- **Session Management:** `get_engine()` and `get_session()` generators.
- **TDD:** In-memory SQLite save/retrieve test.

### Phase 4: HTTP Probe ✅
- **HttpProbe:** `httpx.AsyncClient`-based health checks.
- **Resilience:** Catches `ConnectTimeout`, `ConnectError`, `HTTPStatusError`.
- **ODD:** Granular failure logging (e.g., "Connection timed out after 10s").

### Phase 5: CLI & Connection Pooling Refactor ✅
- **Typer CLI:** `monagent add`, `monagent list-services`, `monagent run`.
- **Entry Point:** `[project.scripts]` with `hatchling`.
- **Master Client:** Engine owns one `httpx.AsyncClient`, passes to all probes.

### Phase 6: Zenith Dashboard (TUI) ✅
- **Textual TUI:** htop-style single-line rows with `VerticalScroll`.
- **Features:** Sydney AEST clock, `H` key to hide healthy, `Q` to quit.
- **Loguru Silencing:** Console logs suppressed during TUI, file logs continue.

### Phase 7: TrueNAS SCALE Integration (Next)
- **WebSocket JSON-RPC v2.0:** `TrueNASProbe` connecting to TrueNAS SCALE API.
- **Target:** Query `pool.query` — alert if any pool status != `ONLINE`.
- **Service Checks:** Add HTTP probes for **Immich** and **Audiobookshelf**.

### Phase 8: State Logic & Notifications (Future)
- **Alert Suppression:** `StateStore` to track previous status. Only fire on state changes.
- **Retry Logic:** Service must fail X consecutive times (default 3) before DOWN alert.
- **Consumers:** `NtfyConsumer`, `TelegramConsumer`, `ConsoleLogger`.

---

## 5. AI Guardrails (Strict)
- **Think Before Coding:** Before every code block, the AI must summarize the design pattern it is about to use.
- **No Monoliths:** Every Probe must live in its own file within `/app/probes/`.
- **No Trial and Error:** If an API endpoint is unknown, the AI must ask for clarification or reference the 2026 documentation rather than guessing.
- **Error Handling:** `BaseProbe.run()` is an Explicit Error Boundary. It must use a general `except Exception` to prevent engine-wide crashes. However, all subclasses MUST implement specific exception handling for known library errors (e.g., `httpx.RequestError`) within their `perform_check` methods to provide granular feedback.
- **Documentation:** Every class and public method requires a Python docstring.