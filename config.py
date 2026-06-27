from __future__ import annotations

import sys
from pathlib import Path


def runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundled_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parent


def resource_path(name: str) -> Path:
    external = PROJECT_ROOT / name
    if external.exists():
        return external
    bundled = BUNDLED_ROOT / name
    if bundled.exists():
        return bundled
    return external


PROJECT_ROOT = runtime_root()
BUNDLED_ROOT = bundled_root()
PRODUCTS_PATH = resource_path("products.xlsx")
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
