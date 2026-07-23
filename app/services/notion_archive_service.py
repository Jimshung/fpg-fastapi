"""Notion 標售案件歸檔：補 schema、upsert、上傳 ZIP。"""
from __future__ import annotations

import asyncio
import calendar
import json
import logging
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

import aiohttp

from app.core.config import settings
from app.models.case_record import CaseRecord
from app.services.notion_zip_contents import (
    ATTACHMENT_MARKER_PREFIX,
    block_plain_text,
    build_attachment_heading_blocks,
    build_media_block,
    managed_attachment_block_ids,
    prepare_zip_members,
)

logger = logging.getLogger(__name__)
API = "https://api.notion.com/v1"

# Notion 約 3 req/s；上傳後稍候再接下一個請求
NOTION_REQUEST_PAUSE = 0.35
NOTION_UPLOAD_PAUSE = 0.25
NOTION_DELETE_PAUSE = 0.2

PRIORITY_COLUMNS = [
    "標售案號",
    "案件類型",
    "廠區聯絡人",
    "品名規格/標售數量",
    "提貨地點",
    "公告日",
    "報價截止日",
    "有附件",
]


def case_type_label(record: CaseRecord) -> str:
    return "競標" if getattr(record, "bid_channel", "") == "cmp" else "一般標售"


def month_view_name(year: int, month: int) -> str:
    """例如 2026/8 →「8 月」。"""
    return f"{month} 月"


def month_date_bounds(year: int, month: int) -> tuple[str, str]:
    """回傳該月公告日篩選用的起迄（含首尾日，ISO）。"""
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start.isoformat(), end.isoformat()


def announce_month_filter(
    year: int,
    month: int,
    *,
    property_ref: str = "公告日",
) -> dict:
    """依公告日切月份。property_ref 建議傳 property id，較穩定。"""
    start, end = month_date_bounds(year, month)
    return {
        "and": [
            {"property": property_ref, "date": {"on_or_after": start}},
            {"property": property_ref, "date": {"on_or_before": end}},
        ]
    }


def is_month_view_name(name: str) -> bool:
    """例如「7 月」「12 月」。"""
    parts = (name or "").strip().split()
    return len(parts) == 2 and parts[0].isdigit() and parts[1] == "月"


def next_calendar_month(today: date | None = None) -> tuple[int, int]:
    base = today or date.today()
    if base.month == 12:
        return base.year + 1, 1
    return base.year, base.month + 1


def normalize_db_id(raw: str) -> str:
    raw = raw.replace("-", "")
    if len(raw) != 32:
        raise ValueError(f"invalid database id length: {raw}")
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


def rich_text(content: str) -> list[dict]:
    return [{"type": "text", "text": {"content": (content or "")[:1800]}}]


