"""PCC 取 _csrf：診斷摘要與重試。"""
import asyncio

import aiohttp
import pytest

from app.services import pcc_http_client as mod
from app.services.pcc_http_client import PccHttpClient, is_waf_blocked, summarize_response

GOOD = '<form><input type="hidden" name="_csrf" value="TOKEN123"></form>'
BLOCKED = "<html><body><h1>Access Denied</h1><script>x()</script></body></html>"


class _Resp:
    def __init__(self, status=200, body="", headers=None):
        self.status = status
        self._body = body
        self.headers = headers or {}

    async def text(self, errors="strict"):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    def __init__(self, items):
        self._items = list(items)
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        item = self._items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def sleeps(monkeypatch):
    recorded = []

    async def fake_sleep(sec):
        recorded.append(sec)

    monkeypatch.setattr(mod.asyncio, "sleep", fake_sleep)
    return recorded


def _client(items):
    c = PccHttpClient()
    c._session = _Session(items)
    return c


def test_summary_contains_status_headers_and_stripped_text():
    s = summarize_response(
        403, {"Server": "AkamaiGHost", "Retry-After": "30"}, BLOCKED
    )
    assert "HTTP 403" in s and "AkamaiGHost" in s and "Retry-After" in s
    assert "Access Denied" in s and "x()" not in s  # script 內容不外洩


WAF_BLOCK_PAGE = (
    "<html><head><title>The URL you requested has been blocked</title></head>"
    "<body>Request Rejected</body></html>"
)


def test_waf_block_page_is_tagged():
    s = summarize_response(500, {}, WAF_BLOCK_PAGE)
    assert s.startswith("[WAF 封鎖] HTTP 500")
    assert is_waf_blocked(WAF_BLOCK_PAGE)


def test_non_waf_pages_are_not_tagged():
    assert "[WAF 封鎖]" not in summarize_response(403, {}, BLOCKED)
    assert not is_waf_blocked(GOOD)


def test_success_first_try_no_sleep(sleeps):
    c = _client([_Resp(200, GOOD)])
    assert asyncio.run(c._refresh_csrf()) == "TOKEN123"
    assert c.session.calls == 1 and sleeps == []


def test_retries_then_succeeds(sleeps):
    c = _client([_Resp(403, BLOCKED), _Resp(200, BLOCKED), _Resp(200, GOOD)])
    assert asyncio.run(c._refresh_csrf()) == "TOKEN123"
    assert c.session.calls == 3
    assert sleeps == [5.0, 15.0]


def test_exhausted_raises_with_diagnostics(sleeps):
    c = _client([_Resp(403, BLOCKED, {"Server": "X"})] * 3)
    with pytest.raises(RuntimeError, match=r"找不到 _csrf.*HTTP 403.*Access Denied"):
        asyncio.run(c._refresh_csrf())
    assert c.session.calls == 3


def test_network_error_is_retried(sleeps):
    c = _client([aiohttp.ClientConnectionError("boom"), _Resp(200, GOOD)])
    assert asyncio.run(c._refresh_csrf()) == "TOKEN123"
    assert c.session.calls == 2 and sleeps == [5.0]
