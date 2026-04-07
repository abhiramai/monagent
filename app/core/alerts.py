import os
from datetime import datetime, timezone
from pathlib import Path

import apprise
from loguru import logger

ALERT_LOG = Path("data") / "alerts.log"


class AlertManager:
    """
    Manages one-shot notifications via apprise.
    Loads notification URLs from the MONAGENT_ALERTS environment variable
    (comma-separated). Sends asynchronously without blocking the engine.
    """

    def __init__(self) -> None:
        self._apprise = apprise.Apprise()
        self._urls: list[str] = []
        alert_urls = os.environ.get("MONAGENT_ALERTS", "")
        for url in (u.strip() for u in alert_urls.split(",") if u.strip()):
            self._apprise.add(url)
            self._urls.append(url)
            logger.info(f"Alert channel registered: {url.split('://')[0]}")

        if not alert_urls.strip():
            logger.info("No alert channels configured (MONAGENT_ALERTS not set)")

    async def send_notification(self, title: str, body: str) -> bool:
        """
        Send a notification asynchronously.
        Returns True if at least one notification was sent successfully.
        """
        if not self._apprise:
            return False

        try:
            result = await self._apprise.async_notify(title=title, body=body)
            if result:
                logger.info(f"Alert sent: {title}")
            else:
                self._log_failure(title, "apprise returned False")
            return result is True
        except Exception as e:
            self._log_failure(title, f"{type(e).__name__}: {e}")
            return False

    def _log_failure(self, title: str, reason: str) -> None:
        """Write alert failure details to data/alerts.log for inspection."""
        ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        urls = ", ".join(self._urls) if self._urls else "(none configured)"
        line = f"[{ts}] FAILED: {title} — {reason} — URLs: {urls}\n"
        with open(ALERT_LOG, "a", encoding="utf-8") as f:
            f.write(line)
        logger.warning(f"Alert failure logged to {ALERT_LOG}: {title}")
