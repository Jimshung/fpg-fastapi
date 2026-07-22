"""台灣標售案篩選（排除大陸案）。

沿用先前寬鬆規則：
- 案號以數字開頭 → 視為台灣案
- 案號以字母開頭 → 需廠區電話符合台灣門號／市話格式才保留

另：已知大陸案號前綴（如 NA-）直接排除，即使電話誤判也不進 Notion。
"""
from __future__ import annotations

import re

from app.models.case_record import CaseRecord

# 已知大陸／非台灣案號前綴（可再補）
MAINLAND_PREFIXES = (
    "NA-",  # 使用者確認：NA-UT0CZ7 等
)

_MOBILE = re.compile(r"^09\d{2}-?\d{3}-?\d{3}$")
# 對齊先前 JS：/^0[2-8]-?\d{1,4}-?\d{3,4}(#\d+)?$/
# 略放寬分機為 (#\d*)?，相容「05-6815918#」這種尾端空白分機
_LANDLINE = re.compile(r"^0[2-8]-?\d{1,4}-?\d{3,4}(#\d*)?$", re.I)


def normalize_phone(number: str) -> str:
    return re.sub(r"\s+", "", (number or "").strip())


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
