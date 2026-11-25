"""FPG 投標紀錄：把「歷史資料」已報價案件的報價單截圖存進 Notion 案件頁面。

用法：
  python -m app.scripts.run_bid_history --from 2026-11-23 --to 2026-11-25 --dry-run
  python -m app.scripts.run_bid_history --from 2026-11-23 --to 2026-11-25
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import tempfile
from datetime import date, timedelta
from pathlib import Path

from app.services.bid_screenshot import BidScreenshotter, cookies_from_jar
from app.services.fpg_http_client import FpgHttpClient
from app.services.fpg_urls import fpg_base_url
from app.services.notion_archive_service import NotionArchiveService
from app.services.notion_bid_record import needs_record, sync_bid_record

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    today = date.today()
    parser = argparse.ArgumentParser(description="FPG 投標紀錄截圖 → Notion")
    parser.add_argument(
        "--from", dest="start", type=date.fromisoformat,
        default=today - timedelta(days=7), help="報價日期起（YYYY-MM-DD，預設 7 天前）",
    )
    parser.add_argument(
        "--to", dest="end", type=date.fromisoformat,
        default=today, help="報價日期迄（YYYY-MM-DD，預設今天）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只列出會處理的案件，不截圖不寫入")
    parser.add_argument(
        "--login-retries", type=int, default=1,
        help="FPG 登入（驗證碼）最多嘗試次數，預設 1：失敗就停，避免帳號被鎖",
    )
    parser.add_argument("--force", action="store_true", help="報價時間相同也重做")
    return parser.parse_args()


CASE_ATTEMPTS = 3
CASE_RETRY_PAUSE = 5.0


async def _record_one(fpg, notion, shooter, tmp, row, page) -> bool:
    """單案最多試 CASE_ATTEMPTS 次（FPG 偶爾會中斷連線）；成功才刪暫存截圖。"""
    for attempt in range(1, CASE_ATTEMPTS + 1):
        try:
            html = await fpg.fetch_bid_detail_html(row)
            shot = await shooter.capture(
                html, Path(tmp) / f"{row.tndsalno}-{row.inqcnt}.jpg"
            )
            await sync_bid_record(notion, page, row.quote_time, shot)
            shot.unlink(missing_ok=True)
            return True
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception(
                "投標紀錄失敗 %s/%s（第 %s/%s 次）",
                row.tndsalno, row.inqcnt, attempt, CASE_ATTEMPTS,
            )
            if attempt < CASE_ATTEMPTS:
                await asyncio.sleep(CASE_RETRY_PAUSE)
    return False


async def run(args: argparse.Namespace) -> int:
    start = args.start.strftime("%Y/%m/%d")
    end = args.end.strftime("%Y/%m/%d")
    failures = 0
    # 登入次數有上限，失敗就結束，避免連續送出失敗登入而被鎖帳號
    async with (
        FpgHttpClient(login_retries=args.login_retries) as fpg,
        NotionArchiveService() as notion,
    ):
        await fpg.login()
        rows = await fpg.search_bid_history(start, end)
        await notion.ensure_schema()

        pending = []
        for row in rows:
            page = await notion.find_page(row.tndsalno, row.inqcnt)
            if not page:
                logger.info("略過 %s/%s：Notion 沒有此案件頁", row.tndsalno, row.inqcnt)
            elif not needs_record(page, row.quote_time, force=args.force):
                logger.info("略過 %s/%s：報價時間未變（%s）", row.tndsalno, row.inqcnt, row.quote_time)
            else:
                pending.append((row, page))

        logger.info("待處理投標紀錄：%s 筆（共 %s 筆已報價）", len(pending), len(rows))
        if args.dry_run or not pending:
            for row, _ in pending:
                logger.info("[dry-run] %s/%s 報價時間 %s", row.tndsalno, row.inqcnt, row.quote_time)
            return 0

        cookies = cookies_from_jar(fpg.session.cookie_jar, fpg_base_url())
        with tempfile.TemporaryDirectory(prefix="fpg_bid_") as tmp:
            async with BidScreenshotter(base_url=fpg_base_url(), cookies=cookies) as shooter:
                for row, page in pending:
                    if await _record_one(fpg, notion, shooter, tmp, row, page):
                        logger.info("已記錄 %s/%s（%s）", row.tndsalno, row.inqcnt, row.quote_time)
                    else:
                        failures += 1
    return 1 if failures else 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    raise SystemExit(asyncio.run(run(_parse_args())))


if __name__ == "__main__":
    main()
