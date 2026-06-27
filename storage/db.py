from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from config import PRICE_HISTORY_DB


DB_PATH = PRICE_HISTORY_DB
SOURCE_TYPES = {"chrome_extension", "manual_input", "report_only"}

PRICE_HISTORY_COLUMNS = {
    "product_id": "TEXT",
    "product_name": "TEXT",
    "name": "TEXT",
    "category": "TEXT",
    "brand": "TEXT",
    "platform": "TEXT",
    "url": "TEXT",
    "normalized_url": "TEXT",
    "item_id": "TEXT",
    "page_title": "TEXT",
    "current_price": "REAL",
    "final_price": "REAL",
    "target_price": "REAL",
    "price_source": "TEXT",
    "confidence": "TEXT",
    "meets_target_price": "INTEGER NOT NULL DEFAULT 0",
    "is_below_target": "INTEGER NOT NULL DEFAULT 0",
    "require_final_price": "INTEGER NOT NULL DEFAULT 0",
    "is_promo_period": "INTEGER NOT NULL DEFAULT 0",
    "promo_name": "TEXT",
    "raw_price_text": "TEXT",
    "discount_text": "TEXT",
    "selected_text": "TEXT",
    "manual_price": "REAL",
    "source_type": "TEXT",
    "failure_reason": "TEXT",
    "error_message": "TEXT",
    "collected_at": "TEXT",
    "created_at": "TEXT",
    "checked_at": "TEXT",
    "stale": "INTEGER NOT NULL DEFAULT 0",
    "alert_sent": "INTEGER NOT NULL DEFAULT 0",
    "alerted_at": "TEXT",
    "error": "TEXT",
    "coupon_text": "TEXT",
    "promotion_text": "TEXT",
    "original_price": "REAL",
    "screenshot_path": "TEXT",
}
INSERT_COLUMNS = list(PRICE_HISTORY_COLUMNS)


