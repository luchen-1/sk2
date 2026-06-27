from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from db import DB_PATH, get_connection, init_db
from product_io import append_product, load_products


PROJECT_PRODUCTS_PATH = Path("products.xlsx")
NOT_FETCHED = "\u672a\u83b7\u53d6"

st.set_page_config(page_title="\u62a4\u80a4\u54c1\u4ef7\u683c\u76d1\u63a7", layout="wide")

st.markdown(
    """
    <style>
    .stApp { background: #f6faf9; }
    [data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #e5e7eb; }
    .hero {
        padding: 22px 26px;
        border: 1px solid #d8e7e3;
        border-radius: 8px;
        background: #ffffff;
        margin-bottom: 18px;
    }
    .hero h1 { margin: 0 0 8px 0; color: #14332e; font-size: 30px; letter-spacing: 0; }
    .hero p { margin: 0; color: #52615e; font-size: 15px; }
    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 14px 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def default_products_path() -> Path:
    return PROJECT_PRODUCTS_PATH


def load_history(db_path: Path = DB_PATH) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(db_path)
    try:
        return pd.read_sql_query("SELECT * FROM price_history ORDER BY checked_at DESC", conn)
    finally:
        conn.close()


def latest_snapshot(products: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    base = products.copy()
    if history.empty:
        for column in [
            "original_price",
            "current_price",
            "coupon_text",
            "promotion_text",
            "raw_price_text",
            "discount_text",
            "final_price",
            "price_source",
            "confidence",
            "is_below_target",
            "meets_target_price",
            "is_promo_period",
            "promo_name",
            "screenshot_path",
            "failure_reason",
            "error_message",
            "last_checked_at",
            "error",
        ]:
            base[column] = None
        base["history_low_final_price"] = None
        return base

    hist = history.copy()
    if "final_price" not in hist.columns:
        hist["final_price"] = None
    latest = hist.sort_values("checked_at").groupby("url", as_index=False).tail(1)
    latest = latest.rename(columns={"checked_at": "last_checked_at"})
    lows = (
        hist.dropna(subset=["final_price"])
        .groupby("url", as_index=False)["final_price"]
        .min()
        .rename(columns={"final_price": "history_low_final_price"})
    )
    keep = [
        "url",
        "original_price",
        "current_price",
        "coupon_text",
        "promotion_text",
        "raw_price_text",
        "discount_text",
        "final_price",
        "price_source",
        "confidence",
        "is_below_target",
        "meets_target_price",
        "is_promo_period",
        "promo_name",
        "screenshot_path",
        "failure_reason",
        "error_message",
        "last_checked_at",
        "error",
    ]
    for column in keep:
        if column not in latest.columns:
            latest[column] = None
    return base.merge(latest[keep], on="url", how="left").merge(lows, on="url", how="left")


def format_price(value: object) -> str:
    if pd.isna(value):
        return NOT_FETCHED
    try:
        return f"\u00a5{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def format_price_source(value: object) -> str:
    labels = {
        "explicit_final_price": "\u9875\u9762\u5238\u540e\u4ef7",
        "estimated_after_discount": "\u4f18\u60e0\u4f30\u7b97\u4ef7",
        "current_page_price_fallback": "\u5f53\u524d\u9875\u9762\u4ef7",
    }
    if pd.isna(value):
        return NOT_FETCHED
    return labels.get(str(value), str(value))


def format_confidence(value: object) -> str:
    labels = {"high": "\u9ad8", "medium": "\u4e2d", "low": "\u4f4e"}
    if pd.isna(value):
        return NOT_FETCHED
    return labels.get(str(value), str(value))


def format_yes_no(value: object) -> str:
    if pd.isna(value):
        return "\u5426"
    return "\u662f" if str(value).strip().lower() in {"1", "true", "yes", "\u662f"} else "\u5426"


def distribution_frame(data: pd.DataFrame, column: str) -> pd.DataFrame:
    if data.empty or column not in data.columns:
        return pd.DataFrame(columns=[column, "\u6570\u91cf"])
    series = data[column].fillna("none").replace({"": "none"})
    return series.value_counts().rename_axis(column).reset_index(name="\u6570\u91cf")


def platform_success_frame(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame(columns=["\u5e73\u53f0", "\u6210\u529f", "\u603b\u6570", "\u6210\u529f\u7387"])
    grouped = data.groupby("platform", dropna=False)
    rows = []
    for platform, group in grouped:
        total_count = len(group)
        success_count = int(group["final_price"].notna().sum())
        rows.append(
            {
                "\u5e73\u53f0": platform,
                "\u6210\u529f": success_count,
                "\u603b\u6570": total_count,
                "\u6210\u529f\u7387": f"{(success_count / total_count * 100):.1f}%" if total_count else "0.0%",
            }
        )
    return pd.DataFrame(rows)


def build_display(snapshot: pd.DataFrame) -> pd.DataFrame:
    display = snapshot.copy()
    target_column = "meets_target_price" if "meets_target_price" in display.columns else "is_below_target"
    display["\u662f\u5426\u8fbe\u5230\u5fc3\u7406\u4ef7"] = display[target_column].fillna(0).astype(int).map(
        {1: "\u662f", 0: "\u5426"}
    )
    display.loc[display["final_price"].isna(), "\u662f\u5426\u8fbe\u5230\u5fc3\u7406\u4ef7"] = NOT_FETCHED
    display["\u76d1\u63a7\u4ef7"] = display["final_price"].apply(format_price)
    display["\u5f53\u524d\u9875\u9762\u4ef7"] = display["current_price"].apply(format_price)
    display["\u539f\u4ef7"] = display["original_price"].apply(format_price)
    display["\u5fc3\u7406\u4ef7"] = display["target_price"].apply(format_price)
    display["\u5386\u53f2\u6700\u4f4e\u76d1\u63a7\u4ef7"] = display["history_low_final_price"].apply(format_price)
    display["\u6700\u8fd1\u68c0\u67e5\u65f6\u95f4"] = display["last_checked_at"].fillna(NOT_FETCHED)
    display["\u4f18\u60e0\u5238"] = display["coupon_text"].fillna("")
    display["\u6d3b\u52a8/\u6ee1\u51cf"] = display["promotion_text"].fillna("")
    display["\u4ef7\u683c\u4f9d\u636e"] = display["price_source"].apply(format_price_source)
    display["\u53ef\u4fe1\u5ea6"] = display["confidence"].apply(format_confidence)
    display["\u662f\u5426\u5927\u4fc3\u671f\u95f4"] = display["is_promo_period"].apply(format_yes_no)
    display["\u6d3b\u52a8\u540d\u79f0"] = display["promo_name"].fillna("")
    display["\u539f\u59cb\u4ef7\u683c\u6587\u672c"] = display["raw_price_text"].fillna("")
    display["\u4f18\u60e0\u8bc1\u636e"] = display["discount_text"].fillna("")
    display["\u622a\u56fe\u8def\u5f84"] = display["screenshot_path"].fillna("")
    display["failure_reason"] = display["failure_reason"].fillna("")
    display["error_message"] = display["error_message"].fillna("")
    return display[
        [
            "category",
            "brand",
            "platform",
            "name",
            "\u76d1\u63a7\u4ef7",
            "\u5fc3\u7406\u4ef7",
            "\u662f\u5426\u8fbe\u5230\u5fc3\u7406\u4ef7",
            "\u4ef7\u683c\u4f9d\u636e",
            "\u53ef\u4fe1\u5ea6",
            "\u662f\u5426\u5927\u4fc3\u671f\u95f4",
            "\u6d3b\u52a8\u540d\u79f0",
            "\u5386\u53f2\u6700\u4f4e\u76d1\u63a7\u4ef7",
            "\u5f53\u524d\u9875\u9762\u4ef7",
            "\u539f\u4ef7",
            "\u4f18\u60e0\u5238",
            "\u6d3b\u52a8/\u6ee1\u51cf",
            "\u539f\u59cb\u4ef7\u683c\u6587\u672c",
            "\u4f18\u60e0\u8bc1\u636e",
            "\u622a\u56fe\u8def\u5f84",
            "failure_reason",
            "error_message",
            "\u6700\u8fd1\u68c0\u67e5\u65f6\u95f4",
            "error",
            "url",
        ]
    ].rename(
        columns={
            "category": "\u5206\u7c7b",
            "brand": "\u54c1\u724c",
            "platform": "\u5e73\u53f0",
            "name": "\u5546\u54c1\u540d",
            "error": "\u9519\u8bef",
            "url": "\u94fe\u63a5",
        }
    )


with get_connection() as conn:
    init_db(conn)

st.markdown(
    """
    <div class="hero">
      <h1>护肤品价格实时监控</h1>
      <p>优先读取券后到手价；抓不到时用页面价兜底，并展示可信度、大促状态和页面证据。</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("\u6570\u636e\u6e90")
    products_path_text = st.text_input("\u5546\u54c1\u6e05\u5355\u8def\u5f84", value=str(default_products_path()))
    products_path = Path(products_path_text.strip('"').strip())

    st.divider()
    st.header("\u8ffd\u52a0\u5546\u54c1")
    with st.form("add_product"):
        category = st.text_input("\u5206\u7c7b")
        brand = st.text_input("\u54c1\u724c")
        platform = st.text_input("\u5e73\u53f0")
        name = st.text_input("\u5546\u54c1\u540d")
        url = st.text_area("\u5546\u54c1\u94fe\u63a5", height=80)
        target_price = st.number_input("\u5fc3\u7406\u4ef7", min_value=0.0, step=1.0)
        promo_name = st.text_input("\u6d3b\u52a8\u540d\u79f0")
        promo_start = st.text_input("\u6d3b\u52a8\u5f00\u59cb\u65f6\u95f4")
        promo_end = st.text_input("\u6d3b\u52a8\u7ed3\u675f\u65f6\u95f4")
        require_final_price = st.toggle("\u8981\u6c42\u660e\u786e\u5238\u540e\u4ef7", value=False)
        enabled = st.toggle("\u542f\u7528", value=True)
        note = st.text_input("\u5907\u6ce8")
        submitted = st.form_submit_button("\u8ffd\u52a0\u5230\u5f53\u524d\u6e05\u5355")

    if submitted:
        if not name.strip() or not url.strip():
            st.error("\u5546\u54c1\u540d\u548c\u94fe\u63a5\u4e0d\u80fd\u4e3a\u7a7a\u3002")
        else:
            append_product(
                {
                    "category": category.strip(),
                    "brand": brand.strip(),
                    "platform": platform.strip(),
                    "name": name.strip(),
                    "url": url.strip(),
                    "target_price": target_price,
                    "promo_name": promo_name.strip(),
                    "promo_start": promo_start.strip(),
                    "promo_end": promo_end.strip(),
                    "require_final_price": require_final_price,
                    "enabled": enabled,
                    "note": note.strip(),
                },
                products_path,
            )
            st.success("\u5df2\u8ffd\u52a0\u5230\u5f53\u524d\u5546\u54c1\u6e05\u5355\u3002")

try:
    products = load_products(str(products_path))
except Exception as exc:
    st.error(f"\u8bfb\u53d6\u5546\u54c1\u6e05\u5355\u5931\u8d25: {exc}")
    st.stop()

history = load_history()
snapshot = latest_snapshot(products, history)

platform_options = sorted([value for value in snapshot["platform"].dropna().unique()])
price_source_options = sorted([value for value in snapshot["price_source"].dropna().unique()])
confidence_options = sorted([value for value in snapshot["confidence"].dropna().unique()])

filter_col1, filter_col2, filter_col3, filter_col4, filter_col5 = st.columns([1, 1, 1, 1, 1])
selected_platforms = filter_col1.multiselect("\u5e73\u53f0", platform_options, default=platform_options)
selected_price_sources = filter_col2.multiselect("price_source", price_source_options, default=price_source_options)
selected_confidences = filter_col3.multiselect("confidence", confidence_options, default=confidence_options)
only_hits = filter_col4.toggle("\u53ea\u770b\u4f4e\u4e8e\u5fc3\u7406\u4ef7", value=False)
only_promo = filter_col5.toggle("\u53ea\u770b\u5927\u4fc3\u671f\u95f4", value=False)

filtered = snapshot.copy()
if selected_platforms:
    filtered = filtered[filtered["platform"].isin(selected_platforms)]
if selected_price_sources:
    filtered = filtered[filtered["price_source"].isin(selected_price_sources)]
if selected_confidences:
    filtered = filtered[filtered["confidence"].isin(selected_confidences)]
if only_hits:
    target_column = "meets_target_price" if "meets_target_price" in filtered.columns else "is_below_target"
    filtered = filtered[filtered[target_column].fillna(0).astype(int) == 1]
if only_promo:
    filtered = filtered[filtered["is_promo_period"].fillna(0).astype(int) == 1]

total = len(snapshot)
final_count = int(snapshot["final_price"].notna().sum()) if total else 0
target_metric_column = "meets_target_price" if "meets_target_price" in snapshot.columns else "is_below_target"
hit_count = int(snapshot[target_metric_column].fillna(0).astype(int).sum()) if total else 0
lowest_final = snapshot["history_low_final_price"].dropna().min() if "history_low_final_price" in snapshot else None

metric1, metric2, metric3, metric4 = st.columns(4)
metric1.metric("\u5546\u54c1\u6570", total)
metric2.metric("\u5df2\u83b7\u53d6\u76d1\u63a7\u4ef7", final_count)
metric3.metric("\u8fbe\u5230\u5fc3\u7406\u4ef7", hit_count)
metric4.metric("\u5386\u53f2\u6700\u4f4e\u76d1\u63a7\u4ef7", format_price(lowest_final))

st.subheader("\u8fd0\u884c\u6982\u89c8")
overview1, overview2, overview3, overview4 = st.columns(4)
overview1.dataframe(platform_success_frame(snapshot), use_container_width=True, hide_index=True)
overview2.dataframe(distribution_frame(snapshot, "price_source"), use_container_width=True, hide_index=True)
overview3.dataframe(distribution_frame(snapshot, "confidence"), use_container_width=True, hide_index=True)
overview4.dataframe(distribution_frame(snapshot, "failure_reason"), use_container_width=True, hide_index=True)

reports_dir = Path("reports")
recent_reports = sorted(reports_dir.glob("price_check_report_*.md"), key=lambda path: path.stat().st_mtime, reverse=True)[:5]
if recent_reports:
    st.subheader("\u6700\u8fd1\u62a5\u544a")
    for report in recent_reports:
        st.markdown(f"- [{report.name}](<{report.resolve()}>)")

st.subheader("\u5546\u54c1\u4ef7\u683c\u76d1\u63a7")
st.dataframe(
    build_display(filtered),
    use_container_width=True,
    hide_index=True,
    column_config={"\u94fe\u63a5": st.column_config.LinkColumn("\u94fe\u63a5", display_text="\u6253\u5f00")},
)

if not history.empty:
    st.subheader("\u5386\u53f2\u8bb0\u5f55")
    show = history.head(100).copy()
    for column in ["original_price", "current_price", "final_price", "target_price"]:
        if column in show:
            show[column] = show[column].apply(format_price)
    st.dataframe(
        show,
        use_container_width=True,
        hide_index=True,
        column_config={"url": st.column_config.LinkColumn("url", display_text="\u6253\u5f00")},
    )
else:
    st.info("\u8fd8\u6ca1\u6709\u5386\u53f2\u8bb0\u5f55\uff0c\u5148\u8fd0\u884c\u4e00\u6b21 main.py \u6293\u4ef7\u3002")

st.caption(
    "\u76d1\u63a7\u4ef7\u4f18\u5148\u4f7f\u7528\u5238\u540e\u5230\u624b\u4ef7\uff0c\u6293\u4e0d\u5230\u65f6\u4f7f\u7528\u5f53\u524d\u9875\u9762\u4ef7\uff1b"
    "\u5927\u4fc3\u671f\u95f4\u4e14\u8981\u6c42\u660e\u786e\u5238\u540e\u4ef7\u65f6\uff0c\u4f4e\u53ef\u4fe1\u9875\u9762\u4ef7\u53ea\u8bb0\u5f55\u4e0d\u53d1\u5f3a\u63d0\u9192\u3002"
)
