"""解析 FPG「歷史資料」報價清單（已報價案件與報價時間）。"""
from __future__ import annotations

import re
from dataclasses import dataclass

_ROW_RE = re.compile(r"<tr\b[^>]*>(?:(?!</tr>).)*?goConfirm\(.*?</tr>", re.S | re.I)
_CONFIRM_RE = re.compile(
    r"goConfirm\(this\.form,'([^']*)','([^']*)','([^']*)','([^']*)','([^']*)','([^']*)'\)"
)
_QUOTE_TIME_RE = re.compile(r"(\d{4}/\d{2}/\d{2})\s+(\d{2}:\d{2}:\d{2})")
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class BidHistoryRow:
    tndsalno: str
    inqcnt: str
    blocid: str
    status_flag: str
    inqdeldat: str
    inqexpire: str
    quote_time: str  # YYYY/MM/DD HH:MM:SS；無則空字串
    status_text: str  # 例：已報價、已檢視


def parse_bid_history(html: str) -> list[BidHistoryRow]:
    rows: list[BidHistoryRow] = []
    for match in _ROW_RE.finditer(html):
        chunk = match.group(0)
        confirm = _CONFIRM_RE.search(chunk)
        if not confirm:
            continue
        blocid, tndsalno, flag, deldat, inqcnt, expire = confirm.groups()
        text = re.sub(r"\s+", " ", _TAG_RE.sub(" ", chunk.replace("&nbsp;", " ")))
        time_match = _QUOTE_TIME_RE.search(text)
        quote_time = f"{time_match.group(1)} {time_match.group(2)}" if time_match else ""
        status_text = ""
        for label in ("已報價", "已檢視", "未報價"):
            if label in text:
                status_text = label
                break
        rows.append(
            BidHistoryRow(
                tndsalno=tndsalno,
                inqcnt=inqcnt,
                blocid=blocid,
                status_flag=flag,
                inqdeldat=deldat,
                inqexpire=expire,
                quote_time=quote_time,
                status_text=status_text,
            )
        )
    return rows