def get_connection(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] if isinstance(row, sqlite3.Row) else row[1] for row in rows}


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT,
            product_name TEXT,
            name TEXT,
            category TEXT,
            brand TEXT,
            platform TEXT,
            url TEXT,
            normalized_url TEXT,
            item_id TEXT,
            page_title TEXT,
            current_price REAL,
            final_price REAL,
            target_price REAL,
            price_source TEXT,
            confidence TEXT,
            meets_target_price INTEGER NOT NULL DEFAULT 0,
            is_below_target INTEGER NOT NULL DEFAULT 0,
            require_final_price INTEGER NOT NULL DEFAULT 0,
            is_promo_period INTEGER NOT NULL DEFAULT 0,
            promo_name TEXT,
            raw_price_text TEXT,
            discount_text TEXT,
            selected_text TEXT,
            manual_price REAL,
            source_type TEXT,
            failure_reason TEXT,
            error_message TEXT,
            collected_at TEXT,
            created_at TEXT,
            checked_at TEXT,
            stale INTEGER NOT NULL DEFAULT 0,
            alert_sent INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            coupon_text TEXT,
            promotion_text TEXT,
            original_price REAL,
            screenshot_path TEXT
        )
        """
    )
    ensure_price_history_columns(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_price_history_product_collected ON price_history (product_id, collected_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_price_history_url_collected ON price_history (normalized_url, collected_at)")
    init_sent_alerts(conn)
    conn.commit()


def ensure_price_history_columns(conn: sqlite3.Connection) -> None:
    existing = table_columns(conn, "price_history")
    for column, definition in PRICE_HISTORY_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE price_history ADD COLUMN {column} {definition}")


def init_sent_alerts(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sent_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT,
            url TEXT,
            final_price REAL,
            alert_date TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            recipient TEXT NOT NULL,
            price_history_id INTEGER,
            price_source TEXT,
            confidence TEXT,
            alert_level TEXT NOT NULL DEFAULT 'fallback',
            FOREIGN KEY(price_history_id) REFERENCES price_history(id)
        )
        """
    )
    existing = table_columns(conn, "sent_alerts")
    for column, definition in {
        "product_id": "TEXT",
        "url": "TEXT",
        "final_price": "REAL",
        "price_source": "TEXT",
        "confidence": "TEXT",
        "alert_level": "TEXT NOT NULL DEFAULT 'fallback'",
        "price_history_id": "INTEGER",
    }.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE sent_alerts ADD COLUMN {column} {definition}")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sent_alerts_product_once_per_day_level
        ON sent_alerts (product_id, final_price, alert_date, recipient, alert_level)
        """
    )


def db_bool(value: object) -> int:
    return 1 if bool(value) else 0


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    product_name = normalized.get("product_name") or normalized.get("name") or ""
    normalized["product_name"] = product_name
    normalized["name"] = product_name
    normalized["checked_at"] = normalized.get("checked_at") or normalized.get("collected_at") or normalized.get("created_at")
    normalized["source_type"] = normalized.get("source_type") if normalized.get("source_type") in SOURCE_TYPES else "report_only"
    normalized["is_below_target"] = db_bool(normalized.get("meets_target_price"))
    for column in ["meets_target_price", "require_final_price", "is_promo_period", "stale", "alert_sent"]:
        normalized[column] = db_bool(normalized.get(column))
    normalized["coupon_text"] = normalized.get("coupon_text") or normalized.get("discount_text")
    normalized["promotion_text"] = normalized.get("promotion_text") or normalized.get("discount_text")
    return normalized


def insert_price_record(conn: sqlite3.Connection, record: dict[str, Any]) -> int:
    normalized = normalize_record(record)
    placeholders = ", ".join("?" for _ in INSERT_COLUMNS)
    cursor = conn.execute(
        f"INSERT INTO price_history ({', '.join(INSERT_COLUMNS)}) VALUES ({placeholders})",
        [normalized.get(column) for column in INSERT_COLUMNS],
    )
    conn.commit()
    history_id = int(cursor.lastrowid)
    record["price_history_id"] = history_id
    return history_id


def insert_price_records(records: list[dict[str, Any]], db_path: str | Path = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        init_db(conn)
        for record in records:
            insert_price_record(conn, record)


def latest_collection_rows(conn: sqlite3.Connection, source_types: tuple[str, ...] = ("chrome_extension", "manual_input")) -> list[sqlite3.Row]:
    placeholders = ", ".join("?" for _ in source_types)
    return conn.execute(
        f"""
        SELECT *
        FROM price_history
        WHERE source_type IN ({placeholders})
        ORDER BY COALESCE(collected_at, checked_at, created_at) DESC, id DESC
        """,
        source_types,
    ).fetchall()


def alert_level_for(price_source: str | None, confidence: str | None) -> str:
    if price_source == "manual_confirmed" or confidence == "manual_confirmed":
        return "manual"
    if price_source == "explicit_final_price" or confidence == "high":
        return "explicit"
    if price_source == "estimated_after_discount" or confidence == "medium":
        return "estimated"
    return "fallback"


def was_alert_sent(
    conn: sqlite3.Connection,
    product_id: str,
    final_price: float,
    alert_date: str,
    recipient: str,
    price_source: str | None = None,
    confidence: str | None = None,
) -> bool:
    alert_level = alert_level_for(price_source, confidence)
    row = conn.execute(
        """
        SELECT 1
        FROM sent_alerts
        WHERE product_id = ? AND final_price = ? AND alert_date = ? AND recipient = ? AND alert_level = ?
        LIMIT 1
        """,
        (product_id, final_price, alert_date, recipient, alert_level),
    ).fetchone()
    return row is not None


def mark_alert_sent(
    conn: sqlite3.Connection,
    product_id: str,
    url: str,
    final_price: float,
    alert_date: str,
    sent_at: str,
    recipient: str,
    price_history_id: int | None,
    price_source: str | None = None,
    confidence: str | None = None,
) -> None:
    alert_level = alert_level_for(price_source, confidence)
    conn.execute(
        """
        INSERT OR IGNORE INTO sent_alerts
            (product_id, url, final_price, alert_date, sent_at, recipient, price_history_id, price_source, confidence, alert_level)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (product_id, url, final_price, alert_date, sent_at, recipient, price_history_id, price_source, confidence, alert_level),
    )
    conn.commit()


def mark_price_history_alert_sent(conn: sqlite3.Connection, price_history_id: int | None, alerted_at: str) -> None:
    if price_history_id is None:
        return
    conn.execute(
        """
        UPDATE price_history
        SET alert_sent = 1, alerted_at = ?
        WHERE id = ?
        """,
        (alerted_at, price_history_id),
    )
    conn.commit()
