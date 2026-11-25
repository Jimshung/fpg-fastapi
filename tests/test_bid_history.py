import asyncio

from app.services.fpg_history_parser import parse_bid_history
from app.services.notion_bid_record import (
    BID_RECORD_HEADING,
    bid_section_block_ids,
    build_bid_blocks,
    needs_record,
    recorded_quote_time,
    sync_bid_record,
)
from app.services.notion_zip_contents import managed_attachment_block_ids


def _row(no, cell_time, status, confirm):
    return f"""
<tr bgcolor=#FFFFFF>
 <td><font>{no}</font></td><td><font>AA-UT0001/01</font></td>
 <td><font>2026/11/01</font></td><td><font>2026/11/10</font></td><td><font>某廠</font></td>
 <td><font>{cell_time}</font><br><font>{status}<br></font><font color="red">(詢價截止)</font></td>
 <td><input type="button" value=詳細 onClick="{confirm}"></td>
</tr>"""


HTML = (
    "<table>"
    + _row(1, "2026/11/24  19:56:07", "已報價",
           "goConfirm(this.form,'111','AA-UT0001','S','','01','true')")
    + _row(2, "2026/11/18  16:32:33", "已檢視",
           "goConfirm(this.form,'111','BB-UT0002','S','','02','true')")
    + "</table>"
)


def test_parse_bid_history_rows():
    rows = parse_bid_history(HTML)
    assert [(r.tndsalno, r.inqcnt, r.status_text) for r in rows] == [
        ("AA-UT0001", "01", "已報價"),
        ("BB-UT0002", "02", "已檢視"),
    ]
    assert rows[0].quote_time == "2026/11/24 19:56:07"
    assert rows[0].blocid == "111" and rows[0].inqexpire == "true"


def _page(time_text):
    rich = [{"plain_text": time_text}] if time_text else []
    return {"id": "p1", "properties": {"報價時間": {"rich_text": rich}}}


def test_needs_record_by_quote_time():
    assert needs_record(_page(""), "2026/11/24 19:56:07")
    assert needs_record(_page("2026/11/20 10:00:00"), "2026/11/24 19:56:07")
    assert not needs_record(_page("2026/11/24 19:56:07"), "2026/11/24 19:56:07")
    assert needs_record(_page("2026/11/24 19:56:07"), "2026/11/24 19:56:07", force=True)
    assert recorded_quote_time(_page("x ")) == "x"


def _block(bid, btype, text=""):
    rich = [{"plain_text": text}] if text else []
    return {"id": bid, "type": btype, btype: {"rich_text": rich}}


def test_bid_section_and_attachment_sections_do_not_overlap():
    # 附件區段在前、投標紀錄在後
    a_then_b = [
        _block("n1", "paragraph", "手動備註"),
        _block("a1", "heading_2", "標售附件"),
        _block("a2", "paragraph", "附件內容｜abc"),
        _block("a3", "pdf"),
        _block("b1", "heading_2", BID_RECORD_HEADING),
        _block("b2", "paragraph", "報價時間：x"),
        _block("b3", "image"),
    ]
    assert bid_section_block_ids(a_then_b) == ["b1", "b2", "b3"]
    assert managed_attachment_block_ids(a_then_b) == ["a1", "a2", "a3"]

    # 投標紀錄在前、附件區段後來重寫在後
    b_then_a = [
        _block("b1", "heading_2", BID_RECORD_HEADING),
        _block("b2", "paragraph", "報價時間：x"),
        _block("b3", "image"),
        _block("a1", "heading_2", "標售附件"),
        _block("a2", "pdf"),
    ]
    assert bid_section_block_ids(b_then_a) == ["b1", "b2", "b3"]
    assert managed_attachment_block_ids(b_then_a) == ["a1", "a2"]


class FakeNotion:
    file_upload_version = "v"

    def __init__(self, children):
        self.children = children
        self.calls = []

    async def upload_file(self, path, *, filename, content_type):
        self.calls.append(("upload", filename, content_type))
        return "up1"

    async def _list_block_children(self, _block_id):
        return self.children

    async def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("json_body")))
        return {}


def test_sync_replaces_old_section_and_updates_property(tmp_path):
    shot = tmp_path / "x.jpg"
    shot.write_bytes(b"jpg")
    notion = FakeNotion(
        [
            _block("keep", "paragraph", "手動備註"),
            _block("b1", "heading_2", BID_RECORD_HEADING),
            _block("b2", "image"),
        ]
    )
    asyncio.run(sync_bid_record(notion, _page(""), "2026/11/24 19:56:07", shot))
    methods = [c[:2] for c in notion.calls]
    assert ("DELETE", "/blocks/b1") in methods and ("DELETE", "/blocks/b2") in methods
    assert ("DELETE", "/blocks/keep") not in methods
    # 欄位最後才更新
    assert notion.calls[-1][0] == "PATCH" and notion.calls[-1][1] == "/pages/p1"
    appended = [c for c in notion.calls if c[1] == "/blocks/p1/children"][0][2]["children"]
    assert appended == build_bid_blocks("2026/11/24 19:56:07", "up1")


class _Row:
    tndsalno = "AA-UT0001"
    inqcnt = "01"
    quote_time = "2026/11/24 19:56:07"


class _FlakyFpg:
    def __init__(self, failures):
        self.failures = failures
        self.calls = 0

    async def fetch_bid_detail_html(self, _row):
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError("Server disconnected")
        return "<html></html>"


class _Shooter:
    async def capture(self, _html, out_path):
        out_path.write_bytes(b"jpg")
        return out_path


def _run_record_one(failures, tmp_path, monkeypatch):
    from app.scripts import run_bid_history as mod

    monkeypatch.setattr(mod, "CASE_RETRY_PAUSE", 0)
    notion = FakeNotion([])
    fpg = _FlakyFpg(failures)
    ok = asyncio.run(
        mod._record_one(fpg, notion, _Shooter(), tmp_path, _Row(), _page(""))
    )
    return ok, fpg.calls, notion


def test_record_one_retries_transient_failure(tmp_path, monkeypatch):
    ok, calls, notion = _run_record_one(2, tmp_path, monkeypatch)
    assert ok and calls == 3
    assert notion.calls[-1][1] == "/pages/p1"  # 欄位最後更新
    assert list(tmp_path.iterdir()) == []  # 暫存截圖已刪


def test_record_one_gives_up_after_three_attempts(tmp_path, monkeypatch):
    ok, calls, notion = _run_record_one(5, tmp_path, monkeypatch)
    assert not ok and calls == 3
    assert notion.calls == []  # 失敗時完全不寫入 Notion


def test_search_bid_history_uses_deadline_filter():
    from app.services.fpg_http_client import FpgHttpClient

    sent = {}

    class Client(FpgHttpClient):
        async def _get(self, url, **kwargs):
            return ""

        async def _post_form(self, url, data, *, referer):
            sent.update(data)
            return HTML

    rows = asyncio.run(Client().search_bid_history("2026/11/18", "2026/11/25"))
    assert sent["querytype"] == "3"
    assert (sent["iqdat1"], sent["iqdat2"]) == ("2026/11/18", "2026/11/25")
    assert sent["podat1"] == "" and sent["podat2"] == ""
    assert sent["radiostatus"] == "1"
    assert [r.tndsalno for r in rows] == ["AA-UT0001"]  # 已檢視不算
