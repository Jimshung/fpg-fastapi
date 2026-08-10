"""公告日空白補齊：不需網路的單元測試。

用法:
  python -m tests.test_announce_date_fallback
"""
from __future__ import annotations

import sys

from app.models.case_record import CaseRecord
from app.services.fpg_parser import fill_missing_announce_dates


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    # 1) 單一公告日：空白應被補上；已有值不動
    records = [
        CaseRecord(tndsalno="01-UTAAAA", inqcnt="01", announce_date=""),
        CaseRecord(tndsalno="01-UTBBBB", inqcnt="01", announce_date="2026-07-27"),
        CaseRecord(tndsalno="01-UTCCCC", inqcnt="01"),
    ]
    filled = fill_missing_announce_dates(records, "2026/07/27", "2026/07/27")
    _assert(filled == 2, f"expected filled=2, got {filled}")
    _assert(records[0].announce_date == "2026-07-27", records[0].announce_date)
    _assert(records[1].announce_date == "2026-07-27", records[1].announce_date)
    _assert(records[2].announce_date == "2026-07-27", records[2].announce_date)

    # 2) 多日區間：不亂填（避免填錯日）
    multi = [CaseRecord(tndsalno="02-UTXXXX", inqcnt="01", announce_date="")]
    filled_multi = fill_missing_announce_dates(
        multi, "2026/07/27", "2026/07/28"
    )
    _assert(filled_multi == 0, f"expected filled=0 for range, got {filled_multi}")
    _assert(multi[0].announce_date == "", "range search must not invent date")

    # 3) ISO 輸入也可
    iso_cases = [CaseRecord(tndsalno="03-UTYYYY", inqcnt="01")]
    filled_iso = fill_missing_announce_dates(
        iso_cases, "2026-07-28", "2026-07-28"
    )
    _assert(filled_iso == 1, f"expected filled=1, got {filled_iso}")
    _assert(iso_cases[0].announce_date == "2026-07-28", iso_cases[0].announce_date)

    print("OK: fill_missing_announce_dates 單元測試通過")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
