"""--catch-up：補洞區間、只擷取未歸檔案件、Notion 查詢。"""
import asyncio
from datetime import date

from app.models.pcc_asset_record import PccAssetRecord
from app.scripts.run_pcc_archive import (
    parse_args,
    resolve_catch_up_range,
    select_unarchived,
)
from app.services.pcc_notion_archive_service import PccNotionArchiveService

TODAY = date(2026, 11, 21)


def test_range_starts_at_latest_archived_day_inclusive():
    assert resolve_catch_up_range(date(2026, 11, 18), TODAY) == (date(2026, 11, 18), TODAY)


def test_range_is_capped():
    assert resolve_catch_up_range(date(2026, 1, 1), TODAY, max_days=14) == (date(2026, 11, 7), TODAY)


def test_range_without_data_or_future_date_is_today():
    assert resolve_catch_up_range(None, TODAY) == (TODAY, TODAY)
    assert resolve_catch_up_range(date(2026, 12, 1), TODAY) == (TODAY, TODAY)


def test_select_unarchived_keeps_only_missing():
    bases = [PccAssetRecord(pk=p) for p in ("1", "2", "3")]
    assert [b.pk for b in select_unarchived(bases, {"2"})] == ["1", "3"]


def test_catch_up_flag_parses():
    assert parse_args(["--catch-up"]).catch_up is True
    assert parse_args([]).catch_up is False


class _FakeNotion(PccNotionArchiveService):
    def __init__(self, pages):
        self.database_id = "db"
        self._pages = pages
        self.bodies = []

    async def request(self, method, path, *, json_body=None, version=None):
        self.bodies.append(json_body)
        return self._pages.pop(0)


def _page(pk, day):
    return {
        "properties": {
            "系統PK": {"rich_text": [{"plain_text": pk}]},
            "公告日期": {"date": {"start": day}},
        }
    }


def test_archived_pks_paginates_and_excludes_error_status():
    n = _FakeNotion([
        {"results": [_page("A", "2026-11-20")], "has_more": True, "next_cursor": "c1"},
        {"results": [_page("B", "2026-11-21")], "has_more": False},
    ])
    assert asyncio.run(n.archived_pks_since(date(2026, 11, 20))) == {"A", "B"}
    assert n.bodies[1]["start_cursor"] == "c1"
    conds = n.bodies[0]["filter"]["and"]
    assert {"property": "狀態", "select": {"does_not_equal": "error"}} in conds


def test_latest_announce_date():
    n = _FakeNotion([{"results": [_page("A", "2026-11-18T00:00:00.000+08:00")]}])
    assert asyncio.run(n.latest_announce_date()) == date(2026, 11, 18)
    assert asyncio.run(_FakeNotion([{"results": []}]).latest_announce_date()) is None


# ---- 端到端：run_pcc_archive --catch-up 的串接（假 PCC / 假 Notion）----
import app.scripts.run_pcc_archive as runmod  # noqa: E402
from app.services.pcc_http_client import PccWafBlockedError  # noqa: E402


class _Ctx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _wire(monkeypatch, tmp_path, *, search):
    calls = {"searched": None, "fetched": [], "upserted": []}

    class FakePcc(_Ctx):
        waf_blocked = False

        async def search_by_announce_date(self, start, end):
            calls["searched"] = (start, end)
            return search()

        async def fetch_cases(self, bases):
            calls["fetched"] = [b.pk for b in bases]
            for b in bases:
                b.status = "ok"
            return bases

    class FakeNotion(_Ctx):
        async def latest_announce_date(self):
            return date(2026, 11, 18)

        async def archived_pks_since(self, start):
            return {"old"}

        async def ensure_schema(self):
            return {}

        async def upsert_many(self, records):
            calls["upserted"] = [r.pk for r in records]
            return [{} for _ in records]

    class FakeDate(date):
        @classmethod
        def today(cls):
            return TODAY

    monkeypatch.setattr(runmod, "PccHttpClient", FakePcc)
    monkeypatch.setattr(runmod, "PccNotionArchiveService", FakeNotion)
    monkeypatch.setattr(runmod, "date", FakeDate)
    monkeypatch.setattr(runmod.settings, "NOTION_TOKEN", "t")
    monkeypatch.setattr(runmod.settings, "PCC_NOTION_DATABASE_ID", "d")
    args = parse_args(
        ["--catch-up", "--skip-notion-view", "--digest-file", str(tmp_path / "d.txt")]
    )
    return calls, args


def test_catch_up_fetches_only_unarchived(monkeypatch, tmp_path):
    calls, args = _wire(
        monkeypatch, tmp_path,
        search=lambda: [PccAssetRecord(pk="old"), PccAssetRecord(pk="new")],
    )
    assert asyncio.run(runmod.run_pcc_archive(args)) == 0
    assert calls["searched"] == (date(2026, 11, 18), TODAY)
    assert calls["fetched"] == ["new"] and calls["upserted"] == ["new"]


def test_catch_up_waf_block_exits_3(monkeypatch, tmp_path):
    def blocked():
        raise PccWafBlockedError("blocked")

    calls, args = _wire(monkeypatch, tmp_path, search=blocked)
    assert asyncio.run(runmod.run_pcc_archive(args)) == runmod.WAF_EXIT_CODE
    assert calls["fetched"] == []
    assert "WAF" in (tmp_path / "d.txt").read_text()
