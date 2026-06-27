from __future__ import annotations

import os
import socket
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse

from config import PROJECT_ROOT
from storage.db import get_connection, init_db, mark_alert_sent, mark_price_history_alert_sent, was_alert_sent


ENV_PATH = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    sender: str
    recipient: str


def load_dotenv(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = strip_inline_comment(value.strip()).strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def strip_inline_comment(value: str) -> str:
    quote: str | None = None
    for index, char in enumerate(value):
        if char in {"'", '"'}:
            quote = None if quote == char else char
        if char == "#" and quote is None and (index == 0 or value[index - 1].isspace()):
            return value[:index].strip()
    return value.strip()


def load_email_config(path: Path = ENV_PATH) -> EmailConfig:
    load_dotenv(path)
    required = {
        "SMTP_HOST": os.getenv("SMTP_HOST"),
        "SMTP_PORT": os.getenv("SMTP_PORT"),
        "SMTP_USER": os.getenv("SMTP_USER"),
        "SMTP_PASSWORD": os.getenv("SMTP_PASSWORD"),
        "EMAIL_FROM": os.getenv("EMAIL_FROM"),
        "EMAIL_TO": os.getenv("EMAIL_TO"),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ValueError(f"Missing email config keys: {', '.join(missing)}")
    smtp_host, smtp_port = normalize_smtp_host_port(str(required["SMTP_HOST"]), str(required["SMTP_PORT"]))
    return EmailConfig(
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=str(required["SMTP_USER"]),
        smtp_password=str(required["SMTP_PASSWORD"]),
        sender=str(required["EMAIL_FROM"]),
        recipient=str(required["EMAIL_TO"]),
    )


def normalize_smtp_host_port(raw_host: str, raw_port: str) -> tuple[str, int]:
    host = raw_host.strip()
    port = int(str(raw_port).strip() or "587")
    if "://" in host:
        parsed = urlparse(host)
        host = parsed.hostname or host
        if parsed.port:
            port = parsed.port
    elif host.count(":") == 1:
        possible_host, possible_port = host.rsplit(":", 1)
        if possible_host and possible_port.isdigit():
            host = possible_host
            port = int(possible_port)
    return host.strip(" /"), port


def to_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def price_text(value: object) -> str:
    number = to_float(value)
    return "未获取" if number is None else f"{number:.2f}"


def yes_no(value: object) -> str:
    return "是" if bool(value) else "否"


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "是"}


def evaluate_email_decision(record: dict) -> tuple[bool, str]:
    if not record.get("meets_target_price"):
        return False, "not_meets_target_price"
    if to_float(record.get("final_price")) is None:
        return False, "missing_final_price"
    if truthy(record.get("stale")):
        return False, "stale_data"
    if record.get("failure_reason") == "douyin_app_required_price_hidden" and record.get("confidence") != "manual_confirmed":
        return False, "douyin_app_required_price_hidden"
    if record.get("price_source") == "current_page_price_fallback" and truthy(record.get("require_final_price")):
        return False, "require_final_price_blocks_fallback"
    if record.get("confidence") not in {"manual_confirmed", "high", "medium"}:
        return False, "confidence_not_allowed"
    return True, ""


def should_send_email(record: dict) -> bool:
    eligible, _ = evaluate_email_decision(record)
    return eligible


def annotate_email_decisions(records: list[dict], email_enabled: bool) -> None:
    for record in records:
        eligible, reason = evaluate_email_decision(record)
        record["email_eligible"] = eligible
        record["alert_sent"] = False
        if not eligible:
            record["email_skip_reason"] = reason
        elif not email_enabled:
            record["email_skip_reason"] = "email_disabled_no_email_mode"
        else:
            record["email_skip_reason"] = ""


def build_alert_subject(record: dict) -> str:
    price_source = record.get("price_source")
    confidence = record.get("confidence")
    if price_source == "manual_confirmed" or confidence == "manual_confirmed":
        prefix = "【手动确认价格低于心理价】"
    elif price_source == "explicit_final_price" or confidence == "high":
        prefix = "【高可信券后价低于心理价】"
    elif price_source == "estimated_after_discount" or confidence == "medium":
        prefix = "【估算券后价低于心理价】"
    else:
        prefix = "【页面价低于心理价-需人工确认】"
    return f"{prefix}{record.get('product_name') or record.get('name') or ''}"


def build_alert_body(record: dict) -> str:
    none_text = "无"
    lines = [
        "监控价已低于或等于你设置的心理价。",
        f"商品名: {record.get('product_name') or record.get('name') or ''}",
        f"平台: {record.get('platform') or ''}",
        f"监控价: {price_text(record.get('final_price'))}",
        f"心理价: {price_text(record.get('target_price'))}",
        f"price_source: {record.get('price_source') or none_text}",
        f"confidence: {record.get('confidence') or none_text}",
        f"source_type: {record.get('source_type') or none_text}",
        f"是否大促期间: {yes_no(record.get('is_promo_period'))}",
        f"promo_name: {record.get('promo_name') or none_text}",
        f"stale: {yes_no(record.get('stale'))}",
        f"failure_reason: {record.get('failure_reason') or none_text}",
        f"raw_price_text: {record.get('raw_price_text') or none_text}",
        f"discount_text: {record.get('discount_text') or none_text}",
        f"商品链接: {record.get('url') or ''}",
        f"采集时间: {record.get('collected_at') or record.get('checked_at') or ''}",
    ]
    return "\n".join(lines)


def send_email(subject: str, body: str, config: EmailConfig) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.sender
    message["To"] = config.recipient
    message.set_content(body)
    if config.smtp_port == 465:
        with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=30) as smtp:
            smtp.login(config.smtp_user, config.smtp_password)
            smtp.send_message(message)
        return

    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(config.smtp_user, config.smtp_password)
        smtp.send_message(message)


def send_price_alert(record: dict, config: EmailConfig | None = None) -> bool:
    if not should_send_email(record):
        return False
    config = config or load_email_config()
    send_email(build_alert_subject(record), build_alert_body(record), config)
    print(f"已发送价格提醒: {record.get('platform')} - {record.get('product_name') or record.get('name')}")
    return True


def send_failure_reason(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, socket.gaierror):
        return "send_failed:smtp_host_unresolved", "SMTP 主机无法解析，请检查 SMTP_HOST。"
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "send_failed:smtp_auth_failed", "SMTP 认证失败，请检查邮箱授权码。"
    if isinstance(exc, TimeoutError):
        return "send_failed:smtp_timeout", "SMTP 连接超时。"
    return f"send_failed:{type(exc).__name__}", f"邮件发送失败: {type(exc).__name__}"


def send_alerts(records: list[dict]) -> int:
    annotate_email_decisions(records, email_enabled=True)
    eligible = [record for record in records if record.get("email_eligible")]
    if not eligible:
        return 0
    try:
        config = load_email_config()
    except ValueError:
        print("邮件配置不完整，跳过邮件提醒。")
        for record in eligible:
            record["email_skip_reason"] = "email_config_incomplete"
        return 0

    sent_count = 0
    alert_date = datetime.now().date().isoformat()
    with get_connection() as conn:
        init_db(conn)
        for record in eligible:
            record["alert_sent"] = False
            final_price = to_float(record.get("final_price"))
            if final_price is None:
                record["email_skip_reason"] = "missing_final_price"
                continue
            product_id = str(record.get("product_id") or record.get("id") or "")
            price_source = record.get("price_source")
            confidence = record.get("confidence")
            if was_alert_sent(conn, product_id, final_price, alert_date, config.recipient, price_source, confidence):
                print(f"今日同级别提醒已发送，跳过: {record.get('platform')} - {record.get('product_name') or record.get('name')}")
                record["email_skip_reason"] = "already_sent_today"
                continue
            try:
                send_price_alert(record, config)
            except Exception as exc:
                reason, message = send_failure_reason(exc)
                record["email_skip_reason"] = reason
                print(f"{message} 跳过本条: {record.get('platform')} - {record.get('product_name') or record.get('name')}")
                continue
            sent_at = datetime.now().isoformat(timespec="seconds")
            mark_alert_sent(
                conn,
                product_id=product_id,
                url=str(record.get("url") or ""),
                final_price=final_price,
                alert_date=alert_date,
                sent_at=sent_at,
                recipient=config.recipient,
                price_history_id=record.get("price_history_id"),
                price_source=price_source,
                confidence=confidence,
            )
            mark_price_history_alert_sent(conn, record.get("price_history_id"), sent_at)
            record["alert_sent"] = True
            record["email_skip_reason"] = "sent"
            sent_count += 1
    return sent_count


def send_test_email(config: EmailConfig | None = None) -> bool:
    try:
        config = config or load_email_config()
    except ValueError:
        print("邮件配置不完整，无法发送测试邮件。")
        return False
    try:
        send_email("护肤品价格监控 SMTP 测试", "这是一封 SMTP 测试邮件。", config)
    except Exception as exc:
        _, message = send_failure_reason(exc)
        print(f"测试邮件发送失败: {message}")
        return False
    print("测试邮件已发送。")
    return True
