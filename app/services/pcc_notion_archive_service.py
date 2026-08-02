"""政府財物變賣 → Notion 歸檔（獨立 database）。"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date
from typing import Optional

import aiohttp

from app.core.config import settings
from app.models.pcc_asset_record import PccAssetRecord
from app.services.notion_archive_service import (
    NOTION_REQUEST_PAUSE,
    announce_month_filter,
    is_month_view_name,
    month_view_name,
    next_calendar_month,
    normalize_db_id,
    rich_text,
)

logger = logging.getLogger(__name__)
API = "https://api.notion.com/v1"
# 頁面 body 受管區段標記（side peek 不用點 View details 也能讀）
SUMMARY_MARKER = "案情摘要｜"
SUMMARY_HEADING = "案情摘要"
NOTION_TEXT_LIMIT = 1800
NOTION_DELETE_PAUSE = 0.2

PRIORITY_COLUMNS = [
    "標案案號",
    "機關名稱",
    "財物名稱",
    "公告日期",
    "截止投標",
    "開標時間",
    "底價金額",
    "變賣標的所在地",
    "聯絡人",
]


def is_valid_email(value: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value or ""))


def _fmt_display_dt(iso: str) -> str:
    text = (iso or "").strip()
    if not text:
        return "—"
    if "T" in text:
        return text.replace("T", " ").replace("+08:00", "").rstrip("Z")
    return text


def _rich_chunks(content: str) -> list[dict]:
    text = (content or "").strip() or "—"
    parts: list[dict] = []
    for i in range(0, len(text), NOTION_TEXT_LIMIT):
        parts.append(
            {"type": "text", "text": {"content": text[i : i + NOTION_TEXT_LIMIT]}}
        )
    return parts


def _heading_block(text: str, *, level: int = 2) -> dict:
    key = f"heading_{level}"
    return {
        "object": "block",
        "type": key,
        key: {"rich_text": _rich_chunks(text)[:1]},
    }


def _paragraph_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _rich_chunks(text)},
    }


def _link_paragraph(label: str, url: str) -> dict:
    """可點連結（短標籤，免掃超長 URL）。"""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {"type": "text", "text": {"content": f"{label}："}},
                {
                    "type": "text",
                    "text": {
                        "content": "開啟採購網詳情",
                        "link": {"url": url},
                    },
                },
            ]
        },
    }


def _bulleted_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rich_chunks(text)},
    }


def _divider_block() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _block_plain_text(block: dict) -> str:
    btype = block.get("type") or ""
    payload = block.get(btype) or {}
    texts = payload.get("rich_text") or []
    return "".join(
        (t.get("plain_text") or t.get("text", {}).get("content") or "") for t in texts
    )


def build_summary_blocks(record: PccAssetRecord) -> list[dict]:
    """Side peek 正文：重點案情，免點 View details。"""
    contact = record.contact_display
    email = (record.email or "").strip()
    if email:
        contact = f"{contact} / {email}" if contact else email

    blocks: list[dict] = [
        _heading_block(SUMMARY_HEADING, level=2),
        _paragraph_block(f"{SUMMARY_MARKER}pk={record.pk}"),
    ]
    # 來源放最前，side peek 一開就能點
    if record.source_url:
        blocks.append(_link_paragraph("來源", record.source_url))
    blocks.extend(
        [
            _bulleted_block(f"機關：{record.org_name or '—'}"),
            _bulleted_block(f"財物：{record.assets_name or '—'}"),
            _bulleted_block(
                f"公告：{_fmt_display_dt(record.announce_date)}"
                f"　截止：{_fmt_display_dt(record.tender_deadline)}"
                f"　開標：{_fmt_display_dt(record.open_time)}"
            ),
            _bulleted_block(f"底價：{record.reserve_price or '—'}"),
            _bulleted_block(f"所在地：{record.location or '—'}"),
            _bulleted_block(f"開標地點：{record.open_place or '—'}"),
            _bulleted_block(f"聯絡：{contact or '—'}"),
        ]
    )

    long_sections = (
        ("投標資格", record.qualification),
        ("文件領取", record.document_howto),
        ("附加說明", record.extra_notes),
    )
    for title, body in long_sections:
        text = (body or "").strip()
        if not text:
            continue
        blocks.append(_divider_block())
        blocks.append(_heading_block(title, level=3))
        # 長文切成多段，避免單 block 過長
        for i in range(0, len(text), NOTION_TEXT_LIMIT):
            blocks.append(_paragraph_block(text[i : i + NOTION_TEXT_LIMIT]))
    return blocks


class PccNotionArchiveService:
    def __init__(
        self,
        *,
        token: Optional[str] = None,
        database_id: Optional[str] = None,
        notion_version: Optional[str] = None,
        file_upload_version: Optional[str] = None,
    ) -> None:
        self.token = (token or settings.NOTION_TOKEN or "").strip().strip('"')
        raw_id = (
            database_id or settings.PCC_NOTION_DATABASE_ID or ""
        ).strip().strip('"')
        if not self.token or not raw_id:
            raise RuntimeError("缺少 NOTION_TOKEN 或 PCC_NOTION_DATABASE_ID")
        self.database_id = normalize_db_id(raw_id)
        self.notion_version = notion_version or settings.NOTION_VERSION
        self.file_upload_version = (
            file_upload_version or settings.NOTION_FILE_UPLOAD_VERSION
        )
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "PccNotionArchiveService":
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
            raise RuntimeError("PccNotionArchiveService 尚未進入 async context")
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
        if title_name and title_name != "標案案號":
            patch[title_name] = {"name": "標案案號"}

        desired = {
            "系統PK": {"rich_text": {}},
            "機關名稱": {"rich_text": {}},
            "機關代碼": {"rich_text": {}},
            "財物名稱": {"rich_text": {}},
            "公告次數": {"rich_text": {}},
            "公告日期": {"date": {}},
            "截止投標": {"date": {}},
            "開標時間": {"date": {}},
            "開標地點": {"rich_text": {}},
            "變賣標的所在地": {"rich_text": {}},
            "底價金額": {"rich_text": {}},
            "聯絡人": {"rich_text": {}},
            "電子郵件": {"email": {}},
            "投標資格摘要": {"rich_text": {}},
            "文件領取方式": {"rich_text": {}},
            "附加說明": {"rich_text": {}},
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
        logger.info("PCC Notion schema patch: %s", sorted(patch))
        return await self.request(
            "PATCH",
            f"/databases/{self.database_id}",
            json_body={"properties": patch},
        )

    async def find_page_by_pk(self, pk: str) -> dict | None:
        data = await self.request(
            "POST",
            f"/databases/{self.database_id}/query",
            json_body={
                "filter": {
                    "property": "系統PK",
                    "rich_text": {"equals": pk},
                },
                "page_size": 1,
            },
        )
        results = data.get("results") or []
        return results[0] if results else None

    @staticmethod
    def _date_prop(value: str) -> dict | None:
        if not value:
            return None
        # Notion date accepts date or datetime with timezone
        return {"date": {"start": value}}

    async def _list_block_children(self, block_id: str) -> list[dict]:
        results: list[dict] = []
        cursor = None
        while True:
            path = f"/blocks/{block_id}/children?page_size=100"
            if cursor:
                path += f"&start_cursor={cursor}"
            data = await self.request("GET", path)
            results.extend(data.get("results") or [])
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
            if not cursor:
                break
        return results

    async def _clear_summary_blocks(self, page_id: str) -> None:
        """刪除受管「案情摘要」區段（從標記／標題到頁尾）。"""
        children = await self._list_block_children(page_id)
        start = None
        for i, block in enumerate(children):
            text = _block_plain_text(block)
            if SUMMARY_MARKER in text or text.strip() == SUMMARY_HEADING:
                start = i
                break
        if start is None:
            return
        for block in children[start:]:
            block_id = block.get("id")
            if not block_id:
                continue
            await self.request("DELETE", f"/blocks/{block_id}")
            await asyncio.sleep(NOTION_DELETE_PAUSE)

    async def sync_page_body(self, page_id: str, record: PccAssetRecord) -> None:
        """把重點案情寫進頁面 body，side peek 直接可見。"""
        children = build_summary_blocks(record)
        if not children:
            return
        await self._clear_summary_blocks(page_id)
        # Notion 單次 append 上限 100
        for i in range(0, len(children), 100):
            await self.request(
                "PATCH",
                f"/blocks/{page_id}/children",
                json_body={"children": children[i : i + 100]},
            )
            await asyncio.sleep(NOTION_REQUEST_PAUSE)
        logger.info("已寫入 PCC 案情摘要 body pk=%s", record.pk)

    async def upsert_case(self, record: PccAssetRecord) -> dict:
        today = date.today().isoformat()
        existing = await self.find_page_by_pk(record.pk) if record.pk else None
        status_name = (
            "error"
            if record.status == "error"
            else ("updated" if existing else "new")
        )
        email = (record.email or "").strip()
        email_ok = is_valid_email(email)
        contact = record.contact_display
        if email and not email_ok:
            contact = f"{contact} / {email}" if contact else email

        props: dict = {
            "標案案號": {
                "title": [
                    {
                        "type": "text",
                        "text": {"content": record.case_no or record.pk},
                    }
                ]
            },
            "系統PK": {"rich_text": rich_text(record.pk)},
            "機關名稱": {"rich_text": rich_text(record.org_name)},
            "機關代碼": {"rich_text": rich_text(record.org_id)},
            "財物名稱": {"rich_text": rich_text(record.assets_name)},
            "公告次數": {"rich_text": rich_text(record.announce_seq)},
            "開標地點": {"rich_text": rich_text(record.open_place)},
            "變賣標的所在地": {"rich_text": rich_text(record.location)},
            "底價金額": {"rich_text": rich_text(record.reserve_price)},
            "聯絡人": {"rich_text": rich_text(contact)},
            "投標資格摘要": {"rich_text": rich_text(record.qualification)},
            "文件領取方式": {"rich_text": rich_text(record.document_howto)},
            "附加說明": {"rich_text": rich_text(record.extra_notes)},
            "狀態": {"select": {"name": status_name}},
            "最後確認": {"date": {"start": today}},
            "來源 URL": {"url": record.source_url or None},
        }
        if email_ok:
            props["電子郵件"] = {"email": email}
        for key, raw in (
            ("公告日期", record.announce_date),
            ("截止投標", record.tender_deadline),
            ("開標時間", record.open_time),
        ):
            prop = self._date_prop(raw)
            if prop:
                props[key] = prop
        if not existing:
            props["首次發現"] = {"date": {"start": today}}

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
        page_id = page.get("id") or (existing or {}).get("id")
        if page_id and record.status != "error":
            try:
                await self.sync_page_body(page_id, record)
            except Exception:
                logger.exception("PCC 案情摘要 body 寫入失敗 %s", record.case_key)
        return page

    async def upsert_many(self, records: list[PccAssetRecord]) -> list[dict | None]:
        pages: list[dict | None] = []
        for record in records:
            try:
                page = await self.upsert_case(record)
                pages.append(page)
                logger.info(
                    "PCC Notion upsert ok %s %s -> %s",
                    record.pk,
                    record.case_no,
                    page.get("url"),
                )
            except Exception:
                logger.exception("PCC Notion upsert 失敗 %s", record.case_key)
                record.status = "error"
                record.error = record.error or "notion upsert failed"
                pages.append(None)
        return pages

    def _table_property_configs(self, name_to_id: dict[str, str]) -> list[dict]:
        configs: list[dict] = []
        for name in PRIORITY_COLUMNS:
            if name not in name_to_id:
                continue
            entry: dict = {"property_id": name_to_id[name], "visible": True}
            if name in ("公告日期", "截止投標", "開標時間"):
                entry["date_format"] = "year_month_day"
                entry["time_format"] = "hidden"
            configs.append(entry)
        priority_ids = {c["property_id"] for c in configs}
        for _name, prop_id in name_to_id.items():
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
            details.append(
                await self.request(
                    "GET", f"/views/{view['id']}", version=version
                )
            )
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
        sort_prop = (
            sort_property
            or name_to_id.get("公告日期")
            or name_to_id.get("截止投標")
            or name_to_id["標案案號"]
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
            logger.info("已更新 PCC Notion view「%s」", view_name)
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
            logger.info("已建立 PCC Notion view「%s」", view_name)

        if require_filter:
            view_id = view.get("id") or (existing or {}).get("id")
            verified = await self.request(
                "GET", f"/views/{view_id}", version=version
            )
            if not verified.get("filter"):
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
                    f"PCC Notion view「{view_name}」截止投標篩選寫入失敗"
                )
            view = verified

        existing_by_name[view_name] = view
        return view

    async def configure_desktop_table(self) -> None:
        """桌面表格（預設依公告日排序）+ 本月／下月（依截止投標篩選）。"""
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
            logger.warning("PCC 桌面表格缺少欄位，略過 view 調整: %s", missing)
            return
        if "截止投標" not in name_to_id:
            logger.warning("缺少截止投標欄位，略過月 view")
            return

        configs = self._table_property_configs(name_to_id)
        details = await self._list_view_details(version=views_version)
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
            filter_body=None,
            existing_by_name=existing_by_name,
            rename_from={"Untitled", "Table", "All Tasks"},
            require_filter=False,
        )

        deadline_prop = name_to_id["截止投標"]
        base = date.today()
        for year, month in ((base.year, base.month), next_calendar_month(base)):
            name = month_view_name(year, month)
            # 重用 FPG helper，但改指向「截止投標」property id
            filt = announce_month_filter(year, month, property_ref=deadline_prop)
            await self._upsert_table_view(
                version=views_version,
                data_source_id=data_source_id,
                name_to_id=name_to_id,
                configs=configs,
                view_name=name,
                filter_body=filt,
                existing_by_name=existing_by_name,
                sort_property=deadline_prop,
                require_filter=True,
            )




