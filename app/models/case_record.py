"""標售案件歸檔用資料模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class QuoteItem:
    """報價明細單一品項（不含材料編號）。"""

    description: str
    quantity: str = ""
    quality_note: str = ""

    def summary_line(self) -> str:
        parts = [self.description]
        if self.quantity:
            parts.append(self.quantity)
        return "｜".join(parts)


@dataclass
class CaseRecord:
    """一筆標售案（案號 + 詢價次數）。"""

    tndsalno: str
    inqcnt: str
    blocid: str = ""
    # "gen"=標案管理(/j202/prc)，"cmp"=競標管理(/j202/cmp)
    bid_channel: str = "gen"
    company: str = ""
    department: str = ""
    location: str = ""
    announce_date: str = ""  # YYYY-MM-DD
    quote_deadline: str = ""  # YYYY-MM-DD
    pickup_period: str = ""
    plant_contact: str = ""
    plant_phone: str = ""
    vendor_notes: str = ""
    eco_code: str = ""
    items: list[QuoteItem] = field(default_factory=list)
    zip_url: str = ""
    zip_path: Optional[str] = None
    zip_sha256: str = ""
    source_url: str = ""
    status: str = "new"
    error: str = ""

    @property
    def case_key(self) -> str:
        return f"{self.tndsalno}/{self.inqcnt}"

    @property
    def contact_display(self) -> str:
        name = (self.plant_contact or "").strip()
        phone = (self.plant_phone or "").strip()
        if name and phone:
            return f"{name} / {phone}"
        return name or phone

    @property
    def items_summary(self) -> str:
        if not self.items:
            return ""
        return "\n".join(item.summary_line() for item in self.items)

    @property
    def quality_summary(self) -> str:
        notes = [i.quality_note for i in self.items if i.quality_note]
        return "\n".join(notes)
