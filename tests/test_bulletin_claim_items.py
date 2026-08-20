"""公報轉報價 checkbox 解析：不需網路。"""
from __future__ import annotations

from app.services.fpg_parser import parse_bulletin_claim_items


def test_parse_claim_items_dedupes_and_splits() -> None:
    html = """
    <input type="checkbox" name="item" value="75708007,01-UT1VV5,01" onClick='goCheck(this.form,this)'>
    <input type="checkbox" name="item" value="75708007,01-UT1VV5,01">
    <input type="checkbox" value="75708007,03-UT1H91,02" name="item">
    <input type="checkbox" name="other" value="75708007,XX-UT0000,01">
    """
    items = parse_bulletin_claim_items(html)
    assert items == [
        ("75708007", "01-UT1VV5", "01"),
        ("75708007", "03-UT1H91", "02"),
    ]


def test_parse_claim_items_empty() -> None:
    assert parse_bulletin_claim_items("<div>已選取尚未報價</div>") == []
