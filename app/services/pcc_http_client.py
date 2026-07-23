"""政府電子採購網「財物變賣」HTTP client（免登入）。"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, timedelta
from typing import Optional

import aiohttp

from app.models.pcc_asset_record import PccAssetRecord
from app.services.pcc_parser import (
    BASE,
    parse_csrf,
    parse_detail,
    parse_displaytag_pages,
    parse_result_total,
    parse_search_summaries,
)

logger = logging.getLogger(__name__)

INDEX = f"{BASE}/opas/aspam/public/indexAspam"
SEARCH = f"{BASE}/opas/aspam/public/readAspam"
DETAIL_BY_KIND = {
    "old": f"{BASE}/opas/aspam/public/readOneAspamDetailOld",
    "new": f"{BASE}/opas/aspam/public/readOneAspamDetailNew",
    "normal": f"{BASE}/opas/aspam/public/readOneAspamDetail",
}
REQUEST_PAUSE = 0.25


def to_western_slash(d: date) -> str:
    return d.strftime("%Y/%m/%d")


def displaytag_page_number(url: str) -> int:
    m = re.search(r"d-\d+-p=(\d+)", url)
    return int(m.group(1)) if m else 0


def default_deadline_window(today: Optional[date] = None) -> tuple[date, date]:
    """預設：今天起 7 天內截止投標。"""
    base = today or date.today()
    return base, base + timedelta(days=7)


class PccHttpClient:
    def __init__(self, *, request_pause: float = REQUEST_PAUSE) -> None:
        self.request_pause = request_pause
        self._session: Optional[aiohttp.ClientSession] = None
        self._csrf = ""

    async def __aenter__(self) -> "PccHttpClient":
        self._session = aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar(unsafe=True),
            timeout=aiohttp.ClientTimeout(total=90),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            },
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if not self._session:
            raise RuntimeError("PccHttpClient 尚未進入 async context")
        return self._session

    async def _refresh_csrf(self) -> str:
        async with self.session.get(INDEX) as resp:
            html = await resp.text(errors="replace")
        self._csrf = parse_csrf(html)
        if not self._csrf:
            raise RuntimeError("PCC 找不到 _csrf")
        return self._csrf

    async def _get_html(self, url: str, *, params: dict | None = None) -> tuple[int, str]:
        await asyncio.sleep(self.request_pause)
        async with self.session.get(
            url, params=params, headers={"Referer": INDEX}
        ) as resp:
            return resp.status, await resp.text(errors="replace")

    async def search_by_tender_deadline(
        self,
        start: date,
        end: date,
        *,
        rows_per_page: int = 100,
    ) -> list[PccAssetRecord]:
        """依截止投標區間搜尋（西元 YYYY/MM/DD）。"""
        await self._refresh_csrf()
        form = {
            "_csrf": self._csrf,
            "searchTenderCaseNo": "",
            "searchAssetsName": "",
            "searchOrgId": "",
            "searchOrgName": "",
            "searchBeginNoticeDate": "",
            "searchEndNoticeDate": "",
            "searchBeginTenderDeadline": to_western_slash(start),
            "searchEndTenderDeadline": to_western_slash(end),
            "pageModel.rowsPerPage": str(rows_per_page),
            "pageModel.pagePosition": "0",
        }
        async with self.session.post(
            SEARCH,
            data=form,
            headers={
                "Referer": INDEX,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        ) as resp:
            html = await resp.text(errors="replace")

        total = parse_result_total(html)
        records = parse_search_summaries(html)
        seen = {r.pk for r in records}
        logger.info(
            "PCC 截止投標 %s~%s：共 %s 筆，本頁 %s 筆",
            start,
            end,
            total,
            len(records),
        )

        for page_url in parse_displaytag_pages(html):
            page_no = displaytag_page_number(page_url)
            if page_no <= 1:
                continue
            status, page_html = await self._get_html(page_url)
            if status >= 400:
                logger.warning("PCC 分頁失敗 status=%s url=%s", status, page_url)
                continue
            added = 0
            for rec in parse_search_summaries(page_html):
                if rec.pk in seen:
                    continue
                seen.add(rec.pk)
                records.append(rec)
                added += 1
            logger.info("PCC 分頁 p=%s +%s（累計 %s）", page_no, added, len(records))
            if total and len(records) >= total:
                break

        return records

    async def _load_detail_html(
        self, base: PccAssetRecord
    ) -> tuple[str, str, str]:
        """回傳 (html, detail_kind, source_url)。"""
        preferred = base.detail_kind if base.detail_kind in DETAIL_BY_KIND else "old"
        order = [preferred] + [k for k in DETAIL_BY_KIND if k != preferred]
        params = {"_csrf": self._csrf, "pk": base.pk}

        last_html = ""
        last_kind = preferred
        last_url = f"{DETAIL_BY_KIND[preferred]}?pk={base.pk}"
        for kind in order:
            url = DETAIL_BY_KIND[kind]
            status, html = await self._get_html(url, params=params)
            last_html, last_kind, last_url = html, kind, f"{url}?pk={base.pk}"
            if status < 400 and "財物名稱" in html:
                return last_html, last_kind, last_url
        return last_html, last_kind, last_url

    async def fetch_detail(self, base: PccAssetRecord) -> PccAssetRecord:
        if not self._csrf:
            await self._refresh_csrf()
        try:
            html, kind, source_url = await self._load_detail_html(base)
            if "財物名稱" not in html:
                raise RuntimeError("詳情頁缺少財物名稱")
            record = parse_detail(html, base)
            record.detail_kind = kind
            record.source_url = source_url
            record.status = "ok"
            return record
        except Exception as exc:  # noqa: BLE001
            logger.exception("PCC 詳情解析失敗 pk=%s", base.pk)
            base.status = "error"
            base.error = str(exc)
            return base

    async def fetch_cases(
        self,
        bases: list[PccAssetRecord],
        *,
        limit: int = 0,
    ) -> list[PccAssetRecord]:
        if limit > 0:
            bases = bases[:limit]
        if not self._csrf:
            await self._refresh_csrf()
        out: list[PccAssetRecord] = []
        for i, base in enumerate(bases, 1):
            logger.info(
                "擷取 PCC 案件 %s/%s：%s %s",
                i,
                len(bases),
                base.pk,
                base.case_no,
            )
            out.append(await self.fetch_detail(base))
        return out
