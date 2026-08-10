"""FPG 電子市集 HTTP client（登入／搜尋／讀詢價與報價／下載附件）。"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import aiohttp

from app.core.config import settings
from app.models.case_record import CaseRecord
from app.services.captcha_service import CaptchaService
from app.services.fpg_parser import (
    fill_missing_announce_dates,
    merge_records,
    parse_bid_go_detail,
    parse_bulletin_case_keys,
    parse_bulletin_cases,
    parse_bulletin_itemnum,
    parse_bulletin_total_pages,
    parse_fromjsp,
    parse_inquiry_form,
    parse_quote_form,
)
from app.services.fpg_urls import (
    BID_PAGE_PATH,
    BID_POST_PATH,
    BULLETIN_PAGE_PATH,
    BULLETIN_POST_PATH,
    CAPTCHA_PATH,
    CMP_BID_PAGE_PATH,
    CMP_BID_POST_PATH,
    LOGIN_SERVLET_PATH,
    fpg_base_url,
    fpg_url,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BidChannelConfig:
    page: str
    post: str
    from_search: str
    from_list: str
    from_detail: str
    label: str


def _bid_channels() -> dict[str, BidChannelConfig]:
    return {
        "gen": BidChannelConfig(
            page=fpg_url(BID_PAGE_PATH),
            post=fpg_url(BID_POST_PATH),
            from_search="FJ202C1PB01",
            from_list="FJ202C1PB02",
            from_detail="FJ202C1PB03",
            label="標案管理",
        ),
        "cmp": BidChannelConfig(
            page=fpg_url(CMP_BID_PAGE_PATH),
            post=fpg_url(CMP_BID_POST_PATH),
            from_search="FJ202C2PB01",
            from_list="FJ202C2PB02",
            from_detail="FJ202C2PB03",
            label="競標管理",
        ),
    }


class FpgHttpClient:
    def __init__(
        self,
        *,
        captcha_service: Optional[CaptchaService] = None,
        download_dir: Optional[Path] = None,
        login_retries: int = 12,
    ) -> None:
        self.captcha_service = captcha_service or CaptchaService()
        self.download_dir = download_dir or Path("app/utils/screenshots/archive_downloads")
        self.login_retries = login_retries
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "FpgHttpClient":
        timeout = aiohttp.ClientTimeout(total=120)
        self._session = aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar(unsafe=True),
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/150.0.0.0 Safari/537.36"
                ),
                "Origin": fpg_base_url(),
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
            raise RuntimeError("FpgHttpClient 尚未進入 async context")
        return self._session

    async def _get(self, url: str, **kwargs) -> str:
        async with self.session.get(url, **kwargs) as resp:
            return await resp.text(errors="replace")

    async def _post_form(self, url: str, data: dict, *, referer: str) -> str:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": referer,
        }
        async with self.session.post(url, data=data, headers=headers) as resp:
            return await resp.text(errors="replace")

    async def login(self) -> None:
        await self._get(settings.LOGIN_URL)
        captcha_url = fpg_url(CAPTCHA_PATH)
        login_servlet = fpg_url(LOGIN_SERVLET_PATH)
        for attempt in range(1, self.login_retries + 1):
            async with self.session.get(
                f"{captcha_url}?rrr={int(time.time() * 1000)}"
            ) as resp:
                image = await resp.read()
            code = await self.captcha_service.solve_captcha(image)
            logger.info("登入驗證碼 attempt=%s ocr=%r", attempt, code)
            if not code or code == "error" or len(str(code)) != 4:
                await asyncio.sleep(2)
                continue
            html = await self._post_form(
                login_servlet,
                {
                    "FROMJSP": "FJ2XXMG01",
                    "BTN": "",
                    "Lang": "",
                    "logonstate": "",
                    "id": settings.FPG_USERNAME,
                    "passwd": settings.FPG_PASSWORD,
                    "vcode": str(code),
                },
                referer=settings.LOGIN_URL,
            )
            if "驗證碼錯誤" in html:
                await asyncio.sleep(1)
                continue
            if "密碼錯誤" in html or "帳號輸入錯誤" in html or "無此帳號" in html:
                raise RuntimeError("FPG 登入失敗：帳號或密碼錯誤（請檢查 .env）")
            if "標售公報" in html or "標案管理" in html:
                logger.info("FPG 登入成功")
                return
        raise RuntimeError("FPG 登入失敗：驗證碼重試耗盡")
    async def search_bulletin_by_announce_date(
        self,
        start_date: str,
        end_date: str,
    ) -> list[CaseRecord]:
        """依公告日搜尋，回傳公報摘要 CaseRecord（已去重）。"""
        bulletin_page = fpg_url(BULLETIN_PAGE_PATH)
        bulletin_post = fpg_url(BULLETIN_POST_PATH)
        await self._get(bulletin_page)
        first = await self._bulletin_list(start_date, end_date, page="1", itemnum="")
        records = parse_bulletin_cases(first)
        # 若細部 parser 漏案，至少保留案號
        for tnd, inq in parse_bulletin_case_keys(first):
            if not any(r.tndsalno == tnd and r.inqcnt == inq for r in records):
                records.append(CaseRecord(tndsalno=tnd, inqcnt=inq))
        pages = parse_bulletin_total_pages(first)
        itemnum = parse_bulletin_itemnum(first)
        logger.info(
            "公報搜尋 %s~%s：第 1/%s 頁，本頁 %s 案，itemnum=%s",
            start_date,
            end_date,
            pages,
            len(records),
            itemnum,
        )
        seen = {(r.tndsalno, r.inqcnt) for r in records}
        for page in range(2, pages + 1):
            html = await self._bulletin_list(
                start_date,
                end_date,
                page=str(page),
                itemnum=itemnum,
                btn="goPage",
            )
            page_records = parse_bulletin_cases(html)
            for tnd, inq in parse_bulletin_case_keys(html):
                if not any(r.tndsalno == tnd and r.inqcnt == inq for r in page_records):
                    page_records.append(CaseRecord(tndsalno=tnd, inqcnt=inq))
            logger.info("公報第 %s 頁：%s 案", page, len(page_records))
            for record in page_records:
                key = (record.tndsalno, record.inqcnt)
                if key in seen:
                    continue
                seen.add(key)
                records.append(record)
        for record in records:
            record.source_url = bulletin_post
        filled = fill_missing_announce_dates(records, start_date, end_date)
        if filled:
            logger.info(
                "單一公告日 %s：補上空白公告日 %s 筆",
                start_date,
                filled,
            )
        return records

    async def _bulletin_list(
        self,
        start_date: str,
        end_date: str,
        *,
        page: str,
        itemnum: str,
        btn: str = "goList",
    ) -> str:
        form = {
            "FROMJSP": "FJ202C1PA01" if page == "1" and btn == "goList" else "FJ202C1PA02",
            "BTN": btn,
            "bcgno": "",
            "bcgnm": "",
            "mcgno": "",
            "mcgnm": "",
            "inqno_or_class": "sel_complex",
            "inqno_or_class_blocid": "",
            "keyword": "all",
            "selSort": "ntidat",
            "selArea": "T",
            "GpBlocid": "all",
            "mk": "srh",
            "page": page,
            "itemnum": itemnum,
            "radio": "radio2",
            "tndsalno": "",
            "date_f": start_date,
            "date_e": end_date,
            "radiodate": "ntidat",
            "mtkd": "X",
            "spec": "",
            "casestyle": "case3",
            "selectBlocid": "75708007",
        }
        if btn == "goPage":
            form["FROMJSP"] = "FJ202C1PA02"
        return await self._post_form(
            fpg_url(BULLETIN_POST_PATH),
            form,
            referer=fpg_url(BULLETIN_PAGE_PATH),
        )

    async def enrich_case(self, base: CaseRecord) -> CaseRecord:
        """以標案／競標管理詢價／報價明細 enrichment；找不到則保留公報摘要。"""
        channels = _bid_channels()
        primary = base.bid_channel if base.bid_channel in channels else "gen"
        fallback = "cmp" if primary == "gen" else "gen"
        last_error = ""
        for channel in (primary, fallback):
            try:
                enriched = await self._enrich_via_channel(base, channel)
            except Exception as exc:
                last_error = str(exc)
                logger.exception(
                    "%s擷取案件失敗 %s/%s",
                    channels[channel].label,
                    base.tndsalno,
                    base.inqcnt,
                )
                continue
            if enriched is not None:
                return enriched
        if last_error:
            base.status = "error"
            base.error = last_error
            base.mark_incomplete_shell()
            return base
        logger.info(
            "標案／競標管理皆無報價單，使用公報摘要 %s/%s",
            base.tndsalno,
            base.inqcnt,
        )
        if base.mark_incomplete_shell():
            logger.warning(
                "公報摘要亦為空殼，略過當成功案 %s/%s",
                base.tndsalno,
                base.inqcnt,
            )
            return base
        base.status = "new"
        if not base.error:
            base.error = ""
        return base

    async def _enrich_via_channel(
        self,
        base: CaseRecord,
        channel: str,
    ) -> CaseRecord | None:
        cfg = _bid_channels()[channel]
        record = CaseRecord(
            tndsalno=base.tndsalno,
            inqcnt=base.inqcnt,
            bid_channel=channel,
        )
        record.source_url = cfg.post
        await self._get(cfg.page)
        list_html = await self._post_form(
            cfg.post,
            {
                "FROMJSP": cfg.from_search,
                "BTN": "goList",
                "srh_kd": "bytndsalno",
                "srh_blocid": "",
                "srh_sts": "",
                "srh_tndsalno": base.tndsalno,
                "srh_begdat": "",
                "srh_enddat": "",
                "dateradio": "ntidat",
                "stsradio": "ntidat",
            },
            referer=cfg.page,
        )
        detail = parse_bid_go_detail(list_html)
        if not detail:
            logger.info(
                "%s無報價單 %s/%s",
                cfg.label,
                base.tndsalno,
                base.inqcnt,
            )
            return None

        blocid, tnd, inq = detail
        record.blocid = blocid
        record.tndsalno = tnd
        record.inqcnt = inq

        page_html = await self._post_form(
            cfg.post,
            {
                "FROMJSP": cfg.from_list,
                "BTN": "goQuo",
                "blocid": blocid,
                "tndsalno": tnd,
                "inqcnt": inq,
                "status": "",
                "inqdeldat": "",
                "inqpur": "",
                "inqexpire": "",
                "quo_from_page": "prc_bid_gen_lst",
            },
            referer=cfg.post,
        )
        fromjsp = parse_fromjsp(page_html) or cfg.from_detail

        inquiry_html = page_html
        quote_html = page_html
        if "七、報價明細" not in page_html:
            quote_html = await self._post_form(
                cfg.post,
                {
                    "FROMJSP": fromjsp,
                    "BTN": "goQuo",
                    "blocid": blocid,
                    "tndsalno": tnd,
                    "inqcnt": inq,
                },
                referer=cfg.post,
            )
        if "委託公司" not in inquiry_html and "二、委託公司" not in inquiry_html:
            inquiry_html = await self._post_form(
                cfg.post,
                {
                    "FROMJSP": parse_fromjsp(quote_html) or fromjsp,
                    "BTN": "goInq",
                    "blocid": blocid,
                    "tndsalno": tnd,
                    "inqcnt": inq,
                },
                referer=cfg.post,
            )

        parse_inquiry_form(inquiry_html, record)
        parse_quote_form(quote_html, record)

        if record.zip_url:
            zip_path = await self.download_zip(record.zip_url, tnd)
            if zip_path:
                record.zip_path = str(zip_path)
                record.zip_sha256 = hashlib.sha256(
                    zip_path.read_bytes()
                ).hexdigest()
        record.status = "new"
        logger.info(
            "%s enrichment 成功 %s/%s items=%s",
            cfg.label,
            tnd,
            inq,
            len(record.items),
        )
        return merge_records(base, record)

    async def download_zip(self, zip_url: str, tndsalno: str) -> Optional[Path]:
        url = urljoin(fpg_base_url(), zip_url)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        path = self.download_dir / f"{tndsalno}.ZIP"
        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    logger.warning("ZIP 下載失敗 %s status=%s", url, resp.status)
                    return None
                data = await resp.read()
            if not data.startswith(b"PK"):
                logger.warning("ZIP 內容不像 zip: %s", url)
                return None
            path.write_bytes(data)
            logger.info("ZIP 已存 %s (%s bytes)", path, len(data))
            return path
        except Exception:
            logger.exception("ZIP 下載例外 %s", url)
            return None

    async def fetch_cases(
        self,
        bases: list[CaseRecord],
        *,
        delay_seconds: float = 0.4,
    ) -> list[CaseRecord]:
        records: list[CaseRecord] = []
        for index, base in enumerate(bases, start=1):
            logger.info(
                "擷取案件 %s/%s：%s/%s",
                index,
                len(bases),
                base.tndsalno,
                base.inqcnt,
            )
            records.append(await self.enrich_case(base))
            if delay_seconds:
                await asyncio.sleep(delay_seconds)
        return records
