"""Notion 429／5xx 重試與節流。"""
import asyncio

import pytest

from app.services import notion_archive_service as mod
from app.services.notion_archive_service import (
    NotionThrottle,
    notion_request,
    notion_retry_delay,
)


class _Resp:
    def __init__(self, status, body="{}", headers=None):
        self.status = status
        self._body = body
        self.headers = headers or {}

    async def text(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def request(self, method, url, **kwargs):
        self.calls += 1
        return self._responses.pop(0)


@pytest.fixture
def sleeps(monkeypatch):
    recorded = []

    async def fake_sleep(sec):
        recorded.append(sec)

    monkeypatch.setattr(mod.asyncio, "sleep", fake_sleep)
    return recorded


def _run(session, throttle=None):
    return asyncio.run(
        notion_request(
            session,
            "POST",
            "https://api.notion.com/v1/x",
            headers={},
            json_body={},
            throttle=throttle or NotionThrottle(),
        )
    )


def test_retry_after_header_is_honoured():
    assert notion_retry_delay(0, "2") == 2.0
    assert notion_retry_delay(3, "999") == mod.NOTION_BACKOFF_MAX


def test_backoff_grows_exponentially_without_header():
    d0, d2 = notion_retry_delay(0), notion_retry_delay(2)
    assert 1.0 <= d0 <= 1.25
    assert 4.0 <= d2 <= 5.0


def test_429_then_success(sleeps):
    session = _Session(
        [
            _Resp(429, '{"code": "rate_limited"}', {"Retry-After": "1"}),
            _Resp(200, '{"ok": true}'),
        ]
    )
    throttle = NotionThrottle()
    assert _run(session, throttle) == {"ok": True}
    assert session.calls == 2
    assert 1.0 in sleeps  # Retry-After 等待
    assert throttle.extra_pause > 0  # 限流後放慢，成功後只衰減不歸零


def test_429_exhausted_raises(sleeps):
    session = _Session([_Resp(429, '{"code": "rate_limited"}')] * 10)
    with pytest.raises(RuntimeError, match="429"):
        _run(session)
    assert session.calls == mod.NOTION_MAX_RETRIES + 1


def test_non_retryable_error_fails_immediately(sleeps):
    session = _Session([_Resp(400, '{"code": "validation_error"}')])
    with pytest.raises(RuntimeError, match="400"):
        _run(session)
    assert session.calls == 1
    assert sleeps == []


def test_throttle_decays_on_success():
    t = NotionThrottle()
    t.on_rate_limited()
    t.on_rate_limited()
    assert t.extra_pause == pytest.approx(2 * mod.NOTION_THROTTLE_STEP)
    for _ in range(30):
        t.on_success()
    assert t.extra_pause == 0.0
