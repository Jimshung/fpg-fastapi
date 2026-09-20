"""電話正規化與台灣案篩選：不需網路。"""
from __future__ import annotations

from app.models.case_record import CaseRecord
from app.services.taiwan_case_filter import (
    filter_taiwan_cases,
    is_taiwan_phone_number,
    is_taiwan_sale,
    normalize_phone,
)


def test_normalize_hyphen_extension() -> None:
    assert normalize_phone("04-26992900-362") == "04-26992900#362"


def test_normalize_ext_labels_and_fullwidth() -> None:
    assert normalize_phone("04-26992900分機362") == "04-26992900#362"
    assert normalize_phone("04-26992900ext.362") == "04-26992900#362"
    assert normalize_phone("04-26992900 Ext 362") == "04-26992900#362"
    # 全形
    assert normalize_phone("０４－２６９９２９００－３６２") == "04-26992900#362"
    assert normalize_phone(" 04-2699 2900-362 ") == "04-26992900#362"


def test_normalize_keeps_hash_extension() -> None:
    assert normalize_phone("04-26992900#362") == "04-26992900#362"
    assert is_taiwan_phone_number("04-26992900#362")


def test_ac_case_passes_after_bad_extension() -> None:
    assert is_taiwan_sale("AC-UT00J2", "04-26992900-362")
    record = CaseRecord(
        tndsalno="AC-UT00J2",
        inqcnt="02",
        plant_phone="04-26992900-362",
        plant_contact="陳文義",
    )
    kept, skipped = filter_taiwan_cases([record])
    assert len(kept) == 1 and not skipped
    assert kept[0].plant_phone == "04-26992900#362"


def test_mainland_prefix_still_skipped() -> None:
    assert not is_taiwan_sale("NA-UT0CZ7", "04-26992900-362")
