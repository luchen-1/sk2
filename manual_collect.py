from __future__ import annotations

from datetime import datetime

from config import configure_console
from local_collector import is_promo_period
from parsers.price_parser import to_float
from product_io import load_products
from storage.db import get_connection, init_db, insert_price_record


def main() -> None:
    configure_console()
    products = load_products("products.xlsx")
    if products.empty:
        print("products.xlsx 中没有可用商品。")
        return

    print("请选择要手动录入价格的商品：")
    for index, product in enumerate(products.to_dict("records"), start=1):
        print(f"{index}. {product.get('platform')} - {product.get('name')}  心理价={product.get('target_price')}")

    raw_index = input("输入序号: ").strip()
    try:
        selected_index = int(raw_index)
        product = products.iloc[selected_index - 1].to_dict()
    except Exception:
        print("序号无效。")
        return

    raw_price = input("输入当前看到的到手价/券后价: ").strip()
    price = to_float(raw_price)
    if price is None:
        print("价格无效。")
        return

    now = datetime.now().isoformat(timespec="seconds")
    target_price = to_float(product.get("target_price"))
    record = {
        "product_id": str(product.get("id") or ""),
        "product_name": product.get("name") or "",
        "category": product.get("category") or "",
        "brand": product.get("brand") or "",
        "platform": product.get("platform") or "",
        "url": product.get("url") or "",
        "normalized_url": product.get("normalized_url") or "",
        "item_id": product.get("item_id") or "",
        "page_title": "",
        "current_price": price,
        "final_price": price,
        "target_price": target_price,
        "price_source": "manual_confirmed",
        "confidence": "manual_confirmed",
        "meets_target_price": target_price is not None and price <= target_price,
        "require_final_price": bool(product.get("require_final_price")),
        "is_promo_period": is_promo_period(product),
        "promo_name": product.get("promo_name") or "",
        "raw_price_text": f"manual_price={price}",
        "discount_text": "",
        "selected_text": "",
        "manual_price": price,
        "source_type": "manual_input",
        "failure_reason": None,
        "error_message": None,
        "collected_at": now,
        "created_at": now,
        "checked_at": now,
        "stale": False,
        "alert_sent": False,
    }

    with get_connection() as conn:
        init_db(conn)
        insert_price_record(conn, record)
    print(f"已录入: {record['platform']} - {record['product_name']} final_price={price}")


if __name__ == "__main__":
    main()
