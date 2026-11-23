"""政府電子採購網「財物變賣」HTTP client（免登入）。"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import re
from datetime import date
from typing import Optional
from urllib.parse import urlencode

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
# 請求間隔（秒）；另加 0~50% 隨機抖動，避免固定節奏的連續請求
REQUEST_PAUSE = 1.0
# 取 _csrf 失敗時的重試等待秒數（共重試 2 次）
CSRF_RETRY_DELAYS = (5.0, 15.0)
# 截止投標回填用：遠迄日（實測 2026 年底後無更多筆）
DEFAULT_DEADLINE_END = date(2027, 12, 31)


def to_western_slash(d: date) -> str:
    return d.strftime("%Y/%m/%d")


def displaytag_page_number(url: str) -> int:
    m = re.search(r"d-\d+-p=(\d+)", url)
    return int(m.group(1)) if m else 0


# WAF 封鎖頁（實測：HTTP 500，頁面約 38KB，關鍵字出現在內文尾端而非開頭）
WAF_BLOCK_MARKERS = (
    "the url you requested has been blocked",
    "web page blocked!",
)


def is_waf_blocked(html: str) -> bool:
    """內文是否為 WAF 封鎖頁（與「token 缺失」等其他失敗區分）。

    必須檢查整份內文：封鎖頁開頭是一大段 CSS，關鍵字在尾端。
    """
    low = html.lower()
    return any(m in low for m in WAF_BLOCK_MARKERS)


class PccWafBlockedError(RuntimeError):
    """PCC 回傳 WAF 封鎖頁；繼續請求只會加深封鎖，應立即停止。"""


def summarize_response(status: int, headers, html: str, limit: int = 300) -> str:
    """回應摘要（狀態碼、關鍵標頭、內文前段純文字），供診斷用。

    若為 WAF 封鎖頁，開頭加上「[WAF 封鎖]」標記，日誌一眼可辨。
    """
    keys = ("Content-Type", "Server", "Retry-After", "Via", "Location")
    picked = {k: headers.get(k) for k in keys if headers.get(k)}
    text = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()[:limit]
    tag = "[WAF 封鎖] " if is_waf_blocked(html) else ""
    return f"{tag}HTTP {status} 標頭={picked} 長度={len(html)} 內文={text!r}"


class PccHttpClient:
    def __init__(
        self,
        *,
        request_pause: float = REQUEST_PAUSE,
        csrf_retry_delays: tuple[float, ...] = CSRF_RETRY_DELAYS,
        proxy_url: str | None = None,
        proxy_key: str | None = None,
    ) -> None:
        # GAS 轉發代理（PCC 封鎖 GitHub IP 時使用）；未設定則直連
        self.proxy_url = (
            proxy_url if proxy_url is not None else os.getenv("PCC_PROXY_URL", "")
        )
        self.proxy_key = (
            proxy_key if proxy_key is not None else os.getenv("PCC_PROXY_KEY", "")
        )
        self.request_pause = request_pause
        self.csrf_retry_delays = csrf_retry_delays
        self._session: Optional[aiohttp.ClientSession] = None
        self._csrf = ""
        self.waf_blocked = False

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
        """取得 _csrf；失敗時記錄回應摘要並退避重試（GitHub IP 偶遭擋／限流）。"""
        if self.proxy_url:
            return ""  # 代理模式不使用 session／_csrf（GET 列表免 token）
        delays = self.csrf_retry_delays
        attempts = len(delays) + 1
        last_error = "PCC 找不到 _csrf"
        for attempt in range(1, attempts + 1):
            try:
                async with self.session.get(INDEX) as resp:
                    html = await resp.text(errors="replace")
                    summary = summarize_response(resp.status, resp.headers, html)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                summary = f"{type(exc).__name__}: {exc}"
                html = ""
            self._csrf = parse_csrf(html)
            if self._csrf:
                return self._csrf
            if is_waf_blocked(html):
                self.waf_blocked = True
                logger.error("PCC 取 _csrf 遭 WAF 封鎖，停止重試：%s", summary)
                raise PccWafBlockedError(f"PCC 遭 WAF 封鎖（{summary}）")
            last_error = f"PCC 找不到 _csrf（{summary}）"
            logger.warning(
                "PCC 取 _csrf 失敗 (%d/%d)：%s", attempt, attempts, summary
            )
            if attempt < attempts:
                await asyncio.sleep(delays[attempt - 1])
        raise RuntimeError(last_error)

    async def _get_html(self, url: str, *, params: dict | None = None) -> tuple[int, str]:
        await asyncio.sleep(
            self.request_pause * (1 + random.uniform(0, 0.5))
            if self.request_pause
            else 0
        )
        if self.proxy_url:
            full = f"{url}?{urlencode(params)}" if params else url
            return await self._relay_get(full)
        async with self.session.get(
            url, params=params, headers={"Referer": INDEX}
        ) as resp:
            html = await resp.text(errors="replace")
            self._raise_if_waf_blocked(resp.status, resp.headers, html)
            return resp.status, html

    async def _relay_get(self, url: str) -> tuple[int, str]:
        """經 GAS 代理抓 PCC 頁面，回傳 (PCC 狀態碼, 內文)。"""
        async with self.session.get(
            self.proxy_url, params={"key": self.proxy_key, "url": url}
        ) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"PCC 代理回應非 JSON（HTTP {resp.status}）：{exc}"
                ) from exc
        status = int(data.get("status", 0))
        body = data.get("body", "")
        if status in (400, 403) and not body.lstrip().startswith("<"):
            raise RuntimeError(f"PCC 代理拒絕請求（{status}）：{body[:100]}")
        self._raise_if_waf_blocked(status, {}, body)
        return status, body

    def _raise_if_waf_blocked(self, status: int, headers, html: str) -> None:
        if is_waf_blocked(html):
            self.waf_blocked = True
            raise PccWafBlockedError(
                f"PCC 遭 WAF 封鎖（{summarize_response(status, headers, html)}）"
            )

    async def _search(
        self,
        *,
        label: str,
        notice_begin: str = "",
        notice_end: str = "",
        dead_begin: str = "",
        dead_end: str = "",
        rows_per_page: int = 100,
    ) -> list[PccAssetRecord]:
        await self._refresh_csrf()
        if self.proxy_url:
            query = {
                "searchTenderCaseNo": "",
                "searchAssetsName": "",
                "searchOrgId": "",
                "searchOrgName": "",
                "searchBeginNoticeDate": notice_begin,
                "searchEndNoticeDate": notice_end,
                "searchBeginTenderDeadline": dead_begin,
                "searchEndTenderDeadline": dead_end,
                "pageModel.rowsPerPage": str(rows_per_page),
            }
            _, html = await self._relay_get(f"{SEARCH}?{urlencode(query)}")
            return await self._collect_pages(html, label)
        form = {
            "_csrf": self._csrf,
            "searchTenderCaseNo": "",
            "searchAssetsName": "",
            "searchOrgId": "",
            "searchOrgName": "",
            "searchBeginNoticeDate": notice_begin,
            "searchEndNoticeDate": notice_end,
            "searchBeginTenderDeadline": dead_begin,
            "searchEndTenderDeadline": dead_end,
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
            self._raise_if_waf_blocked(resp.status, resp.headers, html)

        return await self._collect_pages(html, label)

    async def _collect_pages(self, html: str, label: str) -> list[PccAssetRecord]:
        total = parse_result_total(html)
        records = parse_search_summaries(html)
        seen = {r.pk for r in records}
        logger.info(
            "PCC %s：共 %s 筆，本頁 %s 筆",
            label,
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

    async def search_by_announce_date(
        self,
        start: date,
        end: date,
        *,
        rows_per_page: int = 100,
    ) -> list[PccAssetRecord]:
        """依公告日區間搜尋（西元 YYYY/MM/DD）。"""
        begin = to_western_slash(start)
        finish = to_western_slash(end)
        return await self._search(
            label=f"公告日 {begin}~{finish}",
            notice_begin=begin,
            notice_end=finish,
            rows_per_page=rows_per_page,
        )

    async def search_by_tender_deadline(
        self,
        start: date,
        end: date,
        *,
        rows_per_page: int = 100,
    ) -> list[PccAssetRecord]:
        """依截止投標區間搜尋（西元 YYYY/MM/DD；供歷史回填）。"""
        begin = to_western_slash(start)
        finish = to_western_slash(end)
        return await self._search(
            label=f"截止投標 {begin}~{finish}",
            dead_begin=begin,
            dead_end=finish,
            rows_per_page=rows_per_page,
        )

    async def _load_detail_html(
        self, base: PccAssetRecord
    ) -> tuple[str, str, str]:
        """回傳 (html, detail_kind, source_url)。"""
        preferred = base.detail_kind if base.detail_kind in DETAIL_BY_KIND else "old"
        order = [preferred] + [k for k in DETAIL_BY_KIND if k != preferred]
        params = {"pk": base.pk}
        if self._csrf:
            params = {"_csrf": self._csrf, **params}

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
        except PccWafBlockedError:
            raise
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
            try:
                out.append(await self.fetch_detail(base))
            except PccWafBlockedError as exc:
                logger.error("PCC 遭 WAF 封鎖，停止擷取剩餘 %s 筆", len(bases) - i + 1)
                for rest in bases[i - 1 :]:
                    rest.status = "error"
                    rest.error = f"WAF 封鎖，未擷取（{exc}）"[:300]
                    out.append(rest)
                break
        return out
