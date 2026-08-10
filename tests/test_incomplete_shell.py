"""空殼判定與 Telegram digest 警示：不需網路。

用法:
  python -m tests.test_incomplete_shell
"""
from __future__ import annotations

import sys

from app.models.case_record import CaseRecord, QuoteItem
from app.utils.telegram_digest import build_fpg_digest


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    shell = CaseRecord(tndsalno="01-UT1VS5", inqcnt="01")
    _assert(shell.is_incomplete_shell, "bare case should be shell")
    _assert(shell.mark_incomplete_shell(), "mark should return True")
    _assert(shell.status == "error", shell.status)
    _assert("空殼" in shell.error, shell.error)

    ok = CaseRecord(
        tndsalno="01-UTAAAA",
        inqcnt="01",
        quote_deadline="2026-08-11",
        plant_contact="吳杰懋",
        location="PP倉儲二場",
        items=[QuoteItem(description="預熱器", quantity="1 ST")],
    )
    _assert(not ok.is_incomplete_shell, "complete case must not be shell")
    _assert(not ok.mark_incomplete_shell(), "mark complete should be False")
    _assert(ok.status == "new", ok.status)

    with_deadline_only = CaseRecord(
        tndsalno="01-UTBBBB",
        inqcnt="01",
        quote_deadline="2026-08-11",
    )
    _assert(
        not with_deadline_only.is_incomplete_shell,
        "deadline alone is enough to show in Notion filter",
    )

    digest = build_fpg_digest(
        announce_label="2026/08/04",
        records=[shell, ok],
        page_urls=[None, "https://notion.so/x"],
        ok=1,
        err=1,
        elapsed_s=12.0,
        shells=[shell],
    )
    _assert(digest.startswith("❌"), digest)
    _assert("FPG 標售歸檔" in digest, digest)
    _assert("空殼未寫入 Notion" in digest, digest)
    _assert("01-UT1VS5/01" in digest, digest)
    _assert("01-UTAAAA/01" in digest, digest)
    _assert("notion.so/x" in digest, digest)

    ok_only = build_fpg_digest(
        announce_label="2026/08/04",
        records=[ok],
        page_urls=["https://notion.so/x"],
        ok=1,
        err=0,
        elapsed_s=12.0,
        shells=[],
    )
    _assert(ok_only.startswith("✅"), ok_only)

    print("OK: incomplete shell / digest 單元測試通過")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
