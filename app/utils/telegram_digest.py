"""Telegram 當日公告速覽（短訊息；完整 log 仍在 Actions）。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Sequence

from app.models.case_record import CaseRecord
from app.models.pcc_asset_record import PccAssetRecord

# 低於 Telegram 4096，預留 CI 結尾連結
DIGEST_CHAR_LIMIT = 3500
MAX_ITEMS = 10
DEFAULT_DIGEST_PATH = Path("telegram_digest.txt")


def html_escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def clip(text: str, limit: int = 28) -> str:
    value = " ".join((text or "").split())
    if len(value) <= limit:
        return value
    return value[: max(limit - 1, 1)] + "…"


def short_date(iso: str) -> str:
    """YYYY-MM-DD[T...] → MM/DD；空則 —。"""
    raw = (iso or "").strip()
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return f"{raw[5:7]}/{raw[8:10]}"
    return "—"


def write_digest(text: str, path: Path = DEFAULT_DIGEST_PATH) -> Path:
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def resolve_actions_run_url(explicit: str | None = None) -> str:
    """CI 傳入 ACTIONS_RUN_URL，或由 GITHUB_* 組出 run 連結。"""
    if explicit and explicit.strip():
        return explicit.strip()
    from_env = (os.environ.get("ACTIONS_RUN_URL") or "").strip()
    if from_env:
        return from_env
    server = (os.environ.get("GITHUB_SERVER_URL") or "").rstrip("/")
    repo = (os.environ.get("GITHUB_REPOSITORY") or "").strip()
    run_id = (os.environ.get("GITHUB_RUN_ID") or "").strip()
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return ""


def _job_header(*, success: bool, job_name: str) -> str:
    """仿 GitHub Actions Summary：標題列先放成功／失敗 icon。"""
    icon = "✅" if success else "❌"
    return f"{icon} <b>{html_escape(job_name)}</b>"


def _metrics_line(*, ok: int, err: int, elapsed_s: float) -> str:
    result = "成功" if err == 0 else "失敗"
    return f"{result}｜{ok} 新案｜失敗 {err}｜耗時 {elapsed_s:.0f}s"


def _append_actions_link(lines: list[str], actions_url: str | None) -> None:
    url = resolve_actions_run_url(actions_url)
    if not url:
        return
    lines.append("")
    lines.append(f'<a href="{html_escape(url)}">Actions log</a>')


def _fit(lines: list[str], limit: int = DIGEST_CHAR_LIMIT) -> str:
    text = "\n".join(lines).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def build_fpg_failure_digest(
    *,
    announce_label: str,
    error: str,
    elapsed_s: float,
    actions_url: str | None = None,
) -> str:
    """登入或歸檔早期失敗時的短訊（仍要讓 Telegram 看得到原因）。"""
    lines = [
        _job_header(success=False, job_name="FPG 標售歸檔"),
        f"<b>📅 {html_escape(announce_label)}・台塑標售</b>",
        "登入／歸檔中斷",
        "",
        html_escape(error or "未知錯誤"),
        f"耗時 {elapsed_s:.0f}s",
    ]
    _append_actions_link(lines, actions_url)
    return _fit(lines)


def build_fpg_digest(
    *,
    announce_label: str,
    records: Sequence[CaseRecord],
    page_urls: Sequence[Optional[str]],
    ok: int,
    err: int,
    elapsed_s: float,
    max_items: int = MAX_ITEMS,
    shells: Sequence[CaseRecord] | None = None,
    actions_url: str | None = None,
) -> str:
    shell_list = list(shells) if shells is not None else [
        r for r in records if r.is_incomplete_shell
    ]
    visible_pairs = [
        (record, page_urls[i] if i < len(page_urls) else None)
        for i, record in enumerate(records)
        if not record.is_incomplete_shell
    ]
    success = err == 0 and not shell_list

    lines = [
        _job_header(success=success, job_name="FPG 標售歸檔"),
        f"<b>📅 {html_escape(announce_label)}・台塑標售</b>",
        _metrics_line(ok=ok, err=err, elapsed_s=elapsed_s),
        "",
    ]
    if shell_list:
        lines.append(
            f"⚠ <b>空殼未寫入 Notion（{len(shell_list)}）</b>："
            "公報細節未解析且無報價單"
        )
        for record in shell_list[:max_items]:
            lines.append(f"・{html_escape(record.case_key)}")
        if len(shell_list) > max_items:
            lines.append(f"…另有 {len(shell_list) - max_items} 筆")
        lines.append("請用 --date 該公告日重跑或檢查 parser")
        lines.append("")

    if not visible_pairs and not shell_list:
        lines.append("今日無台灣新案")
    elif visible_pairs:
        shown = visible_pairs[:max_items]
        for i, (record, url) in enumerate(shown, 1):
            summary = clip(
                record.items_summary.split("\n")[0] if record.items_summary else ""
            )
            if not summary:
                summary = "（無品名）"
            mark = "" if record.status != "error" else " ⚠"
            lines.append(
                f"{i}. {html_escape(record.case_key)}｜"
                f"{html_escape(summary)}｜截止 {short_date(record.quote_deadline)}"
                f"{mark}"
            )
            if url:
                lines.append(f'<a href="{html_escape(url)}">Notion</a>')
            lines.append("")

        remaining = len(visible_pairs) - len(shown)
        if remaining > 0:
            lines.append(f"…其餘 {remaining} 筆見 Notion／Actions log")

    if not success:
        _append_actions_link(lines, actions_url)
    return _fit(lines)


def build_pcc_digest(
    *,
    range_label: str,
    records: Sequence[PccAssetRecord],
    ok: int,
    err: int,
    elapsed_s: float,
    max_items: int = MAX_ITEMS,
    actions_url: str | None = None,
) -> str:
    success = err == 0
    lines = [
        _job_header(success=success, job_name="PCC 財物變賣歸檔"),
        f"<b>📅 {html_escape(range_label)}・政府財物變賣</b>",
        _metrics_line(ok=ok, err=err, elapsed_s=elapsed_s),
        "",
    ]
    if not records:
        lines.append("今日無新案")
    else:
        shown = list(records)[:max_items]
        for i, record in enumerate(shown, 1):
            org = clip(record.org_name, 12)
            assets = clip(record.assets_name, 22)
            mark = "" if record.status != "error" else " ⚠"
            lines.append(
                f"{i}. {html_escape(record.case_no or record.pk)}｜"
                f"{html_escape(org)}｜{html_escape(assets)}｜"
                f"截止 {short_date(record.tender_deadline)}"
                f"{mark}"
            )
            if record.source_url:
                lines.append(
                    f'<a href="{html_escape(record.source_url)}">採購網</a>'
                )
            lines.append("")

        remaining = len(records) - len(shown)
        if remaining > 0:
            lines.append(f"…其餘 {remaining} 筆見 Notion／Actions log")

    if not success:
        _append_actions_link(lines, actions_url)
    return _fit(lines)
