from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zipfile import ZipFile

import pandas as pd

from config import PRODUCTS_PATH, SUPPORTED_PLATFORMS


REQUIRED_COLUMNS = ["platform", "name", "url", "target_price"]
OPTIONAL_DEFAULTS = {
    "id": "",
    "category": "",
    "brand": "",
    "enabled": True,
    "promo_name": "",
    "promo_start": "",
    "promo_end": "",
    "require_final_price": False,
    "note": "",
}
OUTPUT_COLUMNS = [
    "id",
    "category",
    "brand",
    "platform",
    "name",
    "url",
    "target_price",
    "enabled",
    "promo_name",
    "promo_start",
    "promo_end",
    "require_final_price",
    "note",
    "item_id",
    "normalized_url",
]
XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
BLOCKED_LINK_PATTERN = re.compile(
    r"(?:^https?://)?(?:3\.cn|[^/]*jd\.com|[^/]*pinduoduo\.com|[^/]*yangkeduo\.com)",
    re.IGNORECASE,
)
DOUYIN_ID_PATTERNS = (
    re.compile(r"(?:item_id|product_id|goods_id)=([A-Za-z0-9_-]+)", re.IGNORECASE),
    re.compile(r"/(?:item|product|goods)/([A-Za-z0-9_-]+)", re.IGNORECASE),
)


def find_product_file(path: str | Path | None = None) -> Path:
    candidate = Path(path) if path else PRODUCTS_PATH
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Product file not found: {candidate}")


def parse_bool(value: object, default: bool) -> bool:
    if pd.isna(value):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"true", "t", "yes", "y", "1", "是", "启用"}:
        return True
    if text in {"false", "f", "no", "n", "0", "否", "停用"}:
        return False
    return default