class NotionArchiveService:
    def __init__(
        self,
        *,
        token: Optional[str] = None,
        database_id: Optional[str] = None,
        notion_version: Optional[str] = None,
        file_upload_version: Optional[str] = None,
    ) -> None:
        self.token = (token or settings.NOTION_TOKEN or "").strip().strip('"')
        raw_id = (database_id or settings.NOTION_DATABASE_ID or "").strip().strip('"')
        if not self.token or not raw_id:
            raise RuntimeError("缺少 NOTION_TOKEN 或 NOTION_DATABASE_ID")
        self.database_id = normalize_db_id(raw_id)
        self.notion_version = notion_version or settings.NOTION_VERSION
        self.file_upload_version = (
            file_upload_version or settings.NOTION_FILE_UPLOAD_VERSION
        )
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "NotionArchiveService":
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=120)
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if not self._session:
            raise RuntimeError("NotionArchiveService 尚未進入 async context")
        return self._session

    def _headers(self, version: Optional[str] = None, *, json_body: bool = True) -> dict:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": version or self.notion_version,
        }
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        version: str | None = None,
    ) -> dict:
        url = path if path.startswith("http") else f"{API}{path}"
        async with self.session.request(
            method,
            url,
            headers=self._headers(version, json_body=True),
            json=json_body,
        ) as resp:
            text = await resp.text()
            try:
                data = json.loads(text) if text else {}
            except json.JSONDecodeError:
                data = {"raw": text}
            if resp.status >= 400:
                raise RuntimeError(
                    f"{method} {url} -> {resp.status}: "
                    f"{json.dumps(data, ensure_ascii=False)[:900]}"
                )
            return data

    async def ensure_schema(self) -> dict:
        db = await self.request("GET", f"/databases/{self.database_id}")
        props = db.get("properties", {})
        existing = set(props.keys())
        patch: dict = {}

        title_name = next(
            (name for name, meta in props.items() if meta.get("type") == "title"),
            None,
        )
        if title_name and title_name != "標售案號":
            patch[title_name] = {"name": "標售案號"}

        desired = {
            "案件類型": {
                "select": {
                    "options": [
                        {"name": "一般標售", "color": "gray"},
                        {"name": "競標", "color": "red"},
                    ]
                }
            },
            "廠區聯絡人": {"rich_text": {}},
            "公告次數": {"rich_text": {}},
            "品名規格/標售數量": {"rich_text": {}},
            "提貨地點": {"rich_text": {}},
            "公告日": {"date": {}},
            "報價截止日": {"date": {}},
            "品質說明": {"rich_text": {}},
            "提貨期限": {"rich_text": {}},
            "委託公司": {"rich_text": {}},
            "委託部門": {"rich_text": {}},
            "廠商配合事項": {"rich_text": {}},
            "環保代碼": {"rich_text": {}},
            "報價明細摘要": {"rich_text": {}},
            "有附件": {"checkbox": {}},
            "附件": {"files": {}},
            "SHA-256": {"rich_text": {}},
            "狀態": {
                "select": {
                    "options": [
                        {"name": "new", "color": "green"},
                        {"name": "updated", "color": "blue"},
                        {"name": "error", "color": "red"},
                    ]
                }
            },
            "首次發現": {"date": {}},
            "最後確認": {"date": {}},
            "來源 URL": {"url": {}},
        }
        for name, schema in desired.items():
            if name not in existing:
                patch[name] = schema

        if not patch:
            return db
        logger.info("Notion schema patch: %s", sorted(patch))
        return await self.request(
            "PATCH",
            f"/databases/{self.database_id}",
            json_body={"properties": patch},
        )

    async def find_page(self, tndsalno: str, inqcnt: str) -> dict | None:
        data = await self.request(
            "POST",
            f"/databases/{self.database_id}/query",
            json_body={
                "filter": {
                    "and": [
                        {"property": "標售案號", "title": {"equals": tndsalno}},
                        {"property": "公告次數", "rich_text": {"equals": inqcnt}},
                    ]
                },
                "page_size": 5,
            },
        )
        results = data.get("results", [])
        return results[0] if results else None

    async def upload_zip(self, zip_path: Path) -> str:
        return await self.upload_file(
            zip_path,
            filename=zip_path.name,
            content_type="application/zip",
        )

    async def upload_file(
        self,
        path: Path,
        *,
        filename: str | None = None,
        content_type: str = "application/octet-stream",
    ) -> str:
        filename = filename or path.name
        data = path.read_bytes()
        last_error = None
        upload_id = ""
        send_url = ""
        used_version = self.file_upload_version
        for version in (self.file_upload_version, "2025-09-03", "2022-06-28"):
            async with self.session.post(
                f"{API}/file_uploads",
                headers=self._headers(version, json_body=True),
                json={
                    "filename": filename,
                    "content_type": content_type,
                },
            ) as resp:
                body = await resp.json()
                if resp.status < 400:
                    upload_id = body["id"]
                    send_url = (
                        body.get("upload_url")
                        or f"{API}/file_uploads/{upload_id}/send"
                    )
                    used_version = version
                    break
                last_error = (resp.status, body)
        else:
            raise RuntimeError(f"create file_upload failed: {last_error}")

        form = aiohttp.FormData()
        form.add_field(
            "file",
            data,
            filename=filename,
            content_type=content_type,
        )
        async with self.session.post(
            send_url,
            headers=self._headers(used_version, json_body=False),
            data=form,
        ) as resp:
            body = await resp.json()
            if resp.status >= 400:
                raise RuntimeError(f"send file failed {resp.status}: {body}")
        return upload_id

    def _existing_sha(self, page: dict) -> str:
        prop = page.get("properties", {}).get("SHA-256", {})
        texts = prop.get("rich_text") or []
        if not texts:
            return ""
        return texts[0].get("plain_text") or texts[0].get("text", {}).get("content", "")

    async def _list_block_children(self, block_id: str) -> list[dict]:
        results: list[dict] = []
        cursor = None
        version = self.file_upload_version
        while True:
            path = f"/blocks/{block_id}/children?page_size=100"
            if cursor:
                path += f"&start_cursor={cursor}"
            data = await self.request("GET", path, version=version)
            results.extend(data.get("results") or [])
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
            if not cursor:
                break
        return results

    async def _page_has_expanded_attachments(
        self,
        page_id: str,
        zip_sha256: str = "",
    ) -> bool:
        needle = (zip_sha256 or "")[:16]
        for block in await self._list_block_children(page_id):
            if block.get("type") != "paragraph":
                continue
            text = block_plain_text(block)
            if ATTACHMENT_MARKER_PREFIX not in text:
                continue
            if not needle or needle in text:
                return True
        return False

    async def _clear_managed_attachment_blocks(self, page_id: str) -> None:
        """只刪除「標售附件」區段（從標題／標記到頁尾），不碰其他手動內容。"""
        children = await self._list_block_children(page_id)
        for block_id in managed_attachment_block_ids(children):
            await self.request(
                "DELETE",
                f"/blocks/{block_id}",
                version=self.file_upload_version,
            )
            await asyncio.sleep(NOTION_DELETE_PAUSE)

    async def sync_attachment_page_body(
        self,
        page_id: str,
        zip_path: Path,
        *,
        force: bool = False,
        zip_sha256: str = "",
    ) -> None:
        """解壓 ZIP，把 PDF／圖片等內容寫進詳細頁內容區。"""
        if not force and await self._page_has_expanded_attachments(page_id, zip_sha256):
            logger.info("頁面內容已展開附件，略過 %s", zip_path.name)
            return

        with tempfile.TemporaryDirectory(prefix="fpg_zip_") as tmp:
            members = prepare_zip_members(zip_path, Path(tmp))
            if not members:
                logger.warning("ZIP 無可用內容 %s", zip_path)
                return

            children = build_attachment_heading_blocks(
                zip_sha256=zip_sha256,
                zip_name=zip_path.name,
                member_count=len(members),
            )
            for member in members:
                upload_id = await self.upload_file(
                    member.path,
                    filename=member.upload_filename,
                    content_type=member.content_type,
                )
                children.append(build_media_block(member, upload_id))
                await asyncio.sleep(NOTION_UPLOAD_PAUSE)

            await self._clear_managed_attachment_blocks(page_id)
            await self.request(
                "PATCH",
                f"/blocks/{page_id}/children",
                version=self.file_upload_version,
                json_body={"children": children},
            )
            await asyncio.sleep(NOTION_REQUEST_PAUSE)
            logger.info(
                "已展開寫入頁面附件內容 %s（%s 檔）",
                zip_path.name,
                len(members),
            )

    async def upsert_case(self, record: CaseRecord) -> dict:
        today = date.today().isoformat()
        existing = await self.find_page(record.tndsalno, record.inqcnt)
        existing_sha = self._existing_sha(existing) if existing else ""

        has_attachment = bool(record.zip_path and Path(record.zip_path).exists())
        file_upload_id = None
        zip_changed = True
        if has_attachment:
            zip_path = Path(record.zip_path)
            if record.zip_sha256 and record.zip_sha256 == existing_sha and existing:
                logger.info(
                    "ZIP 未變更，略過屬性上傳 %s/%s", record.tndsalno, record.inqcnt
                )
                has_attachment = True
                zip_changed = False
            else:
                file_upload_id = await self.upload_zip(zip_path)
                zip_changed = True

        status_name = "error" if record.status == "error" else (
            "updated" if existing else "new"
        )
        summary_parts = []
        if record.items_summary:
            summary_parts.append(record.items_summary)
        if record.quality_summary:
            summary_parts.append(f"品質說明：{record.quality_summary}")
        if record.pickup_period:
            summary_parts.append(f"提貨期限：{record.pickup_period}")
        if record.error:
            summary_parts.append(f"錯誤：{record.error}")

        props: dict = {
            "標售案號": {
                "title": [{"type": "text", "text": {"content": record.tndsalno}}]
            },
            "案件類型": {"select": {"name": case_type_label(record)}},
            "廠區聯絡人": {"rich_text": rich_text(record.contact_display)},
            "公告次數": {"rich_text": rich_text(record.inqcnt)},
            "品名規格/標售數量": {"rich_text": rich_text(record.items_summary)},
            "提貨地點": {"rich_text": rich_text(record.location)},
            "品質說明": {"rich_text": rich_text(record.quality_summary)},
            "提貨期限": {"rich_text": rich_text(record.pickup_period)},
            "委託公司": {"rich_text": rich_text(record.company)},
            "委託部門": {"rich_text": rich_text(record.department)},
            "廠商配合事項": {"rich_text": rich_text(record.vendor_notes)},
            "環保代碼": {"rich_text": rich_text(record.eco_code)},
            "報價明細摘要": {"rich_text": rich_text("\n".join(summary_parts))},
            "有附件": {"checkbox": has_attachment},
            "SHA-256": {"rich_text": rich_text(record.zip_sha256)},
            "狀態": {"select": {"name": status_name}},
            "最後確認": {"date": {"start": today}},
            "來源 URL": {"url": record.source_url or None},
        }
        if record.announce_date:
            props["公告日"] = {"date": {"start": record.announce_date}}
        if record.quote_deadline:
            props["報價截止日"] = {"date": {"start": record.quote_deadline}}
        if not existing:
            props["首次發現"] = {"date": {"start": today}}
        if file_upload_id and record.zip_path:
            props["附件"] = {
                "files": [
                    {
                        "type": "file_upload",
                        "file_upload": {"id": file_upload_id},
                        "name": Path(record.zip_path).name,
                    }
                ]
            }

        if existing:
            page = await self.request(
                "PATCH",
                f"/pages/{existing['id']}",
                json_body={"properties": props},
            )
        else:
            page = await self.request(
                "POST",
                "/pages",
                json_body={
                    "parent": {"database_id": self.database_id},
                    "properties": props,
                },
            )
        await asyncio.sleep(NOTION_REQUEST_PAUSE)

        if has_attachment and record.zip_path:
            try:
                await self.sync_attachment_page_body(
                    page["id"],
                    Path(record.zip_path),
                    force=zip_changed,
                    zip_sha256=record.zip_sha256 or "",
                )
            except Exception:
                logger.exception(
                    "寫入頁面內容附件失敗 %s/%s",
                    record.tndsalno,
                    record.inqcnt,
                )
        return page

    async def upsert_many(self, records: list[CaseRecord]) -> list[dict]:
        pages = []
        for record in records:
            try:
                page = await self.upsert_case(record)
                pages.append(page)
                logger.info(
                    "Notion upsert ok %s -> %s",
                    record.case_key,
                    page.get("url"),
                )
            except Exception:
                logger.exception("Notion upsert 失敗 %s", record.case_key)
                record.status = "error"
        return pages

    def _table_property_configs(self, name_to_id: dict[str, str]) -> list[dict]:
        configs: list[dict] = []
        for name in PRIORITY_COLUMNS:
            entry: dict = {"property_id": name_to_id[name], "visible": True}
            if name in ("公告日", "報價截止日"):
                entry["date_format"] = "year_month_day"
                entry["time_format"] = "hidden"
            configs.append(entry)
        priority_ids = {name_to_id[n] for n in PRIORITY_COLUMNS}
        for name, prop_id in name_to_id.items():
            if prop_id not in priority_ids:
                configs.append({"property_id": prop_id, "visible": False})
        return configs

    async def _list_view_details(self, *, version: str) -> list[dict]:
        listed = await self.request(
            "GET",
            f"/views?database_id={self.database_id}",
            version=version,
        )
        details: list[dict] = []
        for view in listed.get("results", []):
            detail = await self.request(
                "GET",
                f"/views/{view['id']}",
                version=version,
            )
            details.append(detail)
        return details

    async def _upsert_table_view(
        self,
        *,
        version: str,
        data_source_id: str,
        name_to_id: dict[str, str],
        configs: list[dict],
        view_name: str,
        filter_body: dict | None = None,
        existing_by_name: dict[str, dict],
        rename_from: set[str] | None = None,
        sort_property: str | None = None,
        require_filter: bool = False,
    ) -> dict:
        """建立或更新指定名稱的 table view。

        - filter_body=None：不送 filter 欄位（保留既有篩選，避免弄壞桌面表格）
        - require_filter=True：寫入後必須讀回非空 filter，否則重試／報錯
        """
        sort_prop = (
            sort_property
            or name_to_id.get("報價截止日")
            or name_to_id["公告日"]
        )
        payload: dict = {
            "name": view_name,
            "sorts": [{"property": sort_prop, "direction": "ascending"}],
            "configuration": {"type": "table", "properties": configs},
        }
        if filter_body is not None:
            payload["filter"] = filter_body

        existing = existing_by_name.get(view_name)
        if not existing and rename_from:
            for old_name in rename_from:
                candidate = existing_by_name.get(old_name)
                if not candidate or candidate.get("type") != "table":
                    continue
                # 絕不可把「7 月」這類月 view 改名成桌面表格
                cand_name = candidate.get("name") or old_name
                if is_month_view_name(cand_name):
                    continue
                existing = candidate
                break

        if existing:
            view = await self.request(
                "PATCH",
                f"/views/{existing['id']}",
                version=version,
                json_body=payload,
            )
            logger.info("已更新 Notion view「%s」", view_name)
        else:
            view = await self.request(
                "POST",
                "/views",
                version=version,
                json_body={
                    "database_id": self.database_id,
                    "data_source_id": data_source_id,
                    "type": "table",
                    **payload,
                },
            )
            logger.info("已建立 Notion view「%s」", view_name)

        if require_filter:
            view_id = view.get("id") or (existing or {}).get("id")
            verified = await self.request(
                "GET", f"/views/{view_id}", version=version
            )
            if not verified.get("filter"):
                # 少數情況 PATCH 未帶上 filter；強制再寫一次
                await self.request(
                    "PATCH",
                    f"/views/{view_id}",
                    version=version,
                    json_body={"filter": filter_body},
                )
                verified = await self.request(
                    "GET", f"/views/{view_id}", version=version
                )
            if not verified.get("filter"):
                raise RuntimeError(
                    f"Notion view「{view_name}」公告日篩選寫入失敗（filter 仍為空）"
                )
            view = verified

        existing_by_name[view_name] = view
        return view

    async def ensure_month_views(
        self,
        *,
        version: str,
        data_source_id: str,
        name_to_id: dict[str, str],
        configs: list[dict],
        existing_by_name: dict[str, dict],
        today: date | None = None,
    ) -> None:
        """確保「本月」「下個月」依公告日篩選的 table view 存在。"""
        base = today or date.today()
        announce_prop = name_to_id["公告日"]
        months = [(base.year, base.month), next_calendar_month(base)]
        for year, month in months:
            name = month_view_name(year, month)
            await self._upsert_table_view(
                version=version,
                data_source_id=data_source_id,
                name_to_id=name_to_id,
                configs=configs,
                view_name=name,
                filter_body=announce_month_filter(
                    year, month, property_ref=announce_prop
                ),
                existing_by_name=existing_by_name,
                sort_property=announce_prop,
                require_filter=True,
            )

    async def configure_desktop_table(self) -> None:
        """桌面表格欄位順序 + 本月／下月公告日 view。"""
        views_version = self.file_upload_version
        db = await self.request(
            "GET",
            f"/databases/{self.database_id}",
            version=views_version,
        )
        data_source_id = db["data_sources"][0]["id"]
        ds = await self.request(
            "GET",
            f"/data_sources/{data_source_id}",
            version=views_version,
        )
        name_to_id = {
            name: meta["id"] for name, meta in ds.get("properties", {}).items()
        }
        missing = [n for n in PRIORITY_COLUMNS if n not in name_to_id]
        if missing:
            logger.warning("桌面表格缺少欄位，略過 view 調整: %s", missing)
            return
        if "公告日" not in name_to_id:
            logger.warning("缺少公告日欄位，略過月 view")
            return

        configs = self._table_property_configs(name_to_id)
        details = await self._list_view_details(version=views_version)
        # 空名稱不進索引，避免誤把月 view 改成桌面表格
        existing_by_name = {
            name: detail
            for detail in details
            if (name := (detail.get("name") or "").strip())
        }

        await self._upsert_table_view(
            version=views_version,
            data_source_id=data_source_id,
            name_to_id=name_to_id,
            configs=configs,
            view_name="桌面表格",
            filter_body=None,  # 不送 filter，保留「全部案件」
            existing_by_name=existing_by_name,
            rename_from={"Untitled", "Table"},
            require_filter=False,
        )
        await self.ensure_month_views(
            version=views_version,
            data_source_id=data_source_id,
            name_to_id=name_to_id,
            configs=configs,
            existing_by_name=existing_by_name,
        )
