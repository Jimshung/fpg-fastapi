"""解壓標售 ZIP，準備寫入 Notion 頁面內容的檔案清單。"""
from __future__ import annotations

import mimetypes
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

ATTACHMENT_HEADING = "標售附件"
ATTACHMENT_MARKER_PREFIX = "附件內容｜"
IMAGE_SUFFIXES = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
TIF_SUFFIXES = {".tif", ".tiff"}


@dataclass(frozen=True)
class ZipMember:
    display_name: str
    path: Path
    content_type: str
    block_type: str  # pdf | image | file
    upload_filename: str
    caption: str


def block_plain_text(block: dict) -> str:
    btype = block.get("type") or ""
    rich = (block.get(btype) or {}).get("rich_text") or []
    return "".join(
        (t.get("plain_text") or t.get("text", {}).get("content") or "") for t in rich
    )


def decode_zip_entry_name(info: zipfile.ZipInfo) -> str:
    """盡量還原台塑 ZIP 常見的 Big5／CP950 檔名。"""
    raw = info.filename
    if info.flag_bits & 0x800:
        return Path(raw).name
    for encoding in ("cp950", "big5", "utf-8"):
        try:
            return Path(raw.encode("cp437").decode(encoding)).name
        except UnicodeError:
            continue
    return Path(raw).name


def prepare_zip_members(zip_path: Path, work_dir: Path) -> list[ZipMember]:
    """解壓 ZIP，回傳可上傳的成員清單（TIF 會轉成 PNG）。"""
    prepared: list[ZipMember] = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            display = decode_zip_entry_name(info)
            extracted = work_dir / f"{len(prepared):02d}_{Path(display).name}"
            extracted.parent.mkdir(parents=True, exist_ok=True)
            extracted.write_bytes(zf.read(info))

            suffix = extracted.suffix.lower()
            if suffix == ".pdf":
                prepared.append(
                    ZipMember(
                        display_name=display,
                        path=extracted,
                        content_type="application/pdf",
                        block_type="pdf",
                        upload_filename=display,
                        caption=display,
                    )
                )
                continue

            if suffix in IMAGE_SUFFIXES:
                upload_path = extracted
                upload_filename = display
                content_type = mimetypes.guess_type(display)[0] or "image/png"
                if suffix in TIF_SUFFIXES:
                    png_name = f"{Path(display).stem}.png"
                    upload_path = work_dir / f"{len(prepared):02d}_{png_name}"
                    with Image.open(extracted) as img:
                        img.convert("RGB").save(upload_path, format="PNG")
                    upload_filename = png_name
                    content_type = "image/png"
                prepared.append(
                    ZipMember(
                        display_name=display,
                        path=upload_path,
                        content_type=content_type,
                        block_type="image",
                        upload_filename=upload_filename,
                        caption=display,
                    )
                )
                continue

            prepared.append(
                ZipMember(
                    display_name=display,
                    path=extracted,
                    content_type=mimetypes.guess_type(display)[0]
                    or "application/octet-stream",
                    block_type="file",
                    upload_filename=display,
                    caption=display,
                )
            )
    return prepared


def build_attachment_heading_blocks(
    *,
    zip_sha256: str,
    zip_name: str,
    member_count: int,
) -> list[dict]:
    marker = (
        f"{ATTACHMENT_MARKER_PREFIX}"
        f"{(zip_sha256 or zip_name)[:16]}"
        f"｜{member_count} 個檔案"
    )
    return [
        {
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": ATTACHMENT_HEADING}}]
            },
        },
        {
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": marker}}]
            },
        },
    ]


def build_media_block(member: ZipMember, upload_id: str) -> dict:
    return {
        "type": member.block_type,
        member.block_type: {
            "type": "file_upload",
            "file_upload": {"id": upload_id},
            "caption": [
                {"type": "text", "text": {"content": (member.caption or "")[:2000]}}
            ],
        },
    }


def managed_attachment_block_ids(children: list[dict]) -> list[str]:
    """只清除「標售附件」區段：從標題／標記起算到頁尾，避免誤刪其他內容。"""
    start = None
    for index, block in enumerate(children):
        text = block_plain_text(block)
        if ATTACHMENT_HEADING in text or ATTACHMENT_MARKER_PREFIX in text:
            start = index
            break
    if start is None:
        return []
    return [b["id"] for b in children[start:] if b.get("id")]
