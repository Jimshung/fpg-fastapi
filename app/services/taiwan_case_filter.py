"""台灣標售案篩選（排除大陸案）。

沿用先前寬鬆規則：
- 案號以數字開頭 → 視為台灣案
- 案號以字母開頭 → 需廠區電話符合台灣門號／市話格式才保留

另：已知大陸案號前綴（如 NA-）直接排除，即使電話誤判也不進 Notion。

電話會先正規化：全形→半形、去空白、分機／ext → #、誤用 -分機 → #分機。
"""
from __future__ import annotations

import re
import unicodedata

from app.models.case_record import CaseRecord

# 已知大陸／非台灣案號前綴（可再補）
MAINLAND_PREFIXES = (
    "NA-",  # 使用者確認：NA-UT0CZ7 等
)

_MOBILE = re.compile(r"^09\d{2}-?\d{3}-?\d{3}$")
# 對齊先前 JS：/^0[2-8]-?\d{1,4}-?\d{3,4}(#\d+)?$/
# 略放寬分機為 (#\d*)?，相容「05-6815918#」這種尾端空白分機
_LANDLINE = re.compile(r"^0[2-8]-?\d{1,4}-?\d{3,4}(#\d*)?$", re.I)

# 市話主號後誤用「-分機」：04-26992900-362 → 04-26992900#362
_HYPHEN_EXT = re.compile(
    r"^(0[2-8]-?\d{6,10})-(\d{1,5})$",
    re.I,
)
_EXT_LABEL = re.compile(
    r"(?:分機|ext\.?)\s*(\d{1,5})\s*$",
    re.I,
)


def normalize_phone(number: str) -> str:
    """清洗廠區電話，方便台灣門號判斷與入庫。

    - 全形數字／符號 → 半形（NFKC）
    - 去掉空白
    - 「分機362」「ext.362」→「#362」
    - 「04-26992900-362」這類尾段誤用連字號分機 →「#362」
    """
    raw = unicodedata.normalize("NFKC", (number or "")).strip()
    raw = re.sub(r"\s+", "", raw)
    if not raw:
        return ""

    # 已有 #分機則先保留；標籤寫法收成 #
    labeled = _EXT_LABEL.search(raw)
    if labeled:
        raw = raw[: labeled.start()] + "#" + labeled.group(1)

    # 尾段 -分機（僅在尚無 # 時）
    if "#" not in raw:
        hyphen = _HYPHEN_EXT.match(raw)
        if hyphen:
            raw = f"{hyphen.group(1)}#{hyphen.group(2)}"

    return raw


def is_taiwan_phone_number(number: str) -> bool:
    number = normalize_phone(number)
    if not number:
        return False
    return bool(_MOBILE.match(number) or _LANDLINE.match(number))


def is_taiwan_sale(tndsalno: str, phone_number: str) -> bool:
    """對應先前 isTaiwanSale(rowId, phoneNumber)。"""
    row_id = (tndsalno or "").strip()
    if not row_id:
        return False
    upper = row_id.upper()
    if any(upper.startswith(prefix) for prefix in MAINLAND_PREFIXES):
        return False
    if re.match(r"^\d", row_id):
        return True
    if re.match(r"^[A-Za-z]", row_id):
        return is_taiwan_phone_number(phone_number)
    return False


def is_taiwan_case(record: CaseRecord) -> bool:
    if record.plant_phone:
        record.plant_phone = normalize_phone(record.plant_phone)
    return is_taiwan_sale(record.tndsalno, record.plant_phone)


def filter_taiwan_cases(
    records: list[CaseRecord],
) -> tuple[list[CaseRecord], list[CaseRecord]]:
    """回傳 (台灣案, 被排除的大陸／非台灣案)。"""
    kept: list[CaseRecord] = []
    skipped: list[CaseRecord] = []
    for record in records:
        if is_taiwan_case(record):
            kept.append(record)
        else:
            skipped.append(record)
    return kept, skipped
