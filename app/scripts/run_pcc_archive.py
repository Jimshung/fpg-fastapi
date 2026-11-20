"""政府財物變賣 HTTP 擷取 → Notion 歸檔。

用法（日常＝公告日節奏，對齊台塑）:
  python -m app.scripts.run_pcc_archive
  python -m app.scripts.run_pcc_archive --date 2026/07/22
  python -m app.scripts.run_pcc_archive --start 2026/07/22 --end 2026/07/29
  python -m app.scripts.run_pcc_archive --days 3

低頻探測＋自動補洞（排程用）:
  python -m app.scripts.run_pcc_archive --catch-up
  # 從 Notion 最新公告日補到今天（最多回推 CATCH_UP_MAX_DAYS 天），只擷取尚未成功歸檔的案件

歷史回填（依截止投標）:
  python -m app.scripts.run_pcc_archive --deadline-from 2026/07/29
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from app.core.config import settings
from app.services.pcc_http_client import (
    DEFAULT_DEADLINE_END,
    PccHttpClient,
    PccWafBlockedError,
)
from app.services.pcc_notion_archive_service import PccNotionArchiveService
from app.utils.telegram_digest import (
    DEFAULT_DIGEST_PATH,
    build_pcc_digest,
    write_digest,
)

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
        "--catch-up",
        action="store_true",
        help="從 Notion 最新公告日補到今天，只擷取尚未成功歸檔的案件（與日期參數互斥）",
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
    parser.add_argument(
        "--digest-file",
        default=str(DEFAULT_DIGEST_PATH),
        help="Telegram 速覽輸出路徑（預設 telegram_digest.txt）",
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


def resolve_catch_up_range(
    latest: date | None, today: date, *, max_days: int = 14
) -> tuple[date, date]:
    """補洞區間：從 Notion 最新公告日（含當天，可能只歸檔了一部分）到今天。"""
    floor = today - timedelta(days=max_days)
    if latest is None or latest > today:
        return today, today
    return max(latest, floor), today


def select_unarchived(bases: list, archived_pks: set[str]) -> list:
    """只留尚未成功歸檔的案件，避免每次探測都重抓詳情頁。"""
    return [b for b in bases if b.pk not in archived_pks]


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


def _emit_digest(
    *,
    path: Path,
    range_label: str,
    records,
    ok: int,
    err: int,
    elapsed_s: float,
) -> None:
    text = build_pcc_digest(
        range_label=range_label,
        records=records,
        ok=ok,
        err=err,
        elapsed_s=elapsed_s,
    )
    write_digest(text, path)
    logger.info("已寫入 Telegram digest → %s（%s 字）", path, len(text))

# 遭 WAF 封鎖時的結束碼（workflow 據此不再立刻重跑，等下一個排程時段）
WAF_EXIT_CODE = 3
# --catch-up 最多回推天數
CATCH_UP_MAX_DAYS = 14


async def run_pcc_archive(args: argparse.Namespace) -> int:
    use_deadline = bool(args.deadline_from)
    if use_deadline and (args.date or args.start or args.end or args.days is not None):
        logger.error("請勿同時指定公告日參數與 --deadline-from")
        return 2
    if args.catch_up and (
        use_deadline or args.date or args.start or args.end or args.days is not None
    ):
        logger.error("--catch-up 不可與日期參數同時使用")
        return 2
    if not settings.NOTION_TOKEN or not settings.PCC_NOTION_DATABASE_ID:
        logger.error("請先設定 NOTION_TOKEN / PCC_NOTION_DATABASE_ID")
        return 2

    if args.catch_up:
        async with PccNotionArchiveService() as notion:
            latest = await notion.latest_announce_date()
        start, end = resolve_catch_up_range(
            latest, date.today(), max_days=CATCH_UP_MAX_DAYS
        )
        mode_label = "補洞（公告日）"
        logger.info("Notion 最新公告日：%s", latest)
    elif use_deadline:
        start, end = resolve_deadline_range(args)
        mode_label = "截止投標"
    else:
        start, end = resolve_announce_range(args)
        mode_label = "公告日"

    range_label = (
        start.isoformat()
        if start == end
        else f"{start.isoformat()}~{end.isoformat()}"
    )
    digest_path = Path(args.digest_file)
    started = datetime.now()
    logger.info("開始 PCC 歸檔（%s %s ~ %s）", mode_label, start, end)

    records = []
    pages: list = []

    async with PccHttpClient() as pcc, PccNotionArchiveService() as notion:
        try:
            if use_deadline:
                bases = await pcc.search_by_tender_deadline(start, end)
            else:
                bases = await pcc.search_by_announce_date(start, end)
        except PccWafBlockedError as exc:
            logger.error("PCC 遭 WAF 封鎖，本次不再請求：%s", exc)
            write_digest(
                f"🚫 PCC 遭 WAF 封鎖（{range_label}），本次未擷取任何案件",
                digest_path,
            )
            return WAF_EXIT_CODE
        if args.catch_up and bases:
            archived = await notion.archived_pks_since(start)
            total = len(bases)
            bases = select_unarchived(bases, archived)
            logger.info("補洞：搜尋到 %s 筆，已歸檔 %s 筆，待補 %s 筆", total, total - len(bases), len(bases))
        if args.limit and args.limit > 0:
            bases = bases[: args.limit]
        logger.info("待擷取案件數：%s", len(bases))

        if bases:
            await notion.ensure_schema()
            if not args.skip_notion_view:
                try:
                    await notion.configure_desktop_table()
                except Exception:
                    logger.exception("調整 PCC Notion view 失敗（不中斷歸檔）")
            records = await pcc.fetch_cases(bases)
            pages = await notion.upsert_many(records)
        elif args.catch_up:
            logger.info("區間內沒有待補案件（皆已歸檔）")
        else:
            logger.warning("區間內無財物變賣案件")

    ok = sum(1 for r in records if r.status != "error")
    err = sum(1 for r in records if r.status == "error")
    elapsed = (datetime.now() - started).total_seconds()
    logger.info(
        "完成：成功 %s、失敗 %s、Notion pages %s、耗時 %.1fs",
        ok,
        err,
        sum(1 for p in pages if p),
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
    _emit_digest(
        path=digest_path,
        range_label=range_label,
        records=records,
        ok=ok,
        err=err,
        elapsed_s=elapsed,
    )
    if err and pcc.waf_blocked:
        return WAF_EXIT_CODE
    return 0 if err == 0 else 1


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    raise SystemExit(asyncio.run(run_pcc_archive(args)))


if __name__ == "__main__":
    main(sys.argv[1:])
