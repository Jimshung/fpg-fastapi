"""FPG 投標紀錄：把歷史頁的報價單截圖寫進 Notion 案件頁面。

頁面本文有一段獨立區段（標題「投標紀錄（報價單截圖）」＋報價時間＋截圖）；
「報價時間」欄位同時是去重依據：欄位與歷史頁相同就略過，不同（重新報價）才重做。
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.services.notion_zip_contents import (
    ATTACHMENT_HEADING,
    ATTACHMENT_MARKER_PREFIX,
    BID_RECORD_HEADING,
    block_plain_text,
)

logger = logging.getLogger(__name__)

BID_TIME_PROPERTY = "報價時間"
BID_TIME_LABEL = "報價時間："
_DELETE_PAUSE = 0.2


def recorded_quote_time(page: dict) -> str:
    prop = (page.get("properties") or {}).get(BID_TIME_PROPERTY) or {}
    texts = prop.get("rich_text") or []
    return "".join(t.get("plain_text") or "" for t in texts).strip()


def needs_record(page: dict, quote_time: str, *, force: bool = False) -> bool:
    return force or recorded_quote_time(page) != quote_time


def build_bid_blocks(quote_time: str, upload_id: str) -> list[dict]:
    def text(content: str) -> list[dict]:
        return [{"type": "text", "text": {"content": content}}]

    return [
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": text(BID_RECORD_HEADING)},
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": text(f"{BID_TIME_LABEL}{quote_time}")},
        },
        {
            "object": "block",
            "type": "image",
            "image": {"type": "file_upload", "file_upload": {"id": upload_id}},
        },
    ]


def bid_section_block_ids(children: list[dict]) -> list[str]:
    """投標紀錄區段：標題起，到下一個標題／附件區段前為止；不碰其他內容。"""
    start = None
    for index, block in enumerate(children):
        if block_plain_text(block) == BID_RECORD_HEADING:
            start = index
            break
    if start is None:
        return []
    ids = [children[start]["id"]]
    for block in children[start + 1 :]:
        text = block_plain_text(block)
        if (
            block.get("type") == "heading_2"
            or ATTACHMENT_HEADING in text
            or ATTACHMENT_MARKER_PREFIX in text
        ):
            break
        if block.get("id"):
            ids.append(block["id"])
    return ids


async def sync_bid_record(notion, page: dict, quote_time: str, image_path: Path) -> None:
    """上傳截圖 → 換掉舊區段 → 最後才更新「報價時間」欄位（中途失敗下次會重試）。"""
    page_id = page["id"]
    upload_id = await notion.upload_file(
        image_path,
        filename=f"bid-{image_path.stem}.jpg",
        content_type="image/jpeg",
    )
    children = await notion._list_block_children(page_id)  # pylint: disable=protected-access
    for block_id in bid_section_block_ids(children):
        await notion.request(
            "DELETE", f"/blocks/{block_id}", version=notion.file_upload_version
        )
        await asyncio.sleep(_DELETE_PAUSE)
    await notion.request(
        "PATCH",
        f"/blocks/{page_id}/children",
        version=notion.file_upload_version,
        json_body={"children": build_bid_blocks(quote_time, upload_id)},
    )
    await notion.request(
        "PATCH",
        f"/pages/{page_id}",
        json_body={
            "properties": {
                BID_TIME_PROPERTY: {
                    "rich_text": [{"type": "text", "text": {"content": quote_time}}]
                }
            }
        },
    )
