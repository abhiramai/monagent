import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from loguru import logger

AEST = ZoneInfo("Australia/Sydney")

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def _patch_aest(record: dict) -> None:
    record["extra"]["aest"] = (
        record["time"].astimezone(AEST).strftime("%Y-%m-%d %H:%M:%S AEST")
    )


logger.remove()
logger.configure(patcher=_patch_aest)

logger.add(
    sys.stderr,
    level="DEBUG",
    format="<green>{extra[aest]}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    colorize=True,
)

logger.add(
    LOG_DIR / "monagent.log",
    level="DEBUG",
    format="{extra[aest]} | {level: <8} | {name}:{function}:{line} - {message}",
    rotation="10 MB",
    retention="7 days",
    encoding="utf-8",
)
