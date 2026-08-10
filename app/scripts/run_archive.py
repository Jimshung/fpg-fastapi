"""每日標售案件 HTTP 擷取 → Notion 歸檔。

用法:
  python -m app.scripts.run_archive
  python -m app.scripts.run_archive --date 2026/07/22
  python -m app.scripts.run_archive --start 2026/07/22 --end 2026/07/22
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime
from pathlib import Path

from app.core.config import settings
from app.services.fpg_http_client import FpgHttpClient
from app.services.notion_archive_service import NotionArchiveService
from app.services.taiwan_case_filter import filter_taiwan_cases
from app.utils.telegram_digest import (
    DEFAULT_DIGEST_PATH,
    build_fpg_digest,
    write_digest,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FPG 標售案件 → Notion 歸檔")
    parser.add_argument(
        "--date",
        help="單一公告日 YYYY/MM/DD（預設今天）",
    )
    parser.add_argument("--start", help="公告日起日 YYYY/MM/DD")
    parser.add_argument("--end", help="公告日迄日 YYYY/MM/DD")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="最多處理幾案（0=全部，方便試跑）",
    )
    parser.add_argument(
        "--skip-notion-view",
        action="store_true",
        help="略過調整桌面表格欄位順序",
    )
    parser.add_argument(
        "--include-mainland",
        action="store_true",
        help="不過濾大陸案（預設只歸檔台灣案）",
    )
    parser.add_argument(
        "--digest-file",
        default=str(DEFAULT_DIGEST_PATH),
        help="Telegram 速覽輸出路徑（預設 telegram_digest.txt）",
    )
    return parser.parse_args(argv)


def resolve_date_range(args: argparse.Namespace) -> tuple[str, str]:
    if args.date:
        return args.date, args.date
    if args.start or args.end:
        start = args.start or args.end
        end = args.end or args.start
        return start, end
    today = date.today().strftime("%Y/%m/%d")
    return today, today


def _emit_digest(
    *,
    path: Path,
    announce_label: str,
    records,
    pages,
    ok: int,
    err: int,
    elapsed_s: float,
    shells: list | None = None,
) -> None:
    urls = [(p or {}).get("url") if p else None for p in pages]
    text = build_fpg_digest(
        announce_label=announce_label,
        records=records,
        page_urls=urls,
        ok=ok,
        err=err,
        elapsed_s=elapsed_s,
        shells=shells,
    )
    write_digest(text, path)
    logger.info("已寫入 Telegram digest → %s（%s 字）", path, len(text))


async def run_archive(args: argparse.Namespace) -> int:
    start, end = resolve_date_range(args)
    announce_label = start if start == end else f"{start}~{end}"
    digest_path = Path(args.digest_file)
    started = datetime.now()
    logger.info("開始歸檔公告日 %s ~ %s", start, end)

    if not settings.NOTION_TOKEN or not settings.NOTION_DATABASE_ID:
        logger.error("請先設定 NOTION_TOKEN / NOTION_DATABASE_ID")
        return 2

    records = []
    pages: list = []

    async with FpgHttpClient() as fpg, NotionArchiveService() as notion:
        await fpg.login()
        bases = await fpg.search_bulletin_by_announce_date(start, end)
        if not args.include_mainland:
            bases, skipped = filter_taiwan_cases(bases)
            logger.info(
                "台灣案篩選：保留 %s、排除大陸/非台灣 %s",
                len(bases),
                len(skipped),
            )
            for record in skipped:
                logger.info(
                    "[SKIP] %s 電話=%s 聯絡人=%s",
                    record.case_key,
                    record.plant_phone or "(空)",
                    record.contact_display,
                )
        if args.limit and args.limit > 0:
            bases = bases[: args.limit]
        logger.info("待擷取案件數：%s", len(bases))

        if bases:
            await notion.ensure_schema()
            if not args.skip_notion_view:
                try:
                    await notion.configure_desktop_table()
                except Exception:
                    logger.exception("調整 Notion view 失敗（不中斷歸檔）")
            records = await fpg.fetch_cases(bases)
            to_upsert = []
            for record in records:
                if record.mark_incomplete_shell():
                    logger.error(
                        "[SHELL] 不寫入 Notion %s 聯絡人=%s 截止=%s %s",
                        record.case_key,
                        record.contact_display or "(空)",
                        record.quote_deadline or "(空)",
                        record.error,
                    )
                    continue
                to_upsert.append(record)
            pages = await notion.upsert_many(to_upsert)
            # digest 需要與 records 對齊：空殼對應 None
            page_by_key = {
                r.case_key: p for r, p in zip(to_upsert, pages)
            }
            pages = [page_by_key.get(r.case_key) for r in records]
        else:
            logger.warning("今日無（台灣）公告案件")

    shells = [r for r in records if r.is_incomplete_shell]
    ok = sum(1 for r in records if r.status != "error")
    err = sum(1 for r in records if r.status == "error")
    elapsed = (datetime.now() - started).total_seconds()
    logger.info(
        "完成：成功 %s、失敗 %s、空殼略過 %s、Notion pages %s、耗時 %.1fs",
        ok,
        err,
        len(shells),
        sum(1 for p in pages if p),
        elapsed,
    )
    for record in records:
        if record.is_incomplete_shell:
            flag = "SHELL"
        elif record.status == "error":
            flag = "ERR"
        else:
            flag = "OK"
        logger.info(
            "[%s] %s 聯絡人=%s 地點=%s 截止=%s 附件=%s %s",
            flag,
            record.case_key,
            record.contact_display,
            record.location,
            record.quote_deadline,
            bool(record.zip_path),
            record.error,
        )
    _emit_digest(
        path=digest_path,
        announce_label=announce_label,
        records=records,
        pages=pages,
        ok=ok,
        err=err,
        elapsed_s=elapsed,
        shells=shells,
    )
    return 0 if err == 0 else 1


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    raise SystemExit(asyncio.run(run_archive(args)))


if __name__ == "__main__":
    main(sys.argv[1:])
