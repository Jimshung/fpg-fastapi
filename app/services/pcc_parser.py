"""政府電子採購網「財物變賣」HTML 解析。"""
from __future__ import annotations

import html as html_lib
import re
from typing import Optional
from urllib.parse import urljoin

from app.models.pcc_asset_record import PccAssetRecord

BASE = "https://web.pcc.gov.tw"

# formViewNew → DetailOld；formViewOld → DetailNew（官方 JS 命名如此）
_DETAIL_PATH = {
    "New": "/opas/aspam/public/readOneAspamDetailOld",
    "Old": "/opas/aspam/public/readOneAspamDetailNew",
    "Normal": "/opas/aspam/public/readOneAspamDetail",
}
_DETAIL_KIND = {"New": "old", "Old": "new", "Normal": "normal"}


def roc_to_iso(raw: str) -> str:
    """115/07/21 或 115/07/28 09:00 → ISO date / datetime。"""
    text = (raw or "").strip()
    if not text:
        return ""
    m = re.match(
        r"^(\d{2,3})/(\d{1,2})/(\d{1,2})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?",
        text,
    )
    if not m:
        # 已是西元
        m2 = re.match(
            r"^(\d{4})-(\d{2})-(\d{2})(?:[T\s](\d{2}):(\d{2}))?",
            text,
        )
        if m2:
            if m2.group(4):
                return (
                    f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}"
                    f"T{m2.group(4)}:{m2.group(5)}:00+08:00"
                )
            return f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}"
        return ""
    year = int(m.group(1)) + 1911
    month = int(m.group(2))
    day = int(m.group(3))
    if m.group(4) is not None:
        hh = int(m.group(4))
        mm = int(m.group(5))
        ss = int(m.group(6) or 0)
        return f"{year:04d}-{month:02d}-{day:02d}T{hh:02d}:{mm:02d}:{ss:02d}+08:00"
    return f"{year:04d}-{month:02d}-{day:02d}"


def iso_date_only(iso: str) -> str:
    return (iso or "")[:10]


def decode_page_code(text: str) -> str:
    """解開 pageCode2Img(\"...\") 包裝；否則回傳去標籤後文字。"""
    if not text:
        return ""
    m = re.search(r'pageCode2Img\("([^"]+)"\)', text)
    if m:
        return html_lib.unescape(m.group(1))
    cleaned = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html_lib.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_csrf(html: str) -> str:
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', html)
    return m.group(1) if m else ""


def parse_result_total(html: str) -> int:
    m = re.search(r"共有[\s\S]{0,80}?(\d+)[\s\S]{0,40}?筆資料", html)
    return int(m.group(1)) if m else 0


def parse_search_summaries(html: str) -> list[PccAssetRecord]:
    """解析查詢結果列表列。"""
    records: list[PccAssetRecord] = []
    seen: set[str] = set()
    # 以含 formView* 的 <tr> 為一列
    for tr in re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", html, flags=re.I):
        m = re.search(r"formView(New|Old|Normal)\((\d+),", tr)
        if not m:
            continue
        view_type, pk = m.group(1), m.group(2)
        if pk in seen:
            continue
        cells = re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", tr, flags=re.I)
        plain: list[str] = []
        for cell in cells:
            text = decode_page_code(cell)
            if text in ("請選擇", "檢視") or text.startswith("formView"):
                continue
            plain.append(text)
        # 預期：項次, 機關名稱, 標案案號, 公告次數, 財物名稱, 公告日期, ...
        org = plain[1] if len(plain) > 1 else ""
        case_no = plain[2] if len(plain) > 2 else ""
        seq = plain[3] if len(plain) > 3 else ""
        assets = plain[4] if len(plain) > 4 else ""
        announce_raw = plain[5] if len(plain) > 5 else ""
        path = _DETAIL_PATH.get(view_type, _DETAIL_PATH["New"])
        records.append(
            PccAssetRecord(
                pk=pk,
                case_no=case_no,
                announce_seq=seq,
                org_name=org,
                assets_name=assets,
                announce_date=iso_date_only(roc_to_iso(announce_raw)),
                detail_kind=_DETAIL_KIND.get(view_type, "old"),
                source_url=urljoin(BASE, f"{path}?pk={pk}"),
            )
        )
        seen.add(pk)
    return records


def parse_displaytag_pages(html: str) -> list[str]:
    """回傳其他分頁完整 URL（若有）。"""
    urls: list[str] = []
    for href in re.findall(r'href="(/opas/aspam/public/readAspam\?[^"]+)"', html):
        if re.search(r"d-\d+-p=\d+", href):
            urls.append(html_lib.unescape(href))
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(urljoin(BASE, u))
    return out


def _field_map(html: str) -> dict[str, str]:
    """詳情頁 label → raw html/value。"""
    fields: dict[str, str] = {}
    pairs = re.findall(
        r"<(?:th|td)[^>]*>\s*([^<]{1,40}?)\s*</(?:th|td)>\s*<td[^>]*>([\s\S]*?)</td>",
        html,
        flags=re.I,
    )
    for label, raw in pairs:
        key = re.sub(r"\s+", "", label.strip())
        if key and key not in fields:
            fields[key] = raw
    return fields


def parse_detail(html: str, base: Optional[PccAssetRecord] = None) -> PccAssetRecord:
    record = PccAssetRecord(
        pk=base.pk if base else "",
        case_no=base.case_no if base else "",
        announce_seq=base.announce_seq if base else "",
        org_name=base.org_name if base else "",
        assets_name=base.assets_name if base else "",
        announce_date=base.announce_date if base else "",
        detail_kind=base.detail_kind if base else "old",
        source_url=base.source_url if base else "",
    )

    fields = _field_map(html)

    def get(name: str) -> str:
        raw = fields.get(name)
        return decode_page_code(raw) if raw is not None else ""

    record.org_name = get("機關名稱") or record.org_name
    record.org_id = get("機關代碼")
    record.org_address = get("機關地址")
    record.case_no = get("標案案號") or record.case_no
    record.announce_seq = get("公告次數") or record.announce_seq
    record.assets_name = get("財物名稱") or record.assets_name
    record.contact = get("聯絡人")
    record.email = get("電子郵件信箱")
    record.phone = get("聯絡電話")
    record.announce_date = (
        iso_date_only(roc_to_iso(get("公告日期"))) or record.announce_date
    )
    record.tender_deadline = roc_to_iso(get("截止投標"))
    record.open_time = roc_to_iso(get("開標時間"))
    record.open_place = get("開標地點")
    record.location = get("變賣標的所在地")
    record.reserve_price = get("底價金額")
    record.qualification = get("投標資格摘要")
    record.document_howto = get("招標文件領取方式及地點")
    record.extra_notes = get("附加說明")
    if not record.pk:
        m = re.search(r'name="pk"\s+value="(\d+)"', html) or re.search(
            r"[?&]pk=(\d+)", html
        )
        if m:
            record.pk = m.group(1)
    return record
