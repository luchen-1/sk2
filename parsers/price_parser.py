from __future__ import annotations

import re
from typing import Iterable


MONEY_PATTERN = re.compile(r"(?:[¥￥]\s*)?(\d+(?:\.\d{1,2})?)\s*(?:元)?")
EXPLICIT_FINAL_PATTERN = re.compile(
    r"(到手价|到手参考价|券后价|预估到手|预计到手|优惠后|实付|活动价)"
    r"[^\d¥￥]{0,18}(?:[¥￥]\s*)?(\d+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
CURRENT_PRICE_PATTERN = re.compile(
    r"(当前价|页面价|售价|价格|现价|活动价|秒杀价)"
    r"[^\d¥￥]{0,14}(?:[¥￥]\s*)?(\d+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
FULL_REDUCTION_PATTERN = re.compile(r"满\s*(\d+(?:\.\d{1,2})?)\s*(?:元)?\s*(?:减|立减)\s*(\d+(?:\.\d{1,2})?)")
DIRECT_DISCOUNT_PATTERN = re.compile(
    r"(?:立减|直减|优惠券|店铺券|跨店满减|平台券|券|红包|津贴|补贴)[^\d]{0,12}(\d+(?:\.\d{1,2})?)\s*(?:元)?"
)
DANGEROUS_CONTEXT = ("销量", "评价", "评论", "库存", "月销", "已售", "粉丝", "收藏", "浏览", "发货", "天内", "小时")
PRICE_LINE_KEYWORDS = (
    "到手价",
    "到手参考价",
    "券后价",
    "预估到手",
    "预计到手",
    "优惠后",
    "实付",
    "活动价",
    "当前价",
    "页面价",
    "售价",
    "价格",
    "现价",
)
DISCOUNT_KEYWORDS = ("立减", "满减", "店铺券", "优惠券", "跨店满减", "平台券", "券", "红包", "津贴", "补贴", "活动")
DOUYIN_APP_REQUIRED_KEYWORDS = ("前往抖音APP", "打开抖音APP", "可查看完整价格", "¥??? 起", "￥??? 起", "去抖音APP")
SOURCE_LABELS = {
    "页面明确券后价/到手价": ("explicit_final_price", "high"),
    "根据优惠估算价": ("estimated_after_discount", "medium"),
    "普通页面价": ("current_page_price_fallback", "low"),
    "手动确认价": ("manual_confirmed", "manual_confirmed"),
    "explicit_final_price": ("explicit_final_price", "high"),
    "estimated_after_discount": ("estimated_after_discount", "medium"),
    "current_page_price_fallback": ("current_page_price_fallback", "low"),
    "manual_confirmed": ("manual_confirmed", "manual_confirmed"),
}


def to_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            number = float(value)
        else:
            text = str(value).strip()
            text = "".join(
                str(ord(char) - ord("０")) if "０" <= char <= "９" else char
                for char in text
            )
            text = text.replace("￥", "").replace("¥", "").replace("元", "").replace(" ", "")
            text = text.replace("。", ".").replace("，", ",")
            if "," in text and "." not in text:
                parts = text.split(",")
                text = f"{parts[0]}.{parts[1]}" if len(parts) == 2 and len(parts[1]) <= 2 else text.replace(",", "")
            else:
                text = text.replace(",", "")
            match = re.search(r"\d+(?:\.\d+)?", text)
            if not match:
                return None
            number = float(match.group(0))
    except (TypeError, ValueError):
        return None
    return number if 0.01 < number <= 20000 else None


def reasonable_price(value: float | None, prefer: bool = False) -> bool:
    if value is None:
        return False
    if prefer:
        return 1 <= value <= 10000
    return 0.01 < value <= 20000


def nearby_context(text: str, start: int, end: int, radius: int = 8) -> str:
    return text[max(0, start - radius) : min(len(text), end + radius)]


def price_from_match(text: str, match: re.Match[str], group_index: int = 1) -> float | None:
    context = nearby_context(text, match.start(), match.end())
    if any(word in context for word in DANGEROUS_CONTEXT):
        return None
    if "?" in context or "？" in context:
        return None
    value = to_float(match.group(group_index))
    return value if reasonable_price(value) else None


def extract_prices(text: str) -> list[float]:
    prices: list[float] = []
    for match in MONEY_PATTERN.finditer(text or ""):
        value = price_from_match(text, match, 1)
        if value is not None and value not in prices:
            prices.append(value)
    return prices


def normalize_candidate(value: object) -> float | None:
    if isinstance(value, dict):
        value = value.get("value") or value.get("price") or value.get("text")
    if isinstance(value, (int, float)):
        return to_float(value)
    text = str(value or "")
    prices = extract_prices(text)
    return prices[0] if prices else None


def candidate_prices(price_candidates: Iterable | None) -> list[float]:
    prices: list[float] = []
    for candidate in price_candidates or []:
        value = normalize_candidate(candidate)
        if value is not None and value not in prices:
            prices.append(value)
    return prices


def first_explicit_final_price(text: str) -> float | None:
    for match in EXPLICIT_FINAL_PATTERN.finditer(text or ""):
        value = price_from_match(text, match, 2)
        if reasonable_price(value, prefer=True):
            return value
    return None


def first_current_price(text: str) -> float | None:
    for match in CURRENT_PRICE_PATTERN.finditer(text or ""):
        value = price_from_match(text, match, 2)
        if reasonable_price(value, prefer=True):
            return value
    prices = extract_prices(text)
    preferred = [price for price in prices if 1 <= price <= 10000]
    return min(preferred) if preferred else None


def extract_lines(text: str, keywords: tuple[str, ...], limit: int = 8) -> str | None:
    selected: list[str] = []
    for line in [line.strip() for line in (text or "").splitlines() if line.strip()]:
        if any(keyword in line for keyword in keywords):
            compact = re.sub(r"\s+", " ", line)
            if compact not in selected:
                selected.append(compact[:220])
        if len(selected) >= limit:
            break
    return " | ".join(selected) if selected else None


def estimate_discount_amount(text: str, current_price: float | None) -> float | None:
    if current_price is None:
        return None
    discounts: list[float] = []
    for threshold, reduction in FULL_REDUCTION_PATTERN.findall(text or ""):
        threshold_value = to_float(threshold)
        reduction_value = to_float(reduction)
        if threshold_value is not None and reduction_value is not None and current_price >= threshold_value:
            discounts.append(reduction_value)
    for reduction in DIRECT_DISCOUNT_PATTERN.findall(text or ""):
        reduction_value = to_float(reduction)
        if reduction_value is not None and 0 < reduction_value < current_price:
            discounts.append(reduction_value)
    return max(discounts) if discounts else None


def source_from_user_choice(user_price_source: str | None, has_manual_price: bool) -> tuple[str | None, str | None]:
    text = str(user_price_source or "").strip()
    if text in SOURCE_LABELS:
        return SOURCE_LABELS[text]
    if has_manual_price:
        return "manual_confirmed", "manual_confirmed"
    return None, None


def parse_price_text(
    visible_text: str,
    selected_text: str | None = None,
    price_candidates: list | None = None,
    manual_price: float | None = None,
    user_price_source: str | None = None,
) -> dict:
    visible = visible_text or ""
    selected = selected_text or ""
    combined = "\n".join(part for part in [selected, visible] if part)
    raw_price_text = extract_lines(combined, PRICE_LINE_KEYWORDS) or extract_lines(combined, ("¥", "￥"))
    discount_text = extract_lines(combined, DISCOUNT_KEYWORDS)
    hidden_price = any(keyword in combined for keyword in DOUYIN_APP_REQUIRED_KEYWORDS)

    manual = to_float(manual_price)
    if manual is not None:
        price_source, confidence = source_from_user_choice(user_price_source, has_manual_price=True)
        return {
            "current_price": manual,
            "final_price": manual,
            "raw_price_text": raw_price_text or selected or None,
            "discount_text": discount_text,
            "price_source": price_source or "manual_confirmed",
            "confidence": confidence or "manual_confirmed",
            "failure_reason": None,
        }

    selected_explicit = first_explicit_final_price(selected)
    selected_current = first_current_price(selected)
    user_source, user_confidence = source_from_user_choice(user_price_source, has_manual_price=False)
    if selected_current is not None and user_source:
        return {
            "current_price": selected_current,
            "final_price": selected_current,
            "raw_price_text": selected or raw_price_text,
            "discount_text": discount_text,
            "price_source": user_source,
            "confidence": user_confidence,
            "failure_reason": None,
        }
    if selected_explicit is not None:
        return {
            "current_price": selected_current or selected_explicit,
            "final_price": selected_explicit,
            "raw_price_text": selected or raw_price_text,
            "discount_text": discount_text,
            "price_source": "explicit_final_price",
            "confidence": "high",
            "failure_reason": None,
        }

    current_price = first_current_price(visible)
    explicit_final = first_explicit_final_price(visible)
    if explicit_final is not None:
        return {
            "current_price": current_price or explicit_final,
            "final_price": explicit_final,
            "raw_price_text": raw_price_text,
            "discount_text": discount_text,
            "price_source": "explicit_final_price",
            "confidence": "high",
            "failure_reason": None,
        }

    candidates = candidate_prices(price_candidates)
    if current_price is None and candidates:
        preferred = [price for price in candidates if 1 <= price <= 10000]
        current_price = min(preferred) if preferred else None

    discount = estimate_discount_amount(visible, current_price)
    if current_price is not None and discount:
        return {
            "current_price": current_price,
            "final_price": max(round(current_price - discount, 2), 0.01),
            "raw_price_text": raw_price_text,
            "discount_text": discount_text,
            "price_source": "estimated_after_discount",
            "confidence": "medium",
            "failure_reason": None,
        }

    if current_price is not None:
        return {
            "current_price": current_price,
            "final_price": current_price,
            "raw_price_text": raw_price_text,
            "discount_text": discount_text,
            "price_source": "current_page_price_fallback",
            "confidence": "low",
            "failure_reason": None,
        }

    return {
        "current_price": None,
        "final_price": None,
        "raw_price_text": raw_price_text,
        "discount_text": discount_text,
        "price_source": None,
        "confidence": None,
        "failure_reason": "douyin_app_required_price_hidden" if hidden_price else "price_not_found",
    }
