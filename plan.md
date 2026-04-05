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

### Phase 1: Foundation (Structure)
- **Directory Setup:** `/app/core`, `/app/probes`, `/app/models`.
- **Environment:** Create `pyproject.toml` using `uv` (preferred for 2026 speed) or `poetry`.
- **Base Class:** Implement `BaseProbe` Abstract Base Class (ABC) to define the `check()` method contract.

### Phase 2: The Async Engine
- **Orchestration:** Create `AsyncMonitorEngine` to run multiple checks concurrently.
- **Timing:** Use `asyncio.sleep()` loops that respect individual service intervals.
- **Logging:** Implement structured logging (Standard `logging` or `Loguru`).

### Phase 3: Home Lab Specifics (The "Real Problems")
- **TrueNAS SCALE v26 Integration:** Implement a WebSocket JSON-RPC v2.0 client.
- **Target:** Query `pool.query`. Alert if any pool status != `ONLINE`.
- **Service Checks:** Add `HTTPProbe` for **Immich** and **Audiobookshelf**.

### Phase 4: State Logic & Notifications
- **Alert Suppression:** Implement a `StateStore` to track previous status. Only fire Consumers if `current_status != previous_status`.
- **Resilience:** Add "Retry Logic"—a service must fail $X$ consecutive times (default 3) before a "DOWN" alert is sent.

---

## 5. AI Guardrails (Strict)
- **Think Before Coding:** Before every code block, the AI must summarize the design pattern it is about to use.
- **No Monoliths:** Every Probe must live in its own file within `/app/probes/`.
- **No Trial and Error:** If an API endpoint is unknown, the AI must ask for clarification or reference the 2026 documentation rather than guessing.
- **Error Handling:** `BaseProbe.run()` is an Explicit Error Boundary. It must use a general `except Exception` to prevent engine-wide crashes. However, all subclasses MUST implement specific exception handling for known library errors (e.g., `httpx.RequestError`) within their `perform_check` methods to provide granular feedback.
- **Documentation:** Every class and public method requires a Python docstring.