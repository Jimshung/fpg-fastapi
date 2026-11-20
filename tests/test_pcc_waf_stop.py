"""PCC 遭 WAF 封鎖：立即停止、保留已擷取結果、請求間隔含抖動。"""
import asyncio

import pytest

from app.models.pcc_asset_record import PccAssetRecord
from app.services import pcc_http_client as mod
from app.services.pcc_http_client import PccHttpClient, PccWafBlockedError
from tests.test_pcc_csrf_retry import GOOD, WAF_BLOCK_PAGE, _Resp, _Session


@pytest.fixture
def sleeps(monkeypatch):
    recorded = []

    async def fake_sleep(sec):
        recorded.append(sec)

    monkeypatch.setattr(mod.asyncio, "sleep", fake_sleep)
    return recorded


def _client(items, **kw):
    c = PccHttpClient(**kw)
    c._session = _Session(items)
    return c


def test_csrf_waf_block_stops_without_retry(sleeps):
    c = _client([_Resp(500, WAF_BLOCK_PAGE)] * 3)
    with pytest.raises(PccWafBlockedError, match="WAF 封鎖"):
        asyncio.run(c._refresh_csrf())
    assert c.session.calls == 1 and sleeps == [] and c.waf_blocked


def test_non_waf_failure_still_retries(sleeps):
    c = _client([_Resp(403, "<h1>Access Denied</h1>"), _Resp(200, GOOD)])
    assert asyncio.run(c._refresh_csrf()) == "TOKEN123"
    assert c.session.calls == 2 and not c.waf_blocked


def test_request_pause_has_jitter(sleeps):
    c = _client([_Resp(200, "ok")] * 20, request_pause=1.0)
    for _ in range(20):
        asyncio.run(c._get_html("http://x"))
    assert all(1.0 <= s <= 1.5 for s in sleeps)
    assert len(set(sleeps)) > 1  # 不是固定間隔


def test_fetch_cases_keeps_partial_and_stops(sleeps):
    c = _client([_Resp(500, WAF_BLOCK_PAGE)] * 10)
    c._csrf = "T"

    async def fake_detail(base):
        if base.pk == "2":
            raise PccWafBlockedError("blocked")
        base.status = "ok"
        return base

    c.fetch_detail = fake_detail
    bases = [PccAssetRecord(pk=str(i)) for i in (1, 2, 3, 4)]
    out = asyncio.run(c.fetch_cases(bases))
    assert [r.status for r in out] == ["ok", "error", "error", "error"]
    assert all("WAF 封鎖" in r.error for r in out[1:])
    assert c.session.calls == 0  # 第 2 筆被擋後，第 3、4 筆沒有再請求
