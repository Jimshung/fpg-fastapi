"""政府財物變賣 HTTP 擷取 → Notion 歸檔。

用法:
  python -m app.scripts.run_pcc_archive
  python -m app.scripts.run_pcc_archive --start 2026/07/23 --end 2026/07/29
  python -m app.scripts.run_pcc_archive --days 7 --limit 5
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta

from app.core.config import settings
from app.services.pcc_http_client import PccHttpClient, default_deadline_window
from app.services.pcc_notion_archive_service import PccNotionArchiveService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PCC 財物變賣 → Notion 歸檔")
    parser.add_argument("--start", help="截止投標起日 YYYY/MM/DD")
    parser.add_argument("--end", help="截止投標迄日 YYYY/MM/DD")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="未指定起迄時，從今天起往後 N 天（預設 7）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="最多處理幾案（0=全部）",
    )
    parser.add_argument(
        "--skip-notion-view",
        action="store_true",
        help="略過調整桌面／月 view",
    )
    return parser.parse_args(argv)


def parse_slash_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y/%m/%d").date()


def resolve_deadline_range(args: argparse.Namespace) -> tuple[date, date]:
    if args.start or args.end:
        start = parse_slash_date(args.start or args.end)
        end = parse_slash_date(args.end or args.start)
        if end < start:
            start, end = end, start
        return start, end
    start, _ = default_deadline_window()
    return start, start + timedelta(days=max(args.days, 0))


async def run_pcc_archive(args: argparse.Namespace) -> int:
    start, end = resolve_deadline_range(args)
    started = datetime.now()
    logger.info("開始 PCC 歸檔（截止投標 %s ~ %s）", start, end)

    if not settings.NOTION_TOKEN or not settings.PCC_NOTION_DATABASE_ID:
        logger.error("請先設定 NOTION_TOKEN / PCC_NOTION_DATABASE_ID")
        return 2

    async with PccHttpClient() as pcc, PccNotionArchiveService() as notion:
        bases = await pcc.search_by_tender_deadline(start, end)
        if args.limit and args.limit > 0:
            bases = bases[: args.limit]
        logger.info("待擷取案件數：%s", len(bases))
        if not bases:
            logger.warning("區間內無財物變賣案件")
            return 0

        await notion.ensure_schema()
        if not args.skip_notion_view:
            try:
                await notion.configure_desktop_table()
            except Exception:
                logger.exception("調整 PCC Notion view 失敗（不中斷歸檔）")

        records = await pcc.fetch_cases(bases)
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
            "[%s] %s %s 機關=%s 財物=%s 截止=%s %s",
            flag,
            record.pk,
            record.case_no,
            record.org_name,
            (record.assets_name or "")[:40],
            record.tender_deadline,
            record.error,
        )
    return 0 if err == 0 else 1


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    raise SystemExit(asyncio.run(run_pcc_archive(args)))


if __name__ == "__main__":
    main(sys.argv[1:])