def detect_platform_from_url(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    if any(domain in host for domain in ("taobao.com", "tmall.com", "tmall.hk")):
        return "淘宝"
    if any(domain in host for domain in ("douyin.com", "jinritemai.com")):
        return "抖音"
    return None


def canonical_platform(value: object, url: str = "") -> str:
    text = str(value or "").strip().lower()
    if text in {"淘宝", "taobao", "tmall", "天猫", "天猫国际", "tmall hk", "tmall.hk"}:
        return "淘宝"
    if text in {"抖音", "douyin", "jinritemai", "抖音电商"}:
        return "抖音"
    return detect_platform_from_url(url) or str(value or "").strip()


def normalize_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return str(url or "").strip()
    host = parsed.netloc.lower()
    query = parse_qs(parsed.query)
    keep: dict[str, str] = {}
    for key in ("id", "item_id", "product_id", "goods_id"):
        if query.get(key):
            keep[key] = query[key][0]
    if keep:
        query_text = "&".join(f"{key}={value}" for key, value in sorted(keep.items()))
        return f"{parsed.scheme}://{host}{parsed.path}?{query_text}"
    return f"{parsed.scheme}://{host}{parsed.path}".rstrip("/")


def extract_item_id(url: str, platform: str | None = None) -> str:
    parsed = urlparse(str(url or "").strip())
    query = parse_qs(parsed.query)
    if query.get("id"):
        return query["id"][0]
    for key in ("item_id", "product_id", "goods_id"):
        if query.get(key):
            return query[key][0]
    for pattern in DOUYIN_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return ""


def compact_text(value: object) -> str:
    text = re.sub(r"\s+", "", str(value or "").lower())
    return re.sub(r"[^\w\u4e00-\u9fff]", "", text)


def read_csv_file(path: Path) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    return pd.read_csv(path)


def read_excel_file(path: Path) -> pd.DataFrame:
    try:
        return pd.read_excel(path)
    except ImportError:
        if path.suffix.lower() != ".xlsx":
            raise
        return read_xlsx_without_openpyxl(path)


def xlsx_column_index(cell_ref: str) -> int:
    letters = "".join(re.findall(r"[A-Z]+", cell_ref))
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - ord("A") + 1
    return index - 1


def read_xlsx_without_openpyxl(path: Path) -> pd.DataFrame:
    with ZipFile(path) as archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", XLSX_NS):
                shared_strings.append("".join(text.text or "" for text in item.findall(".//a:t", XLSX_NS)))

        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in root.findall(".//a:sheetData/a:row", XLSX_NS):
            values = []
            for cell in row.findall("a:c", XLSX_NS):
                index = xlsx_column_index(cell.attrib.get("r", "A1"))
                while len(values) <= index:
                    values.append("")
                raw_value = cell.find("a:v", XLSX_NS)
                if raw_value is None:
                    value = ""
                elif cell.attrib.get("t") == "s":
                    value = shared_strings[int(raw_value.text or "0")]
                else:
                    value = raw_value.text or ""
                values[index] = value
            rows.append(values)

    if not rows:
        return pd.DataFrame()
    headers = [str(header).strip() for header in rows[0]]
    data = []
    for row in rows[1:]:
        row.extend([""] * (len(headers) - len(row)))
        data.append(row[: len(headers)])
    return pd.DataFrame(data, columns=headers)


def load_products(path: str | Path | None = None) -> pd.DataFrame:
    product_file = find_product_file(path)
    suffix = product_file.suffix.lower()
    if suffix == ".csv":
        df = read_csv_file(product_file)
    elif suffix in {".xlsx", ".xls"}:
        df = read_excel_file(product_file)
    else:
        raise ValueError(f"Unsupported product file format: {product_file.suffix}")

    df.columns = [str(column).strip() for column in df.columns]
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    for column, default in OPTIONAL_DEFAULTS.items():
        if column not in df.columns:
            df[column] = default

    df["url"] = df["url"].where(df["url"].notna(), "").astype(str).str.strip()
    df["platform"] = [canonical_platform(platform, url) for platform, url in zip(df["platform"], df["url"])]
    df = df[df["platform"].isin(SUPPORTED_PLATFORMS)].copy()
    df = df[~df["url"].str.contains(BLOCKED_LINK_PATTERN, regex=True, na=False)].copy()

    df["enabled"] = df["enabled"].apply(lambda value: parse_bool(value, default=True))
    df = df[df["enabled"]].copy()
    df["require_final_price"] = df["require_final_price"].apply(lambda value: parse_bool(value, default=False))
    df["target_price"] = pd.to_numeric(df["target_price"], errors="coerce")
    invalid_targets = df[df["target_price"].isna()]
    if not invalid_targets.empty:
        names = ", ".join(str(value) for value in invalid_targets["name"].head(5))
        raise ValueError(f"Invalid target_price for active products: {names}")

    for column in ["id", "category", "brand", "name", "note", "promo_name", "promo_start", "promo_end"]:
        df[column] = df[column].where(df[column].notna(), "").astype(str).str.strip()
        df[column] = df[column].replace({"nan": "", "NaT": "", "None": ""})

    df = df[df["url"] != ""].copy()
    df["item_id"] = [extract_item_id(url, platform) for url, platform in zip(df["url"], df["platform"])]
    df["normalized_url"] = df["url"].apply(normalize_url)
    for index, row_index in enumerate(df.index, start=1):
        if not str(df.at[row_index, "id"] or "").strip():
            df.at[row_index, "id"] = str(index)
    return df[OUTPUT_COLUMNS].reset_index(drop=True)


def find_matching_product(products: pd.DataFrame, url: str, page_title: str = "") -> dict | None:
    platform = detect_platform_from_url(url) or ""
    item_id = extract_item_id(url, platform)
    normalized = normalize_url(url)
    candidates = products.copy()
    if platform:
        candidates = candidates[candidates["platform"] == platform]

    if item_id:
        by_item = candidates[candidates["item_id"].astype(str) == str(item_id)]
        if not by_item.empty:
            return by_item.iloc[0].to_dict()

    by_url = candidates[candidates["normalized_url"].astype(str) == normalized]
    if not by_url.empty:
        return by_url.iloc[0].to_dict()

    title_key = compact_text(page_title)
    if title_key:
        best_score = 0.0
        best_row = None
        for _, row in candidates.iterrows():
            name_key = compact_text(row.get("name"))
            if not name_key:
                continue
            if name_key in title_key or title_key in name_key:
                score = 1.0
            else:
                score = SequenceMatcher(None, name_key, title_key).ratio()
            if score > best_score:
                best_score = score
                best_row = row
        if best_row is not None and best_score >= 0.45:
            return best_row.to_dict()

    return None


def append_product(product: dict, path: str | Path = PRODUCTS_PATH) -> None:
    product_file = Path(path)
    row = {column: product.get(column, "") for column in OUTPUT_COLUMNS if column not in {"item_id", "normalized_url"}}
    new_row = pd.DataFrame([row])
    if product_file.exists():
        existing = read_excel_file(product_file) if product_file.suffix.lower() in {".xlsx", ".xls"} else read_csv_file(product_file)
        combined = pd.concat([existing, new_row], ignore_index=True)
    else:
        combined = new_row
    if product_file.suffix.lower() in {".xlsx", ".xls"}:
        combined.to_excel(product_file, index=False)
    else:
        combined.to_csv(product_file, index=False, encoding="utf-8-sig")
