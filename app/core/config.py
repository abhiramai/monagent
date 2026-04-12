import os
from pathlib import Path

APP_DIR = Path.home() / ".monagent"
APP_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = APP_DIR / "monagent.db"
LOG_DIR = APP_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

PID_FILE = APP_DIR / "monagent.pid"
