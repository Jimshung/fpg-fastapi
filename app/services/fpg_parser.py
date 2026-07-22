"""從 FPG HTML 解析標售公報／詢價單／報價明細。"""
from __future__ import annotations

import html as html_lib
import re
from typing import Iterable

from app.models.case_record import CaseRecord, QuoteItem


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).replace("\xa0", " ").strip()


def to_iso_date(raw: str) -> str:
    """YYYY/MM/DD → YYYY-MM-DD；已是 ISO 則原樣返回。"""
    raw = (raw or "").strip()
    m = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", raw)
    if not m:
        return raw
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def parse_bulletin_case_keys(html: str) -> list[tuple[str, str]]:
    """從標售公報清單抽出 (tndsalno, inqcnt)，依出現順序去重。"""
    found = re.findall(r">([A-Z0-9]{2}-[A-Z0-9]+)/(\d{2})<", html)
    return list(dict.fromkeys(found))


def _split_contact(raw: str) -> tuple[str, str]:
    raw = strip_html(raw)
    m = re.match(r"^(.+?)\((.+)\)$", raw)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return raw, ""


def parse_bulletin_cases(html: str) -> list[CaseRecord]:
    """從標售公報清單解析可取得的摘要欄位（標案管理前備援）。"""
    records: list[CaseRecord] = []
    seen: set[tuple[str, str]] = set()

    # 依清單序號切開每個案件區塊
    parts = re.split(
        r'<td width="8%">\s*<div align="center"><font size="2">\s*\d+\s*</font>',
        html,
    )
    for chunk in parts[1:]:
        for case_m in re.finditer(
            r'<font size="2">(\d{4}/\d{2}/\d{2})\s*</font></div>\s*</td>\s*'
            r'<td[^>]*>\s*<div align="center"><font size="2">'
            r"([A-Z0-9]{2}-[A-Z0-9]+)/(\d{2})</font></div>\s*</td>\s*"
            r'<td[^>]*>\s*<div align="center"><font size="2">([^<]*)</font></div>\s*</td>\s*'
            r'<td[^>]*><font size="2">([^<]*)</font></td>',
            chunk,
        ):
            deadline, tndsalno, inqcnt, location, contact_raw = case_m.groups()
            key = (tndsalno, inqcnt)
            if key in seen:
                continue
            seen.add(key)

            # 每個案號往前取區塊，避免多案同段時欄位錯位
            local = chunk[max(0, case_m.start() - 4500) : case_m.start()]

            announce = ""
            quantity = ""
            rows = re.findall(
                r'<font size="2">(\d{4}/\d{2}/\d{2})</font></div>\s*</td>\s*'
                r'<td[^>]*>\s*<div align="center"><font size="2">([^<]*)</font></div>\s*</td>\s*'
                r'<td[^>]*>\s*<div align="center"><font size="2">([^<]*)</font></div>',
                local,
            )
            if rows:
                announce, _supplier, quantity = rows[-1]

            description = ""
            desc_matches = re.findall(
                r'<td colspan="5"><font size="2">\s*([\s\S]*?)<br>',
                local,
            )
            if desc_matches:
                description = strip_html(desc_matches[-1])

            eco = ""
            eco_m = re.search(
                r"環保法定代碼：</font></td>\s*<td[^>]*><font[^>]*>([^<]+)",
                local,
            )
            if eco_m:
                eco = strip_html(eco_m.group(1))
                if eco in {"--", "-"}:
                    eco = ""

            contact_name, contact_phone = _split_contact(contact_raw)
            items = []
            if description or quantity:
                items = [
                    QuoteItem(
                        description=description or "(公報品名未解析)",
                        quantity=strip_html(quantity),
                    )
                ]

            records.append(
                CaseRecord(
                    tndsalno=tndsalno,
                    inqcnt=inqcnt,
                    location=strip_html(location),
                    announce_date=to_iso_date(announce),
                    quote_deadline=to_iso_date(deadline),
                    plant_contact=contact_name,
                    plant_phone=contact_phone,
                    eco_code=eco,
                    items=items,
                )
            )
    return records


def parse_bulletin_total_pages(html: str) -> int:
    # goNPage(...,'21','gtpage1') 或 /2頁
    m = re.search(r"/(\d+)頁", html)
    if m:
        return max(1, int(m.group(1)))
    m = re.search(r"goNPage\([^)]*'(\d+)'\s*,\s*'gtpage", html)
    if m:
        # itemnum is total items, not pages — fallback
        pass
    markers = re.findall(r"(\d+)/(\d+)頁", html)
    if markers:
        return max(int(b) for _, b in markers)
    return 1


def parse_bulletin_itemnum(html: str) -> str:
    m = re.search(r"goNPage\([^)]*'(\d+)'\s*,\s*'gtpage", html)
    return m.group(1) if m else ""


def parse_bid_go_detail(html: str) -> tuple[str, str, str] | None:
    """標案管理清單：goDetail(form, blocid, tndsalno, inqcnt)。"""
    m = re.search(
        r"goDetail\(\s*this\.form\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)",
        html,
    )
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)


