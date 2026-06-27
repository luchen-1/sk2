from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from config import DEFAULT_STALE_HOURS, REPORTS_DIR
from storage.db import get_connection, init_db, latest_collection_rows


REPORT_COLUMNS = [
    "product_name",
    "platform",
    "final_price",
    "target_price",
    "meets_target_price",
    "price_source",
    "confidence",
    "source_type",
    "collected_at",
    "stale",
    "email_eligible",
    "email_skip_reason",
    "alert_sent",
    "failure_reason",
    "url",
]

LABELS = {
    "manual_confirmed": "手动确认价",
    "explicit_final_price": "页面明确券后价/到手价",
    "estimated_after_discount": "根据优惠估算价",
    "current_page_price_fallback": "普通页面价",
    "none": "暂无数据",
    "": "暂无数据",
    None: "暂无数据",
    "chrome_extension": "浏览器插件采集",
    "manual_input": "手动录入",
    "report_only": "仅报告记录",
    "high": "高可信",
    "medium": "中可信",
    "low": "低可信",
    "sent": "已发送邮件提醒",
    "already_sent_today": "今日已提醒，避免重复发送",
    "not_meets_target_price": "未达到心理价",
    "stale": "数据已过期，未提醒",
    "stale_data": "数据已过期，未提醒",
    "low_confidence": "价格可信度较低，未正式提醒",
    "confidence_not_allowed": "价格可信度较低，未正式提醒",
    "email_disabled_no_email_mode": "本次只生成报告，未发送邮件",
    "email_config_incomplete": "邮件配置不完整，未发送",
    "missing_final_price": "没有可用价格，未提醒",
    "require_final_price_blocks_fallback": "要求明确券后价，普通页面价未提醒",
    "douyin_app_required_price_hidden": "抖音 Web 隐藏完整价格，需手动确认",
    "price_not_found": "未找到价格",
}

CHINESE_COLUMNS = {
    "final_price": "当前采集价 / 当前到手价",
    "target_price": "心理价",
    "meets_target_price": "是否达到心理价",
    "price_source": "价格来源",
    "confidence": "价格可信度",
    "source_type": "数据来源",
    "collected_at": "采集时间",
    "stale": "数据是否过期",
    "email_eligible": "是否符合提醒条件",
    "email_skip_reason": "邮件处理结果",
    "alert_sent": "是否已发送提醒",
}


def markdown_escape(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace("\r", " ").replace("|", "\\|")


def to_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def format_price(value: object) -> str:
    number = to_float(value)
    if number is None:
        return "暂无数据"
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return f"{text} 元"


def parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def format_datetime(value: object) -> str:
    parsed = parse_datetime(value)
    if parsed is None:
        return "暂无数据"
    return parsed.strftime("%Y-%m-%d %H:%M")


def is_stale(collected_at: object, stale_hours: int = DEFAULT_STALE_HOURS, now: datetime | None = None) -> bool:
    collected = parse_datetime(collected_at)
    if collected is None:
        return True
    now = now or datetime.now()
    return now - collected > timedelta(hours=stale_hours)


def label_for(value: object) -> str:
    if value in LABELS:
        return LABELS[value]
    text = str(value or "").strip()
    if not text:
        return "暂无数据"
    if text.startswith("send_failed:"):
        return f"邮件发送失败：{text.split(':', 1)[1]}"
    return text


def yes_no(value: object) -> str:
    return "是" if bool(value) else "否"


def target_result(record: dict) -> str:
    return "已达到心理价" if record.get("meets_target_price") else "未达到心理价"


def email_status(record: dict) -> str:
    if record.get("alert_sent"):
        return "已发送邮件提醒"
    return label_for(record.get("email_skip_reason"))


def latest_by_product(products: pd.DataFrame, stale_hours: int = DEFAULT_STALE_HOURS) -> list[dict]:
    with get_connection() as conn:
        init_db(conn)
        rows = latest_collection_rows(conn)

    latest: dict[str, dict] = {}
    latest_by_item: dict[str, dict] = {}
    latest_by_url: dict[str, dict] = {}
    for row in rows:
        record = dict(row)
        key = str(record.get("product_id") or "")
        if key and key not in latest:
            latest[key] = record
        item_id = str(record.get("item_id") or "")
        if item_id and item_id not in latest_by_item:
            latest_by_item[item_id] = record
        normalized_url = str(record.get("normalized_url") or "")
        if normalized_url and normalized_url not in latest_by_url:
            latest_by_url[normalized_url] = record

    report_records: list[dict] = []
    now = datetime.now()
    for product in products.to_dict("records"):
        product_id = str(product.get("id") or "")
        item_id = str(product.get("item_id") or "")
        normalized_url = str(product.get("normalized_url") or "")
        latest_record = latest.get(product_id) or latest_by_item.get(item_id) or latest_by_url.get(normalized_url)
        base = {
            "product_id": product_id,
            "product_name": product.get("name") or "",
            "name": product.get("name") or "",
            "platform": product.get("platform") or "",
            "url": product.get("url") or "",
            "normalized_url": normalized_url,
            "item_id": item_id,
            "target_price": product.get("target_price"),
            "require_final_price": bool(product.get("require_final_price")),
            "promo_name": product.get("promo_name") or "",
            "is_promo_period": False,
            "collected": False,
            "stale": True,
            "meets_target_price": False,
            "source_type": "",
        }
        if latest_record:
            merged = {**base, **latest_record}
            merged["product_name"] = latest_record.get("product_name") or latest_record.get("name") or base["product_name"]
            merged["target_price"] = to_float(latest_record.get("target_price")) or to_float(base["target_price"])
            merged["price_history_id"] = latest_record.get("id")
            merged["collected"] = True
            stale_time = latest_record.get("created_at") or latest_record.get("collected_at") or latest_record.get("checked_at")
            merged["stale"] = is_stale(stale_time, stale_hours, now)
            final_price = to_float(merged.get("final_price"))
            target_price = to_float(merged.get("target_price"))
            merged["meets_target_price"] = final_price is not None and target_price is not None and final_price <= target_price
            report_records.append(merged)
        else:
            report_records.append(base)
    return report_records


def today_alerted_count(alert_date: date | None = None) -> int:
    alert_date = alert_date or date.today()
    try:
        with get_connection() as conn:
            init_db(conn)
            row = conn.execute(
                "SELECT COUNT(DISTINCT product_id) AS count FROM sent_alerts WHERE alert_date = ?",
                (alert_date.isoformat(),),
            ).fetchone()
        return int(row["count"] or 0) if row else 0
    except Exception:
        return 0


def latest_history_records(limit: int = 10) -> list[dict]:
    with get_connection() as conn:
        init_db(conn)
        rows = latest_collection_rows(conn)
    return [dict(row) for row in rows[:limit]]


def summarize_records(records: list[dict]) -> dict:
    return {
        "total": len(records),
        "collected": sum(1 for record in records if record.get("collected")),
        "uncollected": sum(1 for record in records if not record.get("collected")),
        "meets_target": sum(1 for record in records if record.get("meets_target_price")),
        "email_sent": sum(1 for record in records if record.get("alert_sent")),
        "today_alerted": today_alerted_count(),
        "price_sources": dict(Counter(str(record.get("price_source") or "none") for record in records)),
        "confidences": dict(Counter(str(record.get("confidence") or "none") for record in records)),
        "failure_reasons": dict(Counter(str(record.get("failure_reason") or "none") for record in records)),
        "email_decisions": dict(Counter(str(record.get("email_skip_reason") or "none") for record in records)),
    }


def append_product_block(lines: list[str], record: dict) -> None:
    lines.extend(
        [
            f"商品：{record.get('platform') or '未知平台'} - {record.get('product_name') or record.get('name') or '未命名商品'}",
            f"当前到手价：{format_price(record.get('final_price'))}",
            f"心理价：{format_price(record.get('target_price'))}",
            f"判断结果：{target_result(record)}",
            f"价格来源：{label_for(record.get('price_source'))}",
            f"价格可信度：{label_for(record.get('confidence'))}",
            f"采集时间：{format_datetime(record.get('collected_at') or record.get('checked_at') or record.get('created_at'))}",
            f"邮件状态：{email_status(record)}",
            "",
        ]
    )


def append_recent_table(lines: list[str], records: list[dict]) -> None:
    if not records:
        lines.extend(["暂无最近采集记录。", ""])
        return
    headers = ["商品", "平台", "当前价", "心理价", "判断结果", "价格来源", "采集时间", "邮件状态"]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for record in records:
        row = [
            record.get("product_name") or record.get("name") or "",
            record.get("platform") or "",
            format_price(record.get("final_price")),
            format_price(record.get("target_price")),
            target_result(record),
            label_for(record.get("price_source") or record.get("confidence")),
            format_datetime(record.get("collected_at") or record.get("checked_at") or record.get("created_at")),
            "已发送提醒" if record.get("alert_sent") else "未发送提醒",
        ]
        lines.append("| " + " | ".join(markdown_escape(item) for item in row) + " |")
    lines.append("")


def append_email_table(lines: list[str], records: list[dict]) -> None:
    target_records = [record for record in records if record.get("meets_target_price")]
    if not target_records:
        lines.extend(["本次没有达到心理价的商品需要处理邮件提醒。", ""])
        return
    headers = ["商品", "平台", "是否符合提醒条件", "邮件处理结果", "是否已发送提醒"]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for record in target_records:
        row = [
            record.get("product_name") or record.get("name") or "",
            record.get("platform") or "",
            "符合" if record.get("email_eligible") else "不符合",
            email_status(record),
            "是" if record.get("alert_sent") else "否",
        ]
        lines.append("| " + " | ".join(markdown_escape(item) for item in row) + " |")
    lines.append("")


def generate_report(records: list[dict], report_time: datetime | None = None) -> Path:
    report_time = report_time or datetime.now()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"price_check_report_{report_time.strftime('%Y%m%d_%H%M%S')}.md"
    summary = summarize_records(records)

    target_records = [record for record in records if record.get("collected") and record.get("meets_target_price")]
    collected_miss_records = [record for record in records if record.get("collected") and not record.get("meets_target_price")]
    uncollected_records = [record for record in records if not record.get("collected")]

    lines = [
        "# 护肤品价格监控报告",
        "",
        f"- 生成时间：{report_time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 总商品数：{summary['total']}",
        f"- 已采集商品数：{summary['collected']}",
        f"- 未采集商品数：{summary['uncollected']}",
        f"- 达到心理价商品数：{summary['meets_target']}",
        f"- 已发送邮件提醒数：{summary['email_sent']}",
        f"- 今日已提醒商品数：{summary['today_alerted']}",
        "",
        "## 一、今日达到心理价商品",
        "",
    ]
    if target_records:
        for record in target_records:
            append_product_block(lines, record)
    else:
        lines.extend(["今日暂无达到心理价的商品。", ""])

    lines.extend(["## 二、已采集但未达到心理价商品", ""])
    if collected_miss_records:
        for record in collected_miss_records:
            append_product_block(lines, record)
    else:
        lines.extend(["暂无已采集但未达到心理价的商品。", ""])

    lines.extend(["## 三、未采集商品", ""])
    if uncollected_records:
        for record in uncollected_records:
            lines.append(f"- {record.get('platform') or '未知平台'} - {record.get('product_name') or record.get('name') or '未命名商品'}，心理价：{format_price(record.get('target_price'))}")
        lines.append("")
    else:
        lines.extend(["所有商品都已有采集记录。", ""])

    lines.extend(["## 四、最近采集记录", ""])
    append_recent_table(lines, latest_history_records(limit=10))

    lines.extend(["## 五、邮件提醒处理结果", ""])
    append_email_table(lines, records)

    lines.extend(
        [
            "## 附：字段说明",
            "",
            "- 当前采集价 / 当前到手价：本次保存或插件采集到的价格。",
            "- 心理价：products.xlsx 中设置的目标价格。",
            "- 价格来源：手动确认价、页面明确券后价/到手价、根据优惠估算价或普通页面价。",
            "- 价格可信度：手动确认价、高可信、中可信或低可信。",
            "- 数据是否过期：超过默认有效期的数据不会发送正式提醒。",
            "- 邮件处理结果：说明本次为什么发送、跳过或等待人工确认。",
            "",
        ]
    )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def print_console_summary(records: list[dict]) -> None:
    summary = summarize_records(records)
    print(f"总商品数: {summary['total']}")
    print(f"已采集商品数: {summary['collected']}")
    print(f"未采集商品数: {summary['uncollected']}")
    print(f"达到心理价商品数: {summary['meets_target']}")
    print(f"已发送邮件提醒数: {summary['email_sent']}")
    print(f"今日已提醒商品数: {summary['today_alerted']}")
    print(f"price_source 分布: {summary['price_sources']}")
    print(f"confidence 分布: {summary['confidences']}")
    print(f"failure_reason 分布: {summary['failure_reasons']}")
    print(f"email_skip_reason 分布: {summary['email_decisions']}")
    target_records = [record for record in records if record.get("meets_target_price")]
    if target_records:
        print("达到心理价商品邮件决策:")
        for record in target_records:
            print(
                "  {platform} - {name}: email_eligible={eligible}, "
                "email_skip_reason={reason}, alert_sent={sent}".format(
                    platform=record.get("platform") or "",
                    name=record.get("product_name") or record.get("name") or "",
                    eligible=record.get("email_eligible"),
                    reason=record.get("email_skip_reason") or "",
                    sent=record.get("alert_sent"),
                )
            )
