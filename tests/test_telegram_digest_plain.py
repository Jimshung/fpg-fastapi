"""Telegram digest 純文字：品名含 < > 不可變成 HTML。"""
from __future__ import annotations

from app.models.case_record import CaseRecord, QuoteItem
from app.utils.telegram_digest import build_fpg_digest


def test_angle_brackets_in_summary_stay_literal() -> None:
    record = CaseRecord(
        tndsalno="02-UT27R1",
        inqcnt="01",
        quote_deadline="2026-09-25",
        plant_contact="測試",
        location="廠區",
        items=[QuoteItem(description="<PBT工程塑膠鏌頭料> 規格A", quantity="1 ST")],
    )
    digest = build_fpg_digest(
        announce_label="2026/09/18",
        records=[record],
        page_urls=["https://notion.so/example"],
        ok=1,
        err=0,
        elapsed_s=10,
        shells=[],
    )
    assert "<b>" not in digest
    assert "<a " not in digest
    assert "&lt;" not in digest
    assert "<PBT" in digest or "PBT工程" in digest
    assert "Notion: https://notion.so/example" in digest
    assert digest.startswith("✅")
