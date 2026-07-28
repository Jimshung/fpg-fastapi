"""政府財物變賣 HTTP 擷取 → Notion 歸檔。

用法（日常＝公告日節奏，對齊台塑）:
  python -m app.scripts.run_pcc_archive
  python -m app.scripts.run_pcc_archive --date 2026/07/22
  python -m app.scripts.run_pcc_archive --start 2026/07/22 --end 2026/07/29
  python -m app.scripts.run_pcc_archive --days 3

歷史回填（依截止投標）:
  python -m app.scripts.run_pcc_archive --deadline-from 2026/07/29
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta

from app.core.config import settings
from app.services.pcc_http_client import DEFAULT_DEADLINE_END, PccHttpClient
from app.services.pcc_notion_archive_service import PccNotionArchiveService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PCC 財物變賣 → Notion 歸檔")
    parser.add_argument(
        "--date",
        help="單一公告日 YYYY/MM/DD（預設今天；與 --deadline-from 互斥）",
    )
    parser.add_argument("--start", help="公告日起日 YYYY/MM/DD")
    parser.add_argument("--end", help="公告日迄日 YYYY/MM/DD")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="未指定起迄時，公告日往回 N 天（含今天；例 --days 3）",
    )
    parser.add_argument(
        "--deadline-from",
        help="改依截止投標回填：起日 YYYY/MM/DD（迄日見 --deadline-to）",
    )
    parser.add_argument(
        "--deadline-to",
        help="截止投標迄日 YYYY/MM/DD（預設 2027/12/31）",
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


def resolve_announce_range(args: argparse.Namespace) -> tuple[date, date]:
    if args.date:
        d = parse_slash_date(args.date)
        return d, d
    if args.start or args.end:
        start = parse_slash_date(args.start or args.end)
        end = parse_slash_date(args.end or args.start)
        if end < start:
            start, end = end, start
        return start, end
    today = date.today()
    if args.days is not None:
        n = max(args.days, 0)
        return today - timedelta(days=n), today
    return today, today


def resolve_deadline_range(args: argparse.Namespace) -> tuple[date, date]:
    start = parse_slash_date(args.deadline_from)
    end = (
        parse_slash_date(args.deadline_to)
        if args.deadline_to
        else DEFAULT_DEADLINE_END
    )
    if end < start:
        start, end = end, start
    return start, end


async def run_pcc_archive(args: argparse.Namespace) -> int:
    use_deadline = bool(args.deadline_from)
    if use_deadline and (args.date or args.start or args.end or args.days is not None):
        logger.error("請勿同時指定公告日參數與 --deadline-from")
        return 2

    if use_deadline:
        start, end = resolve_deadline_range(args)
        mode_label = "截止投標"
    else:
        start, end = resolve_announce_range(args)
        mode_label = "公告日"

    started = datetime.now()
    logger.info("開始 PCC 歸檔（%s %s ~ %s）", mode_label, start, end)

    if not settings.NOTION_TOKEN or not settings.PCC_NOTION_DATABASE_ID:
        logger.error("請先設定 NOTION_TOKEN / PCC_NOTION_DATABASE_ID")
        return 2

    async with PccHttpClient() as pcc, PccNotionArchiveService() as notion:
        if use_deadline:
            bases = await pcc.search_by_tender_deadline(start, end)
        else:
            bases = await pcc.search_by_announce_date(start, end)
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
            "[%s] %s %s 機關=%s 財物=%s 公告=%s 截止=%s %s",
            flag,
            record.pk,
            record.case_no,
            record.org_name,
            (record.assets_name or "")[:40],
            record.announce_date,
            record.tender_deadline,
            record.error,
        )
    return 0 if err == 0 else 1


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    raise SystemExit(asyncio.run(run_pcc_archive(args)))


if __name__ == "__main__":
    main(sys.argv[1:])
