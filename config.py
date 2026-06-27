from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
PRODUCTS_PATH = PROJECT_ROOT / "products.xlsx"
REPORTS_DIR = PROJECT_ROOT / "reports"
SCREENSHOTS_DIR = PROJECT_ROOT / "screenshots"
BACKUPS_DIR = PROJECT_ROOT / "backups"
PRICE_HISTORY_DB = PROJECT_ROOT / "price_history.db"

SUPPORTED_PLATFORMS = {"淘宝", "抖音"}
DEFAULT_STALE_HOURS = 6


def ensure_runtime_dirs() -> None:
    for path in [REPORTS_DIR, SCREENSHOTS_DIR, BACKUPS_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
