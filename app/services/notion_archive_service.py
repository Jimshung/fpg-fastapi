"""Notion 標售案件歸檔：補 schema、upsert、上傳 ZIP。"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional

import aiohttp

from app.core.config import settings
from app.models.case_record import CaseRecord

logger = logging.getLogger(__name__)
API = "https://api.notion.com/v1"

PRIORITY_COLUMNS = [
    "標售案號",
    "廠區聯絡人",
    "公告次數",
    "品名規格/標售數量",
    "提貨地點",
    "公告日",
    "報價截止日",
    "有附件",
]


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
        last_error = None
        upload_id = ""
        send_url = ""
        used_version = self.file_upload_version
        for version in (self.file_upload_version, "2025-09-03", "2022-06-28"):
            async with self.session.post(
                f"{API}/file_uploads",
                headers=self._headers(version, json_body=True),
                json={
                    "filename": zip_path.name,
                    "content_type": "application/zip",
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
            zip_path.read_bytes(),
            filename=zip_path.name,
            content_type="application/zip",
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

    async def upsert_case(self, record: CaseRecord) -> dict:
        today = date.today().isoformat()
        existing = await self.find_page(record.tndsalno, record.inqcnt)
        existing_sha = self._existing_sha(existing) if existing else ""

        has_attachment = bool(record.zip_path and Path(record.zip_path).exists())
        file_upload_id = None
        if has_attachment:
            zip_path = Path(record.zip_path)
            if record.zip_sha256 and record.zip_sha256 == existing_sha and existing:
                logger.info(
                    "ZIP 未變更，略過上傳 %s/%s", record.tndsalno, record.inqcnt
                )
                has_attachment = True
            else:
                file_upload_id = await self.upload_zip(zip_path)

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
        await asyncio.sleep(0.35)  # Notion ~3 req/s
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

    async def configure_desktop_table(self) -> None:
        """把桌面表格可見欄位排成第一眼順序。"""
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

        listed = await self.request(
            "GET",
            f"/views?database_id={self.database_id}",
            version=views_version,
        )
        for view in listed.get("results", []):
            detail = await self.request(
                "GET",
                f"/views/{view['id']}",
                version=views_version,
            )
            if detail.get("type") != "table":
                continue
            name = detail.get("name") or ""
            if name not in ("桌面表格", "Untitled", "", "Table"):
                continue
            await self.request(
                "PATCH",
                f"/views/{view['id']}",
                version=views_version,
                json_body={
                    "name": "桌面表格",
                    "sorts": [
                        {
                            "property": name_to_id["報價截止日"],
                            "direction": "ascending",
                        }
                    ],
                    "configuration": {"type": "table", "properties": configs},
                },
            )
            logger.info("已更新桌面表格欄位順序")
            return