def parse_fromjsp(html: str) -> str:
    m = re.search(r'name=["\']FROMJSP["\'][^>]*value=["\']([^"\']*)["\']', html, re.I)
    if m:
        return m.group(1)
    m = re.search(r'value=["\']([^"\']*)["\'][^>]*name=["\']FROMJSP["\']', html, re.I)
    return m.group(1) if m else ""


def parse_inquiry_form(html: str, record: CaseRecord) -> CaseRecord:
    """解析標售詢價單欄位。"""

    def field(label: str) -> str:
        m = re.search(rf"{re.escape(label)}：([^<]+)", html)
        return strip_html(m.group(1)) if m else ""

    record.company = field("二、委託公司") or field("委託公司")
    dept = re.search(
        r"委託部門：</font></td>\s*<td[^>]*><font[^>]*>([^<]+)",
        html,
    )
    record.department = strip_html(dept.group(1)) if dept else ""
    record.location = field("三、存放地點") or field("存放地點")
    record.announce_date = to_iso_date(field("四、公告日") or field("公告日"))
    record.quote_deadline = to_iso_date(
        field("五、報價截止日") or field("報價截止日")
    )
    pickup = re.search(r"七、提貨期限：(.+?)</font>", html, re.S)
    if pickup:
        record.pickup_period = strip_html(pickup.group(1))
    else:
        record.pickup_period = field("提貨期限")

    contact = re.search(
        r"廠區</font></td>\s*<td[^>]*><font[^>]*>([^<]+)</font></td>\s*"
        r"<td[^>]*><font[^>]*>聯絡電話</font></td>\s*"
        r"<td[^>]*><font[^>]*>([^<]+)",
        html,
        re.S,
    )
    if contact:
        record.plant_contact = strip_html(contact.group(1))
        record.plant_phone = strip_html(contact.group(2))

    case_m = re.search(r"標售案號/詢價次數：\s*([^/\s]+)/(\d{2})", html)
    if case_m:
        record.tndsalno = case_m.group(1).strip()
        record.inqcnt = case_m.group(2).strip()

    bloc = re.search(
        r'name=["\'](?:blocid|_u_gb04_cblocid)["\'][^>]*value=["\']([^"\']+)["\']',
        html,
        re.I,
    )
    if bloc:
        record.blocid = bloc.group(1)
    return record


def parse_quote_form(html: str, record: CaseRecord) -> CaseRecord:
    """解析報價單：品名規格、標售數量、品質說明、附件。"""
    zips = re.findall(r'(/j202/share/j202_download/[^"\']+\.ZIP)', html, re.I)
    if zips:
        record.zip_url = zips[0]

    vendor = re.search(r"四、廠商配合事項[：:]?\s*(.*?)</font>", html, re.S)
    if vendor:
        record.vendor_notes = strip_html(vendor.group(1))

    eco = re.search(r"五、環保代碼[：:]?\s*([^<]+)", html)
    if eco:
        record.eco_code = strip_html(eco.group(1))
        if record.eco_code in {"--", "-"}:
            record.eco_code = ""

    items: list[QuoteItem] = []
    for m in re.finditer(
        r"材料編號:([^<\s]+)<br>\s*((?:&lt;|<)[^<&]+(?:&gt;|>))\s*</font>"
        r"([\s\S]*?)(?=材料編號:|八、報價說明|$)",
        html,
    ):
        desc = strip_html(m.group(2))
        chunk = m.group(3)
        qty = ""
        qty_m = re.search(
            r"標售數量</font></div>\s*</td>[\s\S]*?</tr>\s*(?:<!--[\s\S]*?-->\s*)?<tr>\s*"
            r'<td[^>]*>\s*<div align="center"><font size="2">([^<]+)</font>',
            chunk,
        )
        if qty_m:
            qty = strip_html(qty_m.group(1))
        quality = ""
        q_m = re.search(r"品質說明</font><font[^>]*>：([^<]+)", chunk)
        if q_m:
            quality = strip_html(q_m.group(1))
        items.append(QuoteItem(description=desc, quantity=qty, quality_note=quality))

    # 若沒有 <> 格式，退而求其次抓材料編號後文字
    if not items:
        for m in re.finditer(
            r"材料編號:([^<\s]+)<br>\s*([\s\S]*?)</font>",
            html,
        ):
            desc = strip_html(m.group(2))
            if desc:
                items.append(QuoteItem(description=desc))

    if items:
        record.items = items
    return record


def merge_records(base: CaseRecord, extra: CaseRecord) -> CaseRecord:
    """以 extra 非空欄位覆蓋 base。"""
    for field_name in (
        "blocid",
        "company",
        "department",
        "location",
        "announce_date",
        "quote_deadline",
        "pickup_period",
        "plant_contact",
        "plant_phone",
        "vendor_notes",
        "eco_code",
        "zip_url",
        "zip_path",
        "zip_sha256",
        "source_url",
        "error",
    ):
        value = getattr(extra, field_name)
        if value:
            setattr(base, field_name, value)
    if extra.items:
        base.items = extra.items
    return base


def chunked(items: Iterable, size: int):
    buf = []
    for item in items:
        buf.append(item)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf
