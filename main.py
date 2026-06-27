from __future__ import annotations

import argparse
import time
from datetime import datetime

from config import DEFAULT_STALE_HOURS, configure_console, ensure_runtime_dirs
from notify.email_notifier import annotate_email_decisions, send_alerts, send_test_email
from product_io import load_products
from storage.reporter import generate_report, latest_by_product, print_console_summary


def summarize_for_api(records: list[dict]) -> dict:
    return {
        "total": len(records),
        "collected": sum(1 for record in records if record.get("collected")),
        "uncollected": sum(1 for record in records if not record.get("collected")),
        "meets_target": sum(1 for record in records if record.get("meets_target_price")),
        "email_eligible": sum(1 for record in records if record.get("email_eligible")),
        "alert_sent": sum(1 for record in records if record.get("alert_sent")),
    }


def build_records(products_path: str, stale_hours: int = DEFAULT_STALE_HOURS) -> list[dict]:
    ensure_runtime_dirs()
    products = load_products(products_path)
    return latest_by_product(products, stale_hours=stale_hours)


def generate_report_no_email(products_path: str = "products.xlsx", stale_hours: int = DEFAULT_STALE_HOURS) -> dict:
    records = build_records(products_path, stale_hours)
    annotate_email_decisions(records, email_enabled=False)
    report_path = generate_report(records)
    return {"records": records, "report_path": report_path, "summary": summarize_for_api(records), "sent_count": 0}


def send_alerts_and_generate_report(products_path: str = "products.xlsx", stale_hours: int = DEFAULT_STALE_HOURS) -> dict:
    records = build_records(products_path, stale_hours)
    sent_count = send_alerts(records)
    report_path = generate_report(records)
    return {"records": records, "report_path": report_path, "summary": summarize_for_api(records), "sent_count": sent_count}


def run_once(products_path: str, email: bool, stale_hours: int = DEFAULT_STALE_HOURS) -> list[dict]:
    result = send_alerts_and_generate_report(products_path, stale_hours) if email else generate_report_no_email(products_path, stale_hours)
    records = result["records"]

    if not any(record.get("collected") for record in records):
        print("还没有任何采集数据。请先启动 local_collector.py，并用 Chrome 插件采集商品。")
    print(f"本轮实际发送邮件: {result['sent_count']}" if email else "本轮已禁用邮件提醒。")
    print_console_summary(records)
    print(f"报告已生成: {result['report_path']}")
    return records


def main() -> None:
    configure_console()
    parser = argparse.ArgumentParser(description="Generate reports and alerts from Chrome extension price collections.")
    parser.add_argument("--products", default="products.xlsx", help="Product XLSX or CSV path.")
    parser.add_argument("--interval-minutes", type=int, default=60, help="Report/alert interval in minutes.")
    parser.add_argument("--once", action="store_true", help="Run once and exit.")
    parser.add_argument("--no-email", action="store_true", help="Generate report without sending email alerts.")
    parser.add_argument("--test-email", action="store_true", help="Send one SMTP test email and exit.")
    parser.add_argument("--stale-hours", type=int, default=DEFAULT_STALE_HOURS, help="Collected data older than this is marked stale.")
    args = parser.parse_args()

    if args.test_email:
        send_test_email()
        return

    email = not args.no_email
    if args.once:
        run_once(args.products, email=email, stale_hours=args.stale_hours)
        return

    print(f"启动报告/提醒循环，每 {args.interval_minutes} 分钟运行一次。按 Ctrl+C 停止。")
    try:
        while True:
            print(f"[{datetime.now().isoformat(timespec='seconds')}] 生成报告并检查提醒")
            run_once(args.products, email=email, stale_hours=args.stale_hours)
            time.sleep(args.interval_minutes * 60)
    except KeyboardInterrupt:
        print("已停止。")


if __name__ == "__main__":
    main()
