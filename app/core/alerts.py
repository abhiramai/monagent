import os

import apprise
from loguru import logger


class AlertManager:
    """
    Manages one-shot notifications via apprise.
    Loads notification URLs from the MONAGENT_ALERTS environment variable
    (comma-separated). Sends asynchronously without blocking the engine.
    """

    def __init__(self) -> None:
        self._apprise = apprise.Apprise()
        alert_urls = os.environ.get("MONAGENT_ALERTS", "")
        for url in (u.strip() for u in alert_urls.split(",") if u.strip()):
            self._apprise.add(url)
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
                logger.warning(f"Alert failed to send: {title}")
            return result is True
        except Exception:
            logger.exception(f"Alert exception for: {title}")
            return False
