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

from app.core.config import settings
from app.services.fpg_http_client import FpgHttpClient
from app.services.notion_archive_service import NotionArchiveService
from app.services.taiwan_case_filter import filter_taiwan_cases

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


async def run_archive(args: argparse.Namespace) -> int:
    start, end = resolve_date_range(args)
    started = datetime.now()
    logger.info("開始歸檔公告日 %s ~ %s", start, end)

    if not settings.NOTION_TOKEN or not settings.NOTION_DATABASE_ID:
        logger.error("請先設定 NOTION_TOKEN / NOTION_DATABASE_ID")
        return 2

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
        if not bases:
            logger.warning("今日無（台灣）公告案件")
            return 0

        await notion.ensure_schema()
        if not args.skip_notion_view:
            try:
                await notion.configure_desktop_table()
            except Exception:
                logger.exception("調整 Notion view 失敗（不中斷歸檔）")

        records = await fpg.fetch_cases(bases)
        pages = await notion.upsert_many(records)

    ok = sum(1 for r in records if r.status != "error")
    err = sum(1 for r in records if r.status == "error")
    elapsed = (datetime.now() - started).total_seconds()
    logger.info(
        "完成：成功 %s、失敗 %s、Notion pages %s、耗時 %.1fs",
        ok,
        err,
        len(pages),
        elapsed,
    )
    for record in records:
        flag = "OK" if record.status != "error" else "ERR"
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
    return 0 if err == 0 else 1


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    raise SystemExit(asyncio.run(run_archive(args)))


if __name__ == "__main__":
    main(sys.argv[1:])
