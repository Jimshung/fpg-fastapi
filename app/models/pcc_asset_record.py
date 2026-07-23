"""政府電子採購網「財物變賣」案件模型。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PccAssetRecord:
    """一筆財物變賣案（以 PCC 系統 pk 為唯一鍵）。"""

    pk: str
    case_no: str = ""
    announce_seq: str = ""
    org_name: str = ""
    org_id: str = ""
    org_address: str = ""
    assets_name: str = ""
    contact: str = ""
    email: str = ""
    phone: str = ""
    announce_date: str = ""  # YYYY-MM-DD
    tender_deadline: str = ""  # YYYY-MM-DD or ISO datetime
    open_time: str = ""  # YYYY-MM-DD or ISO datetime
    open_place: str = ""
    location: str = ""
    reserve_price: str = ""
    qualification: str = ""
    document_howto: str = ""
    extra_notes: str = ""
    detail_kind: str = "old"  # old / new / normal
    source_url: str = ""
    status: str = "new"
    error: str = ""

    @property
    def case_key(self) -> str:
        return self.pk or f"{self.case_no}/{self.announce_seq}"

    @property
    def contact_display(self) -> str:
        name = (self.contact or "").strip()
        phone = (self.phone or "").strip()
        if name and phone:
            return f"{name} / {phone}"
        return name or phone
