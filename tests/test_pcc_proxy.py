import asyncio

import pytest

from app.services.pcc_http_client import PccHttpClient, PccWafBlockedError


def run(coro):
    return asyncio.run(coro)


def make(**kw):
    return PccHttpClient(
        request_pause=0, proxy_url="https://script.google.com/x/exec", proxy_key="k", **kw
    )


def test_proxy_skips_csrf_and_searches_via_get(monkeypatch):
    c = make()
    seen = []

    async def fake_relay(url):
        seen.append(url)
        return 200, "<html></html>"

    monkeypatch.setattr(c, "_relay_get", fake_relay)
    assert run(c._refresh_csrf()) == ""
    run(c._search(label="t", notice_begin="2026/01/01", notice_end="2026/01/02"))
    assert len(seen) == 1
    assert "readAspam?" in seen[0]
    assert "searchBeginNoticeDate=2026%2F01%2F01" in seen[0]
    assert "_csrf" not in seen[0]


def test_relay_waf_body_raises(monkeypatch):
    c = make()

    class Resp:
        status = 200

        async def json(self, content_type=None):
            return {"status": 500, "body": "Web Page Blocked! x"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

    class Sess:
        def get(self, *a, **k):
            return Resp()

    c._session = Sess()
    with pytest.raises(PccWafBlockedError):
        run(c._relay_get("https://web.pcc.gov.tw/opas/aspam/public/readAspam"))
