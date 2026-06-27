from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time as datetime_time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from config import PRODUCTS_PATH, configure_console, ensure_runtime_dirs
from parsers.price_parser import DOUYIN_APP_REQUIRED_KEYWORDS, parse_price_text, to_float
from product_io import (
    detect_platform_from_url,
    extract_item_id,
    find_matching_product,
    load_products,
    normalize_url,
)
from storage.db import get_connection, init_db, insert_price_record


HOST = "127.0.0.1"
PORT = 8765


def parse_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"true", "t", "yes", "y", "1", "是"}:
        return True
    if text in {"false", "f", "no", "n", "0", "否"}:
        return False
    return default


def parse_promo_datetime(value: object, end_of_day: bool = False) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime_time.max if end_of_day else datetime_time.min)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt in {"%Y-%m-%d", "%Y/%m/%d"} and end_of_day:
                return datetime.combine(parsed.date(), datetime_time.max)
            return parsed
        except ValueError:
            continue
    return None


def is_promo_period(product: dict, now: datetime | None = None) -> bool:
    now = now or datetime.now()
    start = parse_promo_datetime(product.get("promo_start"), end_of_day=False)
    end = parse_promo_datetime(product.get("promo_end"), end_of_day=True)
    if start is None or end is None:
        return False
    return start <= now <= end


def compact_error(exc: BaseException | str, max_length: int = 240) -> str:
    text = str(exc).replace("\r", " ").replace("\n", " ")
    return " ".join(text.split())[:max_length]


def message_for(record: dict) -> str:
    if record.get("failure_reason") == "douyin_app_required_price_hidden":
        return "抖音 Web 端隐藏完整价格，请手动确认后提交。"
    if not record.get("meets_target_price"):
        return "已记录，当前价格未达到心理价。"
    final_price = to_float(record.get("final_price"))
    target_price = to_float(record.get("target_price"))
    if final_price is not None and target_price is not None and final_price < target_price:
        return "已低于心理价。"
    return "已等于心理价。"


def build_record(payload: dict[str, Any], product: dict, parsed: dict) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    url = str(payload.get("url") or "")
    platform = detect_platform_from_url(url) or product.get("platform") or str(payload.get("platform") or "")
    manual_price = to_float(payload.get("manual_price"))
    final_price = to_float(parsed.get("final_price"))
    target_price = to_float(product.get("target_price"))
    meets_target = final_price is not None and target_price is not None and final_price <= target_price
    visible_text = str(payload.get("visible_text") or "")
    hidden_price = any(keyword in visible_text for keyword in DOUYIN_APP_REQUIRED_KEYWORDS)
    failure_reason = parsed.get("failure_reason")
    if hidden_price and manual_price is None and platform == "抖音":
        failure_reason = "douyin_app_required_price_hidden"

    return {
        "product_id": str(product.get("id") or ""),
        "product_name": product.get("name") or "",
        "category": product.get("category") or "",
        "brand": product.get("brand") or "",
        "platform": platform,
        "url": url,
        "normalized_url": normalize_url(url),
        "item_id": extract_item_id(url, platform),
        "page_title": payload.get("page_title") or "",
        "current_price": parsed.get("current_price"),
        "final_price": parsed.get("final_price"),
        "target_price": target_price,
        "price_source": parsed.get("price_source"),
        "confidence": parsed.get("confidence"),
        "meets_target_price": meets_target,
        "require_final_price": parse_bool(product.get("require_final_price"), default=False),
        "is_promo_period": is_promo_period(product),
        "promo_name": product.get("promo_name") or "",
        "raw_price_text": parsed.get("raw_price_text"),
        "discount_text": parsed.get("discount_text"),
        "selected_text": payload.get("selected_text") or "",
        "manual_price": manual_price,
        "source_type": "chrome_extension",
        "failure_reason": failure_reason,
        "error_message": None,
        "collected_at": now,
        "created_at": now,
        "checked_at": payload.get("collected_at") or now,
        "stale": False,
        "alert_sent": False,
    }


def handle_collect(payload: dict[str, Any], products_path: str | Path = PRODUCTS_PATH) -> dict[str, Any]:
    url = str(payload.get("url") or "").strip()
    if not url:
        return {"ok": False, "matched": False, "failure_reason": "missing_url", "message": "缺少商品页面 URL。"}

    platform = detect_platform_from_url(url)
    if platform not in {"淘宝", "抖音"}:
        return {"ok": False, "matched": False, "failure_reason": "unsupported_platform", "message": "当前只支持淘宝、天猫、天猫国际和抖音。"}

    products = load_products(products_path)
    product = find_matching_product(products, url, str(payload.get("page_title") or ""))
    if product is None:
        return {
            "ok": False,
            "matched": False,
            "failure_reason": "product_not_found_in_excel",
            "message": "未匹配到 products.xlsx 中的商品，请检查商品链接或商品名。",
        }

    parsed = parse_price_text(
        visible_text=str(payload.get("visible_text") or ""),
        selected_text=payload.get("selected_text"),
        price_candidates=payload.get("price_candidates") or [],
        manual_price=to_float(payload.get("manual_price")),
        user_price_source=payload.get("user_price_source"),
    )
    record = build_record(payload, product, parsed)

    try:
        with get_connection() as conn:
            init_db(conn)
            insert_price_record(conn, record)
    except Exception as exc:
        record["failure_reason"] = record.get("failure_reason") or "sqlite_write_failed"
        record["error_message"] = compact_error(exc)
        return {
            "ok": False,
            "matched": True,
            "product_name": record["product_name"],
            "platform": record["platform"],
            "failure_reason": record["failure_reason"],
            "message": "商品已匹配，但写入 SQLite 失败。",
            "error_message": record["error_message"],
        }

    return {
        "ok": True,
        "matched": True,
        "product_name": record["product_name"],
        "platform": record["platform"],
        "current_price": record["current_price"],
        "final_price": record["final_price"],
        "target_price": record["target_price"],
        "meets_target_price": record["meets_target_price"],
        "price_source": record["price_source"],
        "confidence": record["confidence"],
        "failure_reason": record["failure_reason"],
        "message": message_for(record),
        "alert_sent": False,
        "price_history_id": record.get("price_history_id"),
    }


class CollectorHandler(BaseHTTPRequestHandler):
    server_version = "SkincareCollector/2.0"

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_json(200, {"ok": True})

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(200, {"ok": True, "service": "skincare-local-collector"})
        else:
            self.send_json(404, {"ok": False, "message": "Not found"})

    def do_POST(self) -> None:
        if self.path != "/api/collect":
            self.send_json(404, {"ok": False, "message": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object")
        except Exception as exc:
            self.send_json(400, {"ok": False, "failure_reason": "invalid_json", "message": compact_error(exc)})
            return

        result = handle_collect(payload)
        status = 200 if result.get("ok") else 400
        self.send_json(status, result)


def run_server(host: str = HOST, port: int = PORT) -> None:
    ensure_runtime_dirs()
    server = ThreadingHTTPServer((host, port), CollectorHandler)
    print(f"本地采集服务已启动: http://{host}:{port}")
    print("等待 Chrome 插件提交采集数据，按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("本地采集服务已停止。")
    finally:
        server.server_close()


def main() -> None:
    configure_console()
    parser = argparse.ArgumentParser(description="Local HTTP collector for Chrome extension price submissions.")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    print("local_collector.py 兼容入口：现在推荐使用 dashboard.py。")
    from dashboard import run_server as run_dashboard_server

    run_dashboard_server(args.host, args.port)


if __name__ == "__main__":
    main()
